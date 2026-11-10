"""导出实验汇总（Markdown）——从台账自动生成，避免手工抄录出错。

用法：
  python experiments/export_summary.py                # 写到项目根目录 实验汇总-JSNC202611.md
  python experiments/export_summary.py --out <path>

数据来源：
  experiments/results.jsonl   机器可读台账（append-only）
  experiments/schemes.yaml    方案池（动机/假设/风险/结论）
"""

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent           # edge-harness-poc
PROJECT = ROOT.parent.parent                            # 20261022端侧部署
RESULTS = ROOT / "experiments" / "results.jsonl"
SCHEMES = ROOT / "experiments" / "schemes.yaml"

VERDICT_CN = {"adopt": "采纳", "reject": "否决", "iterating": "迭代中"}
ENV_CN = {"pc": "PC·1.7B", "pc4b": "PC·4B", "device": "真机"}
ALIAS = {"C1": "M2", "baseline": "基线"}          # 台账里的 scheme 名 → 方案池 id
METRIC_SHORT = {
    "intent.macro_f1": "F1", "intent.accuracy": "acc", "intent.oos_reject": "OOS",
    "intent.false_reject": "误拒", "faq.info_point_hit": "faq", "faq.intent_route_ok": "路由",
    "faq.refuse_rate": "转云", "mask.precision": "P", "mask.recall": "R",
    "tool.A": "A", "tool.B": "B", "tool.C": "C", "tool.D": "D",
    "faq.judge_agreement": "一致率",
}
KEY_FINDINGS = [
    "优化分两类：**模型无关**（T1/T5/T1b/M2/F2/E1/I5，两模型同向受益）与**依赖容量**（I1/F1/FAQ 生成链路）。",
    "**不要为省模型的力气改它的输入**：C1 首版把原文换成占位符，mask 精度从 0.83 崩到 0.54；改为"
    "「模型看原文 + 规则事后补漏」后达到 0.961。",
    "**确定性短路（F2）性价比最高**：faq 4B 0.798→0.827、1.7B 0.577→0.663；且收益与模型容量负相关。",
    "**上下文本来就短时，检索是负优化**：A1 只喂 top-3 信息点，两模型分别 -1.9/-5.7pt。",
    "**指标会骗人**：F3 补全版 0.74→0.83 是把卡片原文机械补进答案；而判分器 v2 系统性偏严，"
    "faq 真实值比登记值高 4-8pt（v3 复核）。",
    "**切题性判分（v4）无法鉴别补全型虚高**：补全版 0.817 仍高于诚实作答 0.798 → 该边界只能靠"
    "「不加补全」的对照配置来守。",
    "**量化不是瓶颈**：Q4 vs Q8 差异全在 ±2pt 内，Q4 省 40% 内存 → 量产选 Q4_K_M。",
    "**±3pt 是噪声**：同配置重跑 route 类指标漂 3 行样本≈3.3pt；intent 0.899 与阈值的 0.1pt 差距不构成结论。",
]

ORDER = ["intent.accuracy", "intent.macro_f1", "intent.oos_reject", "faq.info_point_hit",
         "faq.intent_route_ok", "mask.precision", "mask.recall",
         "tool.A", "tool.B", "tool.C", "tool.D"]


def load_records() -> list[dict]:
    return [json.loads(l) for l in RESULTS.read_text(encoding="utf-8").splitlines() if l.strip()]


def fmt_metrics(m: dict) -> str:
    parts = []
    for k in ORDER:
        if k in m and isinstance(m[k], (int, float)):
            label = METRIC_SHORT.get(k, k.split(".")[-1])
            parts.append(f"{label} {m[k]:.3f}" if m[k] <= 1 else f"{label} {m[k]:.0f}")
    return " · ".join(parts) or "—"


def first_sentence(text: str, limit: int = 90) -> str:
    t = " ".join((text or "").split())
    if not t:
        return ""
    for sep in ("。", "；", "|"):
        i = t.find(sep)
        if 0 < i < limit:
            return t[:i]
    return t[:limit]


def champions(recs: list[dict]) -> dict[str, dict[str, dict]]:
    latest: dict[str, dict[str, dict]] = collections.defaultdict(dict)
    for r in recs:
        if r["verdict"] != "adopt":
            continue
        for k, v in (r.get("metrics") or {}).items():
            if isinstance(v, (int, float)):
                latest[r["env"]][k] = {"v": v, "scheme": r["scheme"], "ts": r["ts"]}
    return latest


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(PROJECT / "实验汇总-JSNC202611.md"))
    a = ap.parse_args()

    recs = load_records()
    schemes = yaml.safe_load(SCHEMES.read_text(encoding="utf-8"))["schemes"]
    smap = {s["id"]: s for s in schemes}

    v_cnt = collections.Counter(r["verdict"] for r in recs)
    e_cnt = collections.Counter(r["env"] for r in recs)
    tested = collections.Counter(r["scheme"] for r in recs)
    days = sorted({r["ts"][:10] for r in recs})
    pool_cnt = collections.Counter(s["status"] for s in schemes)

    lines: list[str] = []
    A = lines.append

    A("# 实验汇总：端侧智能体 harness 优化（JSNC202611）")
    A("")
    A(f"> 自动生成于台账：`experiments/results.jsonl`；共 **{len(recs)} 条实验记录**、"
      f"**{len(schemes)} 个方案**（其中 {len(tested)} 个已实测）。")
    A("> 口径：faq 命中以 **v2** 为默认登记值；v3（证据化复核）用于能力评估，见各记录备注。")
    A("")
    A("## 零、关键结论（人工撰写，非自动生成）")
    A("")
    for i, k in enumerate(KEY_FINDINGS, 1):
        A(f"{i}. {k}")
    A("")
    A("## 一、概况")
    A("")
    A("| 维度 | 分布 |")
    A("|---|---|")
    A(f"| 记录总数 | {len(recs)} |")
    A(f"| 判定 | " + "、".join(f"{VERDICT_CN[k]} {v}" for k, v in v_cnt.items()) + " |")
    A(f"| 环境 | " + "、".join(f"{ENV_CN.get(k, k)} {v}" for k, v in e_cnt.items()) + " |")
    A(f"| 方案池状态 | " + "、".join(f"{k} {v}" for k, v in pool_cnt.items()) + " |")
    A(f"| 时间跨度 | {days[0]} ~ {days[-1]}（{len(days)} 个工作日） |")
    A("")

    # 冠军指标
    ch = champions(recs)
    A("## 二、当前冠军指标（各环境最新采纳记录）")
    A("")
    keys = ["intent.accuracy", "intent.macro_f1", "intent.oos_reject", "faq.info_point_hit",
            "mask.precision", "mask.recall", "tool.A", "tool.B", "tool.C", "tool.D"]
    envs = [e for e in ("pc", "pc4b", "device") if e in ch]
    A("| 指标 | " + " | ".join(ENV_CN.get(e, e) for e in envs) + " |")
    A("|---|" + "---|" * len(envs))
    for k in keys:
        cells = []
        for e in envs:
            d = ch[e].get(k)
            cells.append(f"{d['v']:.3f} ({d['scheme']})" if d else "—")
        A(f"| {METRIC_SHORT.get(k, k)} | " + " | ".join(cells) + " |")
    A("")
    A("> faq 一行为 **v3 口径**（F2/X1 记录按 v3 登记）；v2 口径见第四节明细与各记录文档。")
    A("")

    # 按方案聚合
    A("## 三、按方案聚合")
    A("")
    A("| 方案 | 名称 | 记录数 | 最终判定 | 结论摘要 |")
    A("|---|---|---|---|---|")
    for sid, n in tested.most_common():
        s = smap.get(ALIAS.get(sid, sid), {})
        name = "初始基线（各环境）" if sid == "baseline" else s.get("title", "—")
        status = "基准" if sid == "baseline" else s.get("status", "—")
        A(f"| `{sid}` | {name} | {n} | {status} | "
          f"{first_sentence(s.get('note', ''))} |")
    A("")

    # 按日期明细
    A("## 四、实验明细（按时间）")
    A("")
    for day in days:
        day_recs = [r for r in recs if r["ts"][:10] == day]
        A(f"### {day}（{len(day_recs)} 条）")
        A("")
        A("| # | 时间 | 方案 | 环境 | 判定 | 标签 | 关键指标 |")
        A("|---|---|---|---|---|---|---|")
        for r in day_recs:
            idx = recs.index(r) + 1
            A(f"| {idx} | {r['ts'][11:16]} | `{r['scheme']}` | {ENV_CN.get(r['env'], r['env'])} | "
              f"{VERDICT_CN.get(r['verdict'], r['verdict'])} | {r['label'][:34]} | "
              f"{fmt_metrics(r.get('metrics') or {})} |")
        A("")

    # 方案池全表
    A("## 五、方案池全表")
    A("")
    A("| 方案 | 名称 | 状态 | 目标指标 |")
    A("|---|---|---|---|")
    for s in schemes:
        A(f"| `{s['id']}` | {s.get('title', '—')} | {s.get('status', '—')} | "
          f"{', '.join(s.get('target') or []) or '—'} |")
    A("")
    A("## 六、读这份表要注意的三件事")
    A("")
    A("1. **±3pt 是噪声**：同配置重跑（llama.cpp 非确定性）会让 route 类指标漂 3 行样本 ≈3.3pt。"
      "小于 3pt 的差异不要当结论。")
    A("2. **faq 有 v2/v3 两套口径**：v2 确定性、可复现，是本表登记值；v3 用 LLM 证据化复核，"
      "系统性上调 4-8pt（4B 0.788→0.827），对外汇报用 v3。")
    A("3. **delta 均相对各环境初始基线**，链条式采纳后单条实验的净变化请看记录备注里的"
      "「前值→后值」。")
    A("")
    A("---")
    A("")
    A("复现：`python experiments/export_summary.py`（本文件由脚本生成，勿手改）。")

    out = Path(a.out)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"已生成 {out}（{len(lines)} 行）")


if __name__ == "__main__":
    main()
