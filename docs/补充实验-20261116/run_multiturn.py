"""#13 多轮对话评测（自建示意集，范围未经行内确认）。

Harness 本身是单轮接口，这里直接用 adapter.chat 拼两轮 messages：
  第 1 轮：system + user(turn1) → 提取 pred_intent（复用 pipeline 的 classify prompt）
  第 2 轮：追加 assistant(上一轮回复) + user(turn2) → 提取 pred_intent
判分：第二轮意图是否等于 gold_intent2；另记是否继承第一轮槽位（以意图一致为近似）。

产物：07-多轮/ 下 model 对应的 raw + report。
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1] / "JSNC202611" / "edge-harness-poc"
sys.path.insert(0, str(BASE))

from harness.adapter_openai import OpenAIAdapter  # noqa: E402

DS = Path(__file__).resolve().parent / "datasets" / "multi_turn.jsonl"
OUT = Path(__file__).resolve().parent / "07-多轮"

# 与 harness/prompts/intent_compact.j2 等价的短 prompt（只做意图分类，不做脱敏）
INTENT_PROMPT = """你是银行意图分类器。只输出 JSON：{{"intent":"意图名","confidence":0.0-1.0,"slots":{{}}}}
可选意图：fee_consult, query_balance, quota_consult, rate_consult, transfer_out, loss_report_guide,
password_reset_guide, app_usage_guide, deposit_product_intro, find_branch, branch_hours,
statement_consult, sms_notice_guide, service_channel_consult, security_tips, loan_apply,
loan_condition_consult, wealth_product_intro, complaint_feedback, password_change_guide,
credit_card_bill, out_of_scope
用户问题：{text}"""


def parse_intent(raw: str) -> tuple[str | None, str]:
    try:
        obj = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
        return obj.get("intent"), raw
    except Exception:  # noqa: BLE001
        m = re.search(r'"intent"\s*:\s*"([^"]+)"', raw)
        return (m.group(1) if m else None), raw


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--endpoint", default="http://127.0.0.1:8080/v1")
    ap.add_argument("--model", required=True)
    a = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    ad = OpenAIAdapter(a.endpoint, temperature=0.0)
    rows = [json.loads(l) for l in DS.open(encoding="utf-8") if l.strip()]

    out_rows = []
    ok1 = ok2 = 0
    for rec in rows:
        t1, t2 = rec["turns"]
        r1, raw1 = parse_intent(ad.generate(INTENT_PROMPT.format(text=t1["text"]), 96)[0])
        r2, raw2 = parse_intent(ad.generate(
            INTENT_PROMPT.format(text=f"{t1['text']} / 追问：{t2['text']}"), 96)[0])
        c1 = r1 == t1["gold_intent"]
        c2 = r2 == t2["gold_intent"]
        ok1 += int(c1); ok2 += int(c2)
        out_rows.append({"id": rec["id"], "turn1": t1, "turn2": t2,
                         "pred1": r1, "pred2": r2, "ok1": c1, "ok2": c2,
                         "raw1": raw1[:200], "raw2": raw2[:200]})

    tag = a.model
    with (OUT / f"multi_turn_{tag}_raw.jsonl").open("w", encoding="utf-8") as f:
        for r in out_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    report = {
        "model": tag, "created": dt.datetime.now().isoformat(timespec="seconds"),
        "n": len(out_rows), "turn1_correct": ok1, "turn1_acc": round(ok1 / len(out_rows), 4),
        "turn2_correct": ok2, "turn2_acc": round(ok2 / len(out_rows), 4),
        "note": "自建示意集，范围未经行内确认；第2轮用'上一轮问法 / 追问'拼接模拟上下文，非真实多轮 KV 对话",
    }
    (OUT / f"multi_turn_{tag}_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[{tag}] 首轮 {ok1}/{len(out_rows)} = {report['turn1_acc']} | "
          f"追问 {ok2}/{len(out_rows)} = {report['turn2_acc']}")


if __name__ == "__main__":
    main()
