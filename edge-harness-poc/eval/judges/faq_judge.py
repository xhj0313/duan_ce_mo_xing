"""faq 子集判分：信息点命中 + 意图路由正确性 + 拒答率。

python eval/judges/faq_judge.py --run reports/<run_id> [--mode v0|v1|v2|v3] [--endpoint URL]

口径演进：
- v0（初版启发式）：期望信息点行中的数字/百分比/关键词字面出现在回复中
- v1（F0 优化）：v0 + 引用命中 + 同义归一（免费/免收/不收费 ↔ 0 元 等）
- v2（收紧）：含数字的信息点必须数字在场；无数字的才允许长短语模糊匹配
- v3（证据化复核）：在 v2 之上，仅对 v2 判为 miss 的信息点做 LLM 复核，
  且要求裁判从答案中**原样摘录支撑片段**（摘不出即视为未覆盖）。
  目的：修正启发式的系统性偏严，同时用"证据必须可回溯"挡住裁判的宽松倾向。
  注意：v3 依赖模型端点（非确定性），只用于离线校准，不接入 CI。

报告同时给出 info_point_hit(v3) 与 info_point_hit(v2)，便于跨口径对照。
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
REG = ROOT / "registry"

JUDGE_VERSION = "v2"
THRESHOLDS = {"info_hit": 0.80}

VERIFY_PROMPT = """严格判断【答案】是否覆盖【信息点】的实质内容。

只依据答案中明确出现的内容，禁止常识推断或补全。
若判定覆盖，必须从答案里**原样摘录**支撑片段作为证据；摘不出就说明没覆盖。

【信息点】{point}
【答案】{reply}

只输出 JSON：{{"covered": true 或 false, "evidence": "<从答案原样摘录的片段，未覆盖则为空>"}}
"""

# v4：切题性复核（只对"疑似堆资料"的行调用，控制成本与误伤）
RELEVANCE_PROMPT = """判断【答案】是否在**直接回答**【问题】。

判定为不相关的典型情形：
- 答案主体在罗列/复述与问题无关的资料条目；
- 答案答的是另一个话题（虽然用词相近）；
- 答案只是把知识条目堆在一起，没有针对问题给出结论。

【问题】{question}
【答案】{reply}

只输出 JSON：{{"relevant": true 或 false, "reason": "<一句话说明>"}}
"""

_FULL2HALF = str.maketrans("０１２３４５６７８９％．，", "0123456789%.,")

# 同义等价组：组内任一写法视作等价（统一成规范词后再做 token 匹配）
EQUIV = [
    (("免费", "免收", "不收费", "不收手续费", "不收取", "零元", "0元", "0 元",
      "没有手续费", "手续费为0", "手续费为 0"), "0元"),
    (("t+0", "T+0", "T0"), "T+0"),
    (("t+1", "T+1", "T1"), "T+1"),
]


def load_info_points(intent_id: str) -> dict[str, str]:
    """意图 → {信息点编号: 信息点行文本}"""
    import yaml
    intents = yaml.safe_load((REG / "intents.yaml").read_text(encoding="utf-8"))
    reg = {it["id"]: it for it in intents["intents"]}[intent_id]
    card = (REG / reg["knowledge"]).read_text(encoding="utf-8")
    points = {}
    for line in card.splitlines():
        m = re.match(r"- \[(I\d+)\]\s*(.+)$", line.strip())
        if m:
            points[m.group(1)] = m.group(2)
    return points


def key_tokens(info_line: str) -> list[str]:
    toks = re.findall(r"\d+(?:\.\d+)?%?", info_line)          # 数字/百分比
    toks += re.findall(r"[\u4e00-\u9fa5]{2,}", info_line)[:3]  # 前几个中文词组
    return [t for t in toks if len(t) >= 2]


def canon(s: str) -> str:
    """归一化：全角→半角、去空白/千分位/markdown、小数尾零、万元→元、同义组统一。"""
    s = s.translate(_FULL2HALF).replace(" ", "").replace("**", "")
    s = re.sub(r"(\d+\.\d*?)0+%", r"\1%", s)
    s = re.sub(r"(\d+\.\d*?)0+(?!\d)", r"\1", s)
    s = re.sub(r"(\d+(?:\.\d+)?)万元",
               lambda m: f"{float(m.group(1)) * 10000:.0f}元", s)
    for group, word in EQUIV:
        for w in group:
            s = s.replace(w, word)
    return s


def num_present(reply_c: str, num: str) -> bool:
    """数字命中（带边界）：避免 '5' 命中 '50'、'0' 命中 '10'。"""
    return re.search(rf"(?<![\d.]){re.escape(num)}(?!\d)", reply_c) is not None


def fuzzy_hit(reply_c: str, token: str, thresh: float = 0.75) -> bool:
    """长中文短语的模糊命中：在回复中滑窗比对，相似度≥thresh 即算覆盖。
    解决"可携带身份证到网点调整" vs "可以通过携带身份证到网点调整"这类一字之差。"""
    from difflib import SequenceMatcher
    t = canon(token)
    n = len(t)
    if n < 4 or not reply_c:
        return False
    best = 0.0
    for i in range(0, max(1, len(reply_c) - n + 1)):
        r = SequenceMatcher(None, t, reply_c[i:i + n]).ratio()
        if r > best:
            best = r
            if best >= thresh:
                return True
    return best >= thresh


def bigram_cov(target: str, source: str) -> float:
    """target 的字符二元组在 source 中的覆盖率（0~1）。"""
    t = canon(target)
    s = canon(source)
    if len(t) < 2:
        return 0.0
    grams = {t[i:i + 2] for i in range(len(t) - 1)}
    pool = {s[i:i + 2] for i in range(len(s) - 1)}
    return len(grams & pool) / len(grams)


def padding_suspect(meta_points: list[str], points: dict[str, str], reply: str,
                    cov: float = 0.6) -> list[str]:
    """v4 前置筛：答案里是否整段复述了**非目标**信息点（堆资料的典型特征）。"""
    out = []
    for pid, txt in points.items():
        if pid in meta_points or len(canon(txt)) < 10:
            continue
        if bigram_cov(txt, reply) >= cov:
            out.append(pid)
    return out


def llm_relevant(adapter, question: str, reply: str) -> tuple[bool, str]:
    raw, _ = adapter.generate(RELEVANCE_PROMPT.format(question=question, reply=reply),
                              max_new_tokens=80)
    m = re.search(r"\{.*\}", raw or "", re.S)
    if not m:
        return True, "parse_fail"          # 解析失败不倒向"不相关"，避免误伤
    try:
        obj = json.loads(m.group(0))
    except Exception:  # noqa: BLE001
        return True, "parse_fail"
    reason = str(obj.get("reason") or "").strip()
    return bool(obj.get("relevant", True)), reason


def llm_verify(adapter, point: str, reply: str) -> bool:
    """v3 证据化复核：覆盖必须给出可回溯的原样片段。"""
    raw, _ = adapter.generate(VERIFY_PROMPT.format(point=point, reply=reply),
                              max_new_tokens=96)
    m = re.search(r"\{.*\}", raw or "", re.S)
    if not m:
        return False
    try:
        obj = json.loads(m.group(0))
    except Exception:  # noqa: BLE001
        return False
    if not obj.get("covered"):
        return False
    ev = str(obj.get("evidence") or "").strip().strip('"“”')
    if len(ev) < 2:
        return False
    return canon(ev) in canon(reply)          # 证据必须真的出现在答案里


def judge(run_dir: Path, mode: str = JUDGE_VERSION, adapter=None) -> dict:
    rows = [json.loads(l) for l in (run_dir / "raw.jsonl").open(encoding="utf-8")]
    if mode in ("v3", "v4") and adapter is None:
        raise SystemExit(f"{mode} 需要 --endpoint（LLM 复核）")
    n_point_hit = n_point_total = 0
    n_point_hit_v0 = 0
    n_point_hit_v2 = 0
    n_point_hit_v3 = 0
    n_verified = n_verify_pass = 0
    n_pad_rows = n_irrel_rows = 0
    n_cite = 0
    n_intent_ok = n_refuse = 0
    misses = []
    for r in rows:
        meta, out = r["meta"], r["output"]
        if out.get("intent") == meta["gold_intent"] and out.get("action") == "faq":
            n_intent_ok += 1
        reply = out.get("reply", "")
        if "转人工" in reply:
            n_refuse += 1
        points = load_info_points(meta["gold_intent"])
        reply_c = canon(reply)

        # v4：先判断整行是否"切题"，判定不相关则该行所有信息点一律不计命中
        row_irrelevant = False
        if mode == "v4":
            suspects = padding_suspect(meta["info_points"], points, reply)
            if suspects:
                n_pad_rows += 1
                ok, _reason = llm_relevant(adapter, r["text"], reply)
                if not ok:
                    row_irrelevant = True
                    n_irrel_rows += 1

        for pid in meta["info_points"]:
            n_point_total += 1
            line = points.get(pid, "")
            toks = key_tokens(line)
            hit_v0 = any(tok in reply for tok in toks)
            if hit_v0:
                n_point_hit_v0 += 1

            if mode == "v0":
                hit = hit_v0
            else:
                hit = hit_v0
                if not hit and re.search(rf"[\[\(]?{pid}[\]\)]?", reply):
                    hit = True          # 引用命中
                    n_cite += 1
                if not hit:
                    hit = any(canon(tok) in reply_c for tok in toks)   # 同义/格式归一后命中
                if not hit and mode in ("v2", "v3", "v4"):
                    # 口径收紧：含数字的信息点必须数字在场（防"5万"只答"额度"被判命中）；
                    # 无数字的信息点才允许长短语模糊匹配。
                    nums = [canon(x) for x in re.findall(r"\d+(?:\.\d+)?%?", line)]
                    if nums:
                        hit = any(num_present(reply_c, n) for n in nums)
                    else:
                        hit = any(canon(p) in reply_c or (len(p) >= 4 and fuzzy_hit(reply_c, p))
                                  for p in toks)
            hit_v2 = hit
            if hit_v2:
                n_point_hit_v2 += 1
            if mode in ("v3", "v4") and not hit_v2:
                n_verified += 1
                if llm_verify(adapter, line, reply):
                    hit = True
                    n_verify_pass += 1
            if hit:
                n_point_hit_v3 += 1
            if mode == "v4" and row_irrelevant:
                hit = False                 # 不切题 → 覆盖不算数
            if hit:
                n_point_hit += 1
            elif len(misses) < 20:
                misses.append({"id": r["id"], "point": pid, "line": line[:50],
                               "reply": reply[:50]})
    rate = n_point_hit / n_point_total if n_point_total else None
    rate_v0 = n_point_hit_v0 / n_point_total if n_point_total else None
    rate_v2 = n_point_hit_v2 / n_point_total if n_point_total else None
    rate_v3 = n_point_hit_v3 / n_point_total if n_point_total else None
    return {"n": len(rows), "judge_version": mode,
            "intent_route_ok": n_intent_ok / len(rows) if rows else None,
            "info_point_hit": rate, "info_point_hit_v0": rate_v0,
            "info_point_hit_v2": rate_v2, "info_point_hit_v3": rate_v3,
            "verify_calls": n_verified, "verify_pass": n_verify_pass,
            "pad_suspect_rows": n_pad_rows, "irrelevant_rows": n_irrel_rows,
            "cite_hits": n_cite,
            "refuse_rate": n_refuse / len(rows) if rows else None,
            "miss_examples": misses,
            "threshold_check": {"info_hit>=0.80": (rate or 0) >= THRESHOLDS["info_hit"]}}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--mode", default=JUDGE_VERSION, choices=["v0", "v1", "v2", "v3", "v4"])
    ap.add_argument("--endpoint", default="http://127.0.0.1:8080/v1",
                    help="v3 复核用的模型端点")
    a = ap.parse_args()
    run_dir = Path(a.run)
    if not run_dir.is_absolute():
        run_dir = Path(__file__).resolve().parent.parent / "reports" / run_dir
    adapter = None
    if a.mode in ("v3", "v4"):
        import sys
        sys.path.insert(0, str(ROOT))
        from harness.adapter_openai import OpenAIAdapter
        adapter = OpenAIAdapter(a.endpoint)
    rep = judge(run_dir, a.mode, adapter)
    (run_dir / f"report{'' if a.mode == JUDGE_VERSION else '_' + a.mode}.json").write_text(
        json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in rep.items() if k != "miss_examples"},
                     ensure_ascii=False, indent=2))
    for m in rep["miss_examples"][:6]:
        print("MISS", m["id"], m["point"], "|", m["line"], "| reply:", m["reply"])
