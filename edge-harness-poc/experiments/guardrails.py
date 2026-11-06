"""D2：回归护栏（零模型调用，秒级）。

为什么需要：这两天已经踩过两次"改一处、坏另一处"——
① T1 让工具调用打通，但 C 类安全从 1.00 掉到 0.57；
② C1 首版把输入前置替换，mask 精度从 0.83 崩到 0.54。
如果有护栏，第二次改动跑完瞬间就能发现。本脚本把**已采纳方案的关键行为**固化成断言：

  1) 规则层金标测试：T5 安全策略 / I5 意图规则 / T1b 参数校验 / C1 脱敏规则 / F1 输出解析
  2) 注册表与数据一致性：意图→知识卡存在、工具类意图→工具存在
  3) 当前冠军快照：从 results.jsonl 汇总各环境最新 adopt 指标，供人工比对

用法：
  python experiments/guardrails.py          # 全量检查
  python experiments/guardrails.py --quiet  # 只输出结论
退出码：0 全通过；1 有失败项。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

from harness.pipeline import (Harness, apply_rule_mask, merge_rule_entities,  # noqa: E402
                              rebuild_masked_text, sanitize_entities, parse_faq_output,
                              faq_shortcut, luhn_ok)

REG = ROOT / "registry"
RESULTS = ROOT / "experiments" / "results.jsonl"
FAILS: list[str] = []
PASS = 0


def check(name: str, fn) -> None:
    global PASS
    try:
        fn()
        PASS += 1
    except AssertionError as e:
        FAILS.append(f"{name}: {e or '断言失败'}")
    except Exception as e:  # noqa: BLE001
        FAILS.append(f"{name}: {type(e).__name__}: {e}")


# ---------- 1) 规则层金标 ----------

def t5_policy() -> None:
    f = Harness.policy_violation
    assert f("get_balance", {"account": "姓名_1"}, "查[姓名_1]", "查张三余额") == "other_person"
    assert f("get_balance", {}, "把余额发到 boss@bank.com", "把余额发到 boss@bank.com") == "exfil"
    assert f("find_branch", {"city": "武汉"}, "武汉网点", "武汉有哪些网点") is None
    assert f("get_balance", {}, "查下余额", "查下余额") is None


def i5_intent_rules() -> None:
    f = Harness.apply_intent_rules
    assert f("微信怎么发红包", {"intent": "find_branch", "confidence": .9})["intent"] == "out_of_scope"
    assert f("验证码能告诉别人吗", {"intent": "out_of_scope", "confidence": .9})["intent"] == "security_tips"
    assert f("查下余额", {"intent": "query_balance", "confidence": .9})["intent"] == "query_balance"
    assert f("微信银行怎么开通", {"intent": "service_channel_consult", "confidence": .9})["intent"] != "out_of_scope"


def t1b_args() -> None:
    tools = {t["name"]: t for t in
             yaml.safe_load((REG / "tools.yaml").read_text(encoding="utf-8"))["tools"]}
    assert Harness.invalid_args(tools["find_branch"], {"city": "附近"}, "附近有什么网点") == ["city"]
    assert Harness.invalid_args(tools["find_branch"], {"city": "武汉"}, "武汉哪个网点近") == []
    assert Harness.invalid_args(tools["calc_interest"], {"amount": 35000, "term": "三年"},
                                "存三年利息多少") == ["amount"]
    # 中文数字（十万/三万五）必须能还原
    assert Harness.invalid_args(tools["calc_interest"], {"amount": 100000, "term": "一年"},
                                "十万存一年利息多少") == []
    assert Harness.invalid_args(tools["calc_interest"], {"amount": 35000, "term": "两年"},
                                "三万五存两年") == []


def c1_mask_rules() -> None:
    ents, masked = apply_rule_mask("我手机13812345678，卡号4111111111111111")
    types = {e["type"] for e in ents}
    assert {"PHONE", "BANK_CARD"} <= types, ents
    assert "13812345678" not in masked
    assert not [e for e in apply_rule_mask("订单号 1234567890123456 到账")[0]
                if e["type"] == "BANK_CARD"]
    assert luhn_ok("4111111111111111")
    # 模型脏输出过滤 + 合并 + 重建
    dirty = sanitize_entities([{"type": "NAME", "original": "张三"},
                               {"type": "ID_CARD", "original": "[证件_1]"},
                               {"type": "ORDER_NUM", "original": "123"}])
    assert [e["type"] for e in dirty] == ["NAME"]
    merged = merge_rule_entities(dirty, "张三电话13812345678")
    assert rebuild_masked_text("张三电话13812345678", merged) == "[姓名_1]电话[手机_1]"


def f2_shortcut() -> None:
    """F2：高置信问题直出卡片原文，低置信必须返回 None（交给模型）。"""
    card = (REG / "kb/rate_consult.md").read_text(encoding="utf-8")
    hit = faq_shortcut(card, "房贷利率多少")
    assert hit and "LPR" in hit, hit
    assert faq_shortcut(card, "怎么开卡") is None


def f1_parse() -> None:
    ans, cited = parse_faq_output('{"answer":"免费","cited":["I1"]}')
    assert ans == "免费" and cited == ["I1"]
    ans2, _ = parse_faq_output("用户输入：转账收费吗\n\n答案是免费")
    assert ans2.startswith("答案是免费"), ans2


# ---------- 2) 注册表一致性 ----------

def registry_integrity() -> None:
    intents = yaml.safe_load((REG / "intents.yaml").read_text(encoding="utf-8"))["intents"]
    tools = {t["name"] for t in
             yaml.safe_load((REG / "tools.yaml").read_text(encoding="utf-8"))["tools"]}
    ids = [it["id"] for it in intents]
    assert len(ids) == len(set(ids)), "意图 id 重复"
    for it in intents:
        if it.get("route") == "faq":
            assert (REG / it["knowledge"]).exists(), f"缺知识卡: {it['id']}"
        if it.get("route") == "tool":
            assert it.get("tool") in tools, f"工具未注册: {it['id']} -> {it.get('tool')}"
            for s in it.get("slots") or []:
                if s.get("required"):
                    assert s.get("ask"), f"{it['id']} 必填槽缺 ask 话术"


# ---------- 3) 冠军快照 ----------

def champions() -> list[str]:
    if not RESULTS.exists():
        return ["（无 results.jsonl）"]
    recs = [json.loads(l) for l in RESULTS.read_text(encoding="utf-8").splitlines() if l.strip()]
    latest: dict[tuple[str, str], dict] = {}
    for r in recs:
        if r.get("verdict") != "adopt":
            continue
        for k, v in (r.get("metrics") or {}).items():
            if isinstance(v, (int, float)):
                latest[(r["env"], k)] = {"v": v, "scheme": r["scheme"], "ts": r["ts"]}
    keys = ["intent.macro_f1", "intent.oos_reject", "faq.info_point_hit",
            "tool.A", "tool.C", "mask.precision", "mask.recall"]
    out = []
    for env in sorted({e for e, _ in latest}):
        cells = []
        for k in keys:
            d = latest.get((env, k))
            cells.append(f"{k.split('.')[-1]}={d['v']:.3f}({d['scheme']})" if d else f"{k.split('.')[-1]}=—")
        out.append(f"  [{env}] " + "  ".join(cells))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    checks = [
        ("T5 安全策略", t5_policy),
        ("I5 意图规则", i5_intent_rules),
        ("T1b 参数校验（含中文数字）", t1b_args),
        ("C1 脱敏规则（含 Luhn/脏输出过滤）", c1_mask_rules),
        ("F1 输出解析", f1_parse),
        ("F2 确定性短路", f2_shortcut),
        ("注册表一致性", registry_integrity),
    ]
    for name, fn in checks:
        check(name, fn)

    print(f"护栏检查：{PASS} 通过 / {len(FAILS)} 失败")
    for f in FAILS:
        print("  ✗", f)
    if not a.quiet:
        print("\n当前冠军指标（各环境最新 adopt）：")
        for line in champions():
            print(line)
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
