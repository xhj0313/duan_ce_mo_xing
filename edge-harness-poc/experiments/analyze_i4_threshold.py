"""I4：OOS / 置信度阈值离线扫描（不改模型调用、无需重跑推理）。

原理：pipeline.route 的判定是
    pred = out_of_scope  if (intent == out_of_scope or confidence < CONF_MIN)
raw.jsonl 已记录每行的 pred_intent 与 confidence，因此可在本地精确重演不同 CONF_MIN
下的路由结果——这是**对既有输出的后处理模拟**，与真实重跑等价（分类本身不变）。

用法：
  python experiments/analyze_i4_threshold.py --env pc
  python experiments/analyze_i4_threshold.py --env device
输出：
  - 屏幕：阈值扫描表 + 推荐阈值
  - experiments/artifacts/I4_threshold_sweep_<env>.md（随实验归档）
  - experiments/artifacts/I4_metrics_<env>.json（供 run_experiment.py --metrics-file 登记）
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "eval" / "reports"
ART = ROOT / "experiments" / "artifacts"
ART.mkdir(parents=True, exist_ok=True)

DEFAULT_RUN = {
    "pc": "20261023_094120_qwen3-1.7b_intent_mid_openai",
    "device": "20261023_144520_qwen3-1.7b_intent_mid_openai",
}
CUR_MIN = 0.50


def load_rows(run: str) -> list[dict]:
    rows = []
    for line in (REPORTS / run / "raw.jsonl").read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        if "__error__" in r["output"]:
            continue
        rows.append({"gold": r["meta"].get("gold_intent"),
                     "pred": r["output"].get("pred_intent") or "out_of_scope",
                     "conf": float(r["output"].get("confidence") or 0.0)})
    return rows


def evaluate(rows: list[dict], t: float) -> dict:
    gold = [r["gold"] for r in rows]
    pred = ["out_of_scope" if (r["pred"] == "out_of_scope" or r["conf"] < t) else r["pred"]
            for r in rows]

    n = len(rows)
    acc = sum(1 for g, p in zip(gold, pred) if g == p) / n
    oos_idx = [i for i, g in enumerate(gold) if g == "out_of_scope"]
    in_idx = [i for i, g in enumerate(gold) if g != "out_of_scope"]
    oos_reject = (sum(1 for i in oos_idx if pred[i] == "out_of_scope") / len(oos_idx)
                  if oos_idx else None)
    false_reject = (sum(1 for i in in_idx if pred[i] == "out_of_scope") / len(in_idx)
                    if in_idx else None)

    classes = sorted(set(gold) | set(pred))
    stats = {c: defaultdict(int) for c in classes}
    for g, p in zip(gold, pred):
        if g == p:
            stats[g]["tp"] += 1
        else:
            stats[p]["fp"] += 1
            stats[g]["fn"] += 1
    f1s = []
    for c, s in stats.items():
        tp, fp, fn = s["tp"], s["fp"], s["fn"]
        pr = tp / (tp + fp) if tp + fp else 0.0
        rc = tp / (tp + fn) if tp + fn else 0.0
        f1s.append(2 * pr * rc / (pr + rc) if pr + rc else 0.0)
    macro_f1 = sum(f1s) / len(f1s) if f1s else 0.0

    return {"t": t, "accuracy": acc, "macro_f1": macro_f1,
            "oos_reject": oos_reject, "false_reject": false_reject,
            "oos_pred_count": sum(1 for p in pred if p == "out_of_scope")}


def pick(sweep: list[dict], cur: dict) -> tuple[dict, list[dict], str]:
    """推荐阈值：
    可行 = OOS 拒识≥0.85 且 macro-F1 不劣于当前 1pt 以上。
    若不可行，保持当前阈值，并返回结论类型。
    """
    viable = [s for s in sweep if (s["oos_reject"] or 0) >= 0.85
              and s["macro_f1"] >= cur["macro_f1"] - 0.01]
    if viable:
        best = max(viable, key=lambda s: (s["oos_reject"], s["macro_f1"]))
        return best, viable, "viable"
    # 诊断：阈值区间内是否根本没有变化
    same = len({round(s["macro_f1"], 4) for s in sweep}) == 1
    return cur, [], ("no-effect" if same else "no-viable")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", default="pc", choices=["pc", "device"])
    ap.add_argument("--run", default=None, help="覆盖默认 run id")
    a = ap.parse_args()

    run = a.run or DEFAULT_RUN[a.env]
    rows = load_rows(run)
    conf_dist = defaultdict(int)
    for r in rows:
        conf_dist[r["conf"]] += 1
    print(f"env={a.env} run={run} 有效样本={len(rows)}（已剔除传输错误行）")
    print(f"gold=OOS 样本数: {sum(1 for r in rows if r['gold'] == 'out_of_scope')}")
    print("置信度取值分布: " + ", ".join(f"{k}×{v}" for k, v in sorted(conf_dist.items())))

    ts = [round(0.30 + 0.05 * i, 2) for i in range(14)]      # 0.30 ~ 0.95
    sweep = [evaluate(rows, t) for t in ts]
    cur = evaluate(rows, CUR_MIN)
    best, viable, kind = pick(sweep, cur)

    kind_cn = {"viable": "存在可行阈值", "no-effect": "阈值区间内完全无变化（置信度无区分度）",
               "no-viable": "无可行阈值"}[kind]
    verdict_hint = "adopt" if kind == "viable" else "reject"

    head = "| CONF_MIN | accuracy | macro-F1 | OOS 拒识 | 误拒率 | 判 OOS 条数 |"
    lines = [f"# I4 阈值扫描（{a.env}）", "",
             f"- run: `{run}`｜有效样本 {len(rows)}｜其中 OOS {sum(1 for r in rows if r['gold'] == 'out_of_scope')} 条",
             f"- 置信度分布：{', '.join(f'{k}×{v}' for k, v in sorted(conf_dist.items()))}"
             f"（唯一取值 {len(conf_dist)} 个）",
             f"- 口径：对既有 raw.jsonl 做后处理重演，分类结果不变，仅模拟路由层阈值",
             f"- **结论：{kind_cn}**", "",
             head, "|---|---|---|---|---|---|"]
    for s in sweep:
        mark = " ← 当前" if abs(s["t"] - CUR_MIN) < 1e-9 else (" ★ 推荐" if s is best and kind == "viable" else "")
        lines.append(f"| {s['t']:.2f}{mark} | {s['accuracy']:.4f} | {s['macro_f1']:.4f} | "
                     f"{(s['oos_reject'] or 0):.3f} | {(s['false_reject'] or 0):.3f} | {s['oos_pred_count']} |")
    lines += ["", f"**当前阈值 0.50**：macro-F1 {cur['macro_f1']:.4f}，OOS 拒识 {(cur['oos_reject'] or 0):.3f}，"
                  f"误拒 {(cur['false_reject'] or 0):.3f}"]
    if kind == "viable":
        lines.append(f"**推荐阈值 {best['t']:.2f}**：macro-F1 {best['macro_f1']:.4f}，"
                     f"OOS 拒识 {(best['oos_reject'] or 0):.3f}，误拒 {(best['false_reject'] or 0):.3f}")
    else:
        lines.append("**建议：保持 0.50 不变**——阈值不是有效调节手段。"
                     "改进 OOS 需换机制（规则前置 / 二级确认 / 模型升级），见 schemes.yaml 的 I4 note。")
    text = "\n".join(lines)
    (ART / f"I4_threshold_sweep_{a.env}.md").write_text(text, encoding="utf-8")

    use = best if kind == "viable" else cur
    metrics = {"intent.accuracy": round(use["accuracy"], 4),
               "intent.macro_f1": round(use["macro_f1"], 4),
               "intent.oos_reject": round(use["oos_reject"] or 0, 4),
               "intent.false_reject": round(use["false_reject"] or 0, 4)}
    (ART / f"I4_metrics_{a.env}.json").write_text(
        json.dumps({"recommend": kind, "threshold": use["t"], "metrics": metrics,
                    "verdict_hint": verdict_hint,
                    "confidence_distinct_values": len(conf_dist),
                    "confidence_dist": {str(k): v for k, v in sorted(conf_dist.items())}},
                   ensure_ascii=False, indent=2),
        encoding="utf-8")

    print(text)
    print(f"\n已写出: {ART / f'I4_threshold_sweep_{a.env}.md'}")
    print(f"已写出: {ART / f'I4_metrics_{a.env}.json'}（recommend={kind}）")


if __name__ == "__main__":
    main()
