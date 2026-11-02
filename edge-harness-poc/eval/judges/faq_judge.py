"""faq 子集判分：信息点命中 + 意图路由正确性 + 拒答率。

python eval/judges/faq_judge.py --run reports/<run_id> [--mode v0|v1]

口径：
- v0（初版启发式）：期望信息点行中的数字/百分比/关键词字面出现在回复中
- v1（F0 优化）：在 v0 基础上增加
    ① 引用命中：回复中出现 [I1] 形式的信息点编号即视为命中（强 grounding 信号）
    ② 同义归一：免费/免收/不收费 ↔ 0 元；0.10% ↔ 0.1%；1万元 ↔ 10000元；去千分位/全角
  v1 仍为启发式，取代不了 LLM-as-judge；主要用于消除"同义改写被判 miss"的系统性低估。
- 报告同时给出 info_point_hit(v1) 与 info_point_hit_v0，便于跨口径对照。
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


def judge(run_dir: Path, mode: str = JUDGE_VERSION) -> dict:
    rows = [json.loads(l) for l in (run_dir / "raw.jsonl").open(encoding="utf-8")]
    n_point_hit = n_point_total = 0
    n_point_hit_v0 = 0
    n_cite = 0
    n_intent_ok = n_refuse = 0
    misses = []
    for r in rows:
        meta, out = r["meta"], r["output"]
        if out.get("intent") == meta["gold_intent"] and out.get("action") == "faq":
            n_intent_ok += 1
        if "转人工" in out.get("reply", ""):
            n_refuse += 1
        points = load_info_points(meta["gold_intent"])
        reply = out.get("reply", "")
        reply_c = canon(reply)
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
                if not hit and mode == "v2":
                    # 口径收紧：含数字的信息点必须数字在场（防"5万"只答"额度"被判命中）；
                    # 无数字的信息点才允许长短语模糊匹配。
                    nums = [canon(x) for x in re.findall(r"\d+(?:\.\d+)?%?", line)]
                    if nums:
                        hit = any(num_present(reply_c, n) for n in nums)
                    else:
                        hit = any(canon(p) in reply_c or (len(p) >= 4 and fuzzy_hit(reply_c, p))
                                  for p in toks)
            if hit:
                n_point_hit += 1
            elif len(misses) < 20:
                misses.append({"id": r["id"], "point": pid, "line": line[:50],
                               "reply": reply[:50]})
    rate = n_point_hit / n_point_total if n_point_total else None
    rate_v0 = n_point_hit_v0 / n_point_total if n_point_total else None
    return {"n": len(rows), "judge_version": mode,
            "intent_route_ok": n_intent_ok / len(rows) if rows else None,
            "info_point_hit": rate, "info_point_hit_v0": rate_v0,
            "cite_hits": n_cite,
            "refuse_rate": n_refuse / len(rows) if rows else None,
            "miss_examples": misses,
            "threshold_check": {"info_hit>=0.80": (rate or 0) >= THRESHOLDS["info_hit"]}}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--mode", default=JUDGE_VERSION, choices=["v0", "v1", "v2"])
    a = ap.parse_args()
    run_dir = Path(a.run)
    if not run_dir.is_absolute():
        run_dir = Path(__file__).resolve().parent.parent / "reports" / run_dir
    rep = judge(run_dir, a.mode)
    (run_dir / "report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
    print(json.dumps({k: v for k, v in rep.items() if k != "miss_examples"},
                     ensure_ascii=False, indent=2))
    for m in rep["miss_examples"][:6]:
        print("MISS", m["id"], m["point"], "|", m["line"], "| reply:", m["reply"])
