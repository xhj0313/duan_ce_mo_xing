"""#13 多轮对话集（自建示意集，范围未经行内确认）。

20 组两轮对话：第一轮是明确业务请求，第二轮是依赖上文指代的问题
（"那笔呢""跨行的呢""改成 5 万"等），用于测上下文承接与澄清能力。

口径声明：
- 场景与话术为本实验自建，**未经行内确认范围**；
- 判分重点：第二轮是否正确继承第一轮的意图/槽位，而非答案业务正确性；
- 不能外推为"真实多轮流量表现"。
"""

from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parent / "datasets" / "multi_turn.jsonl"

# (turn1, expected_intent1, turn2, expected_intent2, 关键继承槽位)
CASES = [
    ("转账手续费多少", "fee_consult", "跨行的呢", "fee_consult", "cross_bank"),
    ("查一下我的余额", "query_balance", "那定期的呢", "deposit_product_intro", "deposit"),
    ("我要挂失银行卡", "loss_report_guide", "是尾号 8474 那张", "loss_report_guide", "card_tail=8474"),
    ("密码忘了怎么办", "password_reset_guide", "登录密码", "password_reset_guide", "pwd_type=login"),
    ("附近哪里有网点", "find_branch", "明天营业吗", "branch_hours", "branch=nearby"),
    ("房贷利率多少", "rate_consult", "首套呢", "rate_consult", "house=first"),
    ("转账限额是多少", "quota_consult", "能调到 5 万吗", "quota_consult", "amount=50000"),
    ("怎么开通短信提醒", "sms_notice_guide", "免费吗", "sms_notice_guide", "fee"),
    ("电子回单在哪开", "statement_consult", "要带章的", "statement_consult", "with_seal"),
    ("我要申请贷款", "loan_apply", "装修贷可以吗", "loan_condition_consult", "loan_type=decoration"),
    ("跨行转账收手续费吗", "fee_consult", "一万以上呢", "fee_consult", "amount>10000"),
    ("查最近交易明细", "statement_consult", "只看支出", "statement_consult", "direction=out"),
    ("大额存单利息多少", "deposit_product_intro", "三年的呢", "deposit_product_intro", "term=3y"),
    ("手机银行怎么绑定卡", "app_usage_guide", "绑定别人的卡行吗", "app_usage_guide", "third_party"),
    ("我要投诉", "complaint_feedback", "网点服务态度", "complaint_feedback", "target=branch"),
    ("信用卡账单多少", "credit_card_bill", "能分期吗", "loan_condition_consult", "installment"),
    ("开户行是哪个", "find_branch", "能线上查吗", "find_branch", "channel=online"),
    ("换手机号要什么材料", "password_change_guide", "必须去网点吗", "password_change_guide", "channel=branch"),
    ("理财有什么推荐", "wealth_product_intro", "要稳一点的", "wealth_product_intro", "risk=low"),
    ("提现手续费多少", "fee_consult", "本行 ATM 呢", "fee_consult", "channel=own_atm"),
]


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        for i, (t1, i1, t2, i2, slot) in enumerate(CASES, 1):
            rec = {
                "id": f"mt_{i:02d}", "subset": "multi_turn", "split": "test",
                "turns": [
                    {"text": t1, "gold_intent": i1},
                    {"text": t2, "gold_intent": i2},
                ],
                "meta": {"inherit_slot": slot, "n_turns": 2, "source": "self-built"},
            }
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    meta = {
        "name": "multi_turn", "n": len(CASES), "source": "自建示意集",
        "limits": [
            "范围未经行内确认",
            "只测两轮，不等于真实多轮流量",
            "第二轮 gold_intent 为人工设定，未做标注一致性检验",
        ],
    }
    OUT.with_suffix(".meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"写出 {OUT}（{len(CASES)} 组两轮对话）")


if __name__ == "__main__":
    main()
