"""D3：判分器校准（LLM-as-judge 抽检）。

背景：这两天出现两次"指标骗人"——F3 自动补全把 0.74 刷到 0.83（文本堆砌骗过关键词匹配）、
C1 首版把 0.83 打到 0.54（模型脏输出被计为误报）。说明**规则判分本身需要体检**。

做法：抽样 N 条 FAQ 评测记录，让本地大模型当裁判，逐条判断"答案是否覆盖指定信息点"，
与 faq_judge v2 的结论对比，给出：
  - 一致率、假阳（规则说命中、LLM 说没覆盖）、假阴（规则说漏、LLM 说覆盖）
  - 分歧样本明细（供人工复核，判断哪边错）

用法：
  python experiments/calibrate_judge.py --run <faq_run_id> --sample 30 \
      --endpoint http://127.0.0.1:8080/v1
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from harness.adapter_openai import OpenAIAdapter  # noqa: E402
import yaml  # noqa: E402

REG = ROOT / "registry"
REPORTS = ROOT / "eval" / "reports"

PROMPT = """你是银行客服质检员。判断【答案】是否覆盖了【待核对信息点】。

要求：只要答案表达了该信息点的实质内容即可算覆盖（同义改写、换说法都算）；
仅有相关话题但没有该信息点的实质内容，算未覆盖。

【问题】{q}
【答案】{a}
【待核对信息点】
{points}

只输出 JSON：{{"covered": ["<被覆盖的信息点编号>"]}}
"""


def load_points(intent_id: str) -> dict[str, str]:
    intents = yaml.safe_load((REG / "intents.yaml").read_text(encoding="utf-8"))["intents"]
    reg = {it["id"]: it for it in intents}[intent_id]
    card = (REG / reg["knowledge"]).read_text(encoding="utf-8")
    out = {}
    for line in card.splitlines():
        m = re.match(r"- \[(I\d+)\]\s*(.+)$", line.strip())
        if m:
            out[m.group(1)] = m.group(2).strip()
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--sample", type=int, default=30)
    ap.add_argument("--endpoint", default="http://127.0.0.1:8080/v1")
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()

    sys.path.insert(0, str(ROOT / "eval" / "judges"))
    from faq_judge import canon, fuzzy_hit, key_tokens, num_present  # noqa: E402

    def rule_hit(line: str, reply: str) -> bool:
        """复刻 faq_judge v2 的单点判定。"""
        rc = canon(reply)
        if any(t in reply for t in key_tokens(line)):
            return True
        if any(canon(t) in rc for t in key_tokens(line)):
            return True
        nums = [canon(x) for x in re.findall(r"\d+(?:\.\d+)?%?", line)]
        if nums:
            return any(num_present(rc, n) for n in nums)
        return any(canon(p) in rc or (len(p) >= 4 and fuzzy_hit(rc, p))
                   for p in key_tokens(line))

    rows = [json.loads(l) for l in (REPORTS / a.run / "raw.jsonl").open(encoding="utf-8")]
    rows = [r for r in rows if r["output"].get("action") == "faq"
            and r["meta"].get("info_points")]
    random.Random(a.seed).shuffle(rows)
    sample = rows[:a.sample]

    ad = OpenAIAdapter(a.endpoint)
    agree = rule_only = llm_only = 0
    diffs = []
    for r in sample:
        points = load_points(r["meta"]["gold_intent"])
        pids = [p for p in r["meta"]["info_points"] if p in points]
        if not pids:
            continue
        body = "\n".join(f"- [{p}] {points[p]}" for p in pids)
        prompt = PROMPT.format(q=r["text"], a=r["output"].get("reply", ""), points=body)
        raw, _ = ad.generate(prompt, max_new_tokens=96)
        m = re.search(r"\{.*\}", raw, re.S)
        try:
            covered = set(json.loads(m.group(0)).get("covered") or []) if m else set()
        except Exception:  # noqa: BLE001
            covered = set()

        for p in pids:
            rule = rule_hit(points[p], r["output"].get("reply", ""))
            llm = p in covered
            if rule == llm:
                agree += 1
            elif rule and not llm:
                rule_only += 1
                diffs.append(("规则说命中/LLM说没覆盖", r["id"], p, points[p][:40],
                              r["output"].get("reply", "")[:70]))
            else:
                llm_only += 1
                diffs.append(("规则说漏/LLM说覆盖", r["id"], p, points[p][:40],
                              r["output"].get("reply", "")[:70]))

    total = agree + rule_only + llm_only
    print(f"样本 {len(sample)} 条 / 判定 {total} 个信息点")
    if total:
        print(f"一致率 {agree / total:.3f}  | 规则偏严(规则漏) {llm_only}  | 规则偏松(规则命中) {rule_only}")
    print(f"\n分歧样本（最多 8 条）：")
    for kind, rid, pid, line, reply in diffs[:8]:
        print(f"  [{kind}] {rid} {pid} | 期望: {line}")
        print(f"      实际: {reply}")


if __name__ == "__main__":
    main()
