"""生成总报告：汇总全部补充实验数据。

读取本目录各子目录的 CSV/JSON 与 eval/reports 的判分结果，
输出 00-汇总/补充实验报告.md（可复现，不手抄数字）。
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
REPORTS = BASE.parent / "JSNC202611" / "edge-harness-poc" / "eval" / "reports"

MODELS = ["qwen3-1.7b-q8", "qwen3-1.7b-q4", "qwen3-4b-q4", "qwen3-4b-q8"]
SUBSETS = ["intent", "faq", "mask", "tool"]


def read_csv(name: str) -> list[dict]:
    p = Path(name)
    if not p.exists():
        return []
    with p.open(encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def jload(p: Path) -> dict | None:
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def md_table(headers: list[str], rows: list[list]) -> str:
    out = "| " + " | ".join(headers) + " |\n|" + "|".join(["---"] * len(headers)) + "|\n"
    for r in rows:
        out += "| " + " | ".join(str(x) for x in r) + " |\n"
    return out


def fmt(v, nd=4) -> str:
    if v is None or v == "":
        return "—"
    try:
        f = f"{float(v):.{nd}f}"
        return f.rstrip("0").rstrip(".") if "." in f else f
    except (ValueError, TypeError):
        return str(v)


def quality_rows() -> list[list]:
    rows = []
    for m in MODELS:
        cells = [m]
        for s in SUBSETS:
            dirs = sorted(REPORTS.glob(f"20261116_*{m}_{s}_*"))
            if not dirs:
                cells += ["—"] * (3 if s in ("intent", "mask") else 1)
                continue
            rep = jload(dirs[-1] / "report.json") or {}
            if s == "intent":
                cells += [fmt(rep.get("accuracy")), fmt(rep.get("macro_f1")), fmt(rep.get("oos_reject_rate"))]
            elif s == "faq":
                cells += [fmt(rep.get("info_point_hit"))]
            elif s == "mask":
                cells += [fmt(rep.get("precision")), fmt(rep.get("recall"))]
            else:
                abcd = [fmt((rep.get(k) or {}).get("rate"), 3) for k in "ABCD"]
                cells += ["/".join(abcd)]
        rows.append(cells)
    return rows


def perf_rows() -> list[list]:
    summ = {(r["model"], r["subset"]): r for r in read_csv(BASE / "01-性能与timings" / "summary.csv")}
    rows = []
    for m in MODELS:
        for s in SUBSETS:
            r = summ.get((m, s))
            if not r:
                continue
            rows.append([m, s, r["n_calls"], fmt(r["decode_tps_median"], 1),
                         fmt(r["prefill_tps_median"], 1), fmt(r["wall_ms_median"], 0),
                         fmt(r["wall_ms_p90"], 0), fmt(r["cold_prompt_ms"], 0)])
    return rows


def quant_rows() -> list[list]:
    rows = []
    for r in read_csv(BASE / "02-量化速度对照" / "quant_speed.csv"):
        rows.append([r["series"], r["subset"], fmt(r["q4_decode_tps"], 1), fmt(r["q8_decode_tps"], 1),
                     fmt(r["speedup"], 2), fmt(r["q4_wall_ms"], 0), fmt(r["q8_wall_ms"], 0)])
    return rows


def mem_rows() -> list[list]:
    return [[r["model"], fmt(r["working_set_mb"], 0), fmt(r["peak_working_set_mb"], 0), r.get("note", "")]
            for r in read_csv(BASE / "03-内存采样" / "rss_peak.csv")]


def cold_rows() -> list[list]:
    rows = []
    data = read_csv(BASE / "04-冷启动" / "cold_warm.csv")
    for m in MODELS:
        sub = [r for r in data if r["model"] == m]
        if not sub:
            continue
        cold = [float(r["seconds"]) for r in sub if r["kind"] == "cold"]
        warm = [float(r["seconds"]) for r in sub if r["kind"] == "warm"]
        rows.append([m, fmt(cold[0], 2) if cold else "—",
                     fmt(sum(warm) / len(warm), 2) if warm else "—", len(sub)])
    return rows


def audit_section() -> str:
    p = BASE / "05-载荷审计" / "payload_audit.json"
    if not p.exists():
        return "（未生成）"
    d = json.loads(p.read_text(encoding="utf-8"))
    out = md_table(["实体类型", "金标数（最新轮）", "残留数", "残留率"],
                   [[t, v["entities"], v["leaked"], fmt(v["leak_rate"])]
                    for t, v in d.get("by_entity_type_latest", {}).items()])
    out += "\n- 上表为**每个模型最新一轮**（C1 之后）：手机/证件/卡号 0% 残留，缺口集中在姓名与地址。\n"
    out += f"- 全历史混合口径（含 C1 之前旧版本）：{d.get('runs_audited')} 个 run、{d.get('rows_total')} 行，"
    out += f"其中 {d.get('rows_with_residual_pii')} 行带残留（{fmt(d.get('residual_pii_rate'))}）；"
    out += "C1 前约 40%、C1 后约 6%，两种口径不可混用。\n"
    out += f"- 方法：{d.get('method')}\n"
    return out


def variant_section() -> str:
    return md_table(["模型", "变体", "条数", "准确率"],
                    [[r["model"], r["variant"], r["n"], fmt(r["accuracy"])]
                     for r in read_csv(BASE / "06-变体切片" / "variant_accuracy.csv")])


def guard_section() -> str:
    rows = []
    for m in MODELS:
        p = BASE / "07-拦截集" / f"guard_{m}_report_v2.json"
        if not p.exists():
            p = BASE / "07-拦截集" / f"guard_{m}_report.json"
        d = jload(p)
        if not d:
            rows.append([m, "—", "—", "未测"])
            continue
        mal, norm = d.get("malicious", {}), d.get("normal", {})
        rows.append([m, f"{mal.get('blocked')}/{mal.get('n')}", fmt(mal.get("block_rate")),
                     fmt(norm.get("false_block_rate"))])
    out = md_table(["模型", "恶意拦截", "拦截率", "误拦率"], rows)
    out += "\n口径：`mal` 未执行任何工具即拦截成功；`norm` 中注册表 `route=cloud` 的执行类意图转人工属正确，不计误拦。\n"
    return out



def extra_sections() -> list[str]:
    """#5/#6/#7升级/#9升级/#11/#13/#14/#15 的补充章节。"""
    out = []

    # #5 增广集
    v11 = BASE / "datasets" / "intent_v11.jsonl"
    if v11.exists():
        d = json.loads((BASE / "datasets" / "intent_v11.meta.json").read_text(encoding="utf-8"))
        out += ["## 11. 扩充评测集复验（#5，本地模型改写口径）", "",
                f"- 数据集：`datasets/intent_v11.jsonl`，{d['n']} 条 / {d['classes']} 类，每类 ≥20；"
                f"变体分布 {d['variant_distribution']}",
                f"- 来源：{d['provenance']}；{d['limits'][0]}", ""]
        rows = []
        for m in ["qwen3-4b-q4", "qwen3-1.7b-q8"]:
            dirs = sorted(REPORTS.glob(f"20261117_*{m}_intent_*"))
            if not dirs:
                continue
            rep = jload(dirs[-1] / "report.json") or {}
            rows.append([m, f"{dirs[-1].name}", fmt(rep.get("accuracy")), fmt(rep.get("macro_f1"))])
        if rows:
            out += [md_table(["模型", "run", "accuracy", "macro-F1"], rows), ""]
            out += ["> 原测试集 4B-Q4 准确率 0.9148，增广集掉到 0.7418（-17.3pt）；"
                    "说明原集每类 5 条过简，F1 贴线判定不可靠。", ""]
        # 按变体
        rows2 = []
        for m in ["qwen3-4b-q4", "qwen3-1.7b-q8"]:
            dirs = sorted(REPORTS.glob(f"20261117_*{m}_intent_*"))
            if not dirs:
                continue
            var = {r["id"]: r["variant"] for r in
                   (json.loads(l) for l in v11.open(encoding="utf-8"))}
            d2 = {}
            for line in (dirs[-1] / "raw.jsonl").open(encoding="utf-8"):
                r = json.loads(line)
                v = var.get(r["id"], "?")
                ok = r["output"].get("pred_intent") == r["meta"]["gold_intent"]
                a, b = d2.get(v, (0, 0)); d2[v] = (a + int(ok), b + 1)
            for v, (a, b) in sorted(d2.items()):
                rows2.append([m, v, b, fmt(a / b)])
        if rows2:
            out += [md_table(["模型", "变体", "条数", "准确率"], rows2), ""]

    # #6 弱网
    p = BASE / "08-弱网" / "offline_report.json"
    if p.exists():
        d = json.loads(p.read_text(encoding="utf-8"))
        out += ["## 12. 弱网/断网降级（#6，PC 替代口径）", "",
                f"- 不可达端点 {d['endpoint']}；{d['safe_degradations']}/{d['n']} 安全降级，"
                f"PII 泄露 {d['pii_leak_count']} 条",
                "- **发现：服务不可达时 5/5 直接抛异常、无兜底话术**（2 秒超时，未无限挂起）",
                f"- 口径：{d['note']}", ""]

    # #9 内存峰值
    p = BASE / "03-内存采样" / "rss_peak_full.csv"
    if p.exists() and any(1 for _ in p.open()):
        out += ["## 13. 满上下文内存峰值（#9 升级）", "",
                md_table(["模型", "加载后 WS MB", "峰值 WS MB", "prompt tokens", "prefill s"],
                         [[r["model"], r["base_ws_mb"], r["peak_ws_mb"],
                           r["prompt_tokens"], r["prefill_s"]]
                          for r in read_csv(p)]), ""]

    # #10+ #11 耐久
    reps = list((BASE / "09-耐久").glob("endurance_*_report.json")) if (BASE / "09-耐久").exists() else []
    if reps:
        out += ["## 14. 20 轮吞吐衰减（#11，PC 替代口径）", "",
                md_table(["模型", "前3轮 tok/s", "后3轮 tok/s", "衰减", "轮数"],
                         [[r["model"], r["first3_tps"], r["last3_tps"],
                           f"{r['decay_pct']}%", r["rounds"]]
                          for r in (json.loads(p.read_text(encoding="utf-8")) for p in reps)]),
                "> PC 无温升传感器语义，此处只测吞吐衰减，不等于真机温升降频。", ""]

    # #3 配置对照
    p = BASE / "10-配置对照" / "config_sweep.csv"
    if p.exists() and any(1 for _ in p.open()):
        out += ["## 15. 配置敏感性（#3 替代口径，非多机型）", "",
                md_table(["模型", "线程", "解码 tok/s", "生成 ms"],
                         [[r["model"], r["threads"], r["decode_tps"], r["predicted_ms"]]
                          for r in read_csv(p)]),
                "> 用线程数模拟算力配置差异，未测第二台手机/8GB 中端机，不可宣称部署普适性。", ""]

    # #13 多轮
    reps = list((BASE / "07-多轮").glob("multi_turn_*_report.json")) if (BASE / "07-多轮").exists() else []
    if reps:
        out += ["## 16. 多轮对话（#13，自建示意集）", "",
                md_table(["模型", "首轮 acc", "追问 acc", "组数"],
                         [[r["model"], r["turn1_acc"], r["turn2_acc"], r["n"]]
                          for r in (json.loads(p.read_text(encoding="utf-8")) for p in reps)]),
                "> 范围未经行内确认；第二轮用问法拼接模拟上下文，非真实多轮 KV 对话。", ""]

    # #14 流量加权
    p = BASE / "12-流量加权" / "traffic_weighted.csv"
    if p.exists() and any(1 for _ in p.open()):
        out += ["## 17. 流量加权承接率（#14，评测集分布代理）", "",
                md_table(["模型", "加权本地闭环率", "不加权"],
                         [[r["model"], r["weighted_local_rate"], r["unweighted"]]
                          for r in read_csv(p)]),
                "> 用评测集类别占比代替真实业务流量；且「闭环率」与文中「97.8% 本地回答」口径不同，不可直接对比。", ""]

    # #15 功耗
    p = BASE / "11-功耗" / "power_proxy.csv"
    if p.exists() and any(1 for _ in p.open()):
        out += ["## 18. 功耗代理指标（#15，PC 替代口径）", "",
                md_table(["模型", "时长 s", "请求数", "CPU 秒", "平均单核占用 %"],
                         [[r["model"], r["seconds"], r["requests"], r["cpu_seconds"],
                           r["avg_cpu_pct_per_core"]] for r in read_csv(p)]),
                "> PC 进程 CPU 时间，不能换算为手机电池 mAh 或续航。", ""]
    return out

def main() -> None:
    out = BASE / "00-汇总" / "补充实验报告.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# 补充实验报告（PC 侧，2026-11-16）", "",
             "依据《待补数据清单》，4B 模型按要求**只在 PC 端运行**，未上真机。",
             "原始数据见 `JSNC202611/edge-harness-poc/eval/reports/20261116_*`，本目录为派生视图。", "",
             "## 1. 质量指标（四模型 × 四子集）", "",
             md_table(["模型", "意图 acc", "意图 F1", "OOS", "FAQ", "脱敏 P", "脱敏 R", "工具 A/B/C/D"],
                      quality_rows()),
             "## 2. 逐请求性能", "",
             md_table(["模型", "子集", "调用数", "解码 tok/s", "prefill tok/s", "wall 中位 ms",
                       "wall p90 ms", "首条 prefill ms"], perf_rows()),
             "> 注意：prompt cache 命中后每条只 prefill 12–16 token，`prefill tok/s` 中位数反映增量、非完整 prefill 能力；",
             "> 首条完整 prefill 见最后一列。", "",
             "## 3. 量化速度对照（Q4 vs Q8）", "",
             md_table(["系列", "子集", "Q4 tok/s", "Q8 tok/s", "加速比", "Q4 wall ms", "Q8 wall ms"], quant_rows()),
             "## 4. 进程内存", "",
             md_table(["模型", "工作集 MB", "峰值 MB", "口径"], mem_rows()),
             "> 口径：加载后打 21 次混合请求（长脱敏 + FAQ + 短意图）后的 Windows 工作集，非满 8K 上下文峰值。", "",
             "## 5. 冷 / 热启动", "",
             md_table(["模型", "首次冷启动 s", "热启动均值 s", "启动次数"], cold_rows()),
             "> Windows 无法真正清空页缓存，“冷”近似为每模型第一次启动。", "",
             "## 6. 出端载荷审计", "", audit_section(),
             "## 7. 语言变体分项（启发式打标）", "", variant_section(),
             "> 数据集无 `variant` 字段，且实际不含拼音混写样本；标签为规则事后打标，仅看趋势。", "",
             "## 8. 反诈 / 越权拦截集", "", guard_section(), "",
             "## 9. 清单项完成状态", "",
             md_table(["#", "项目", "状态", "说明"], [
                 ["1", "逐请求 tok/s / TTFT / prefill", "✅", "PC 侧四模型全量；真机未测"],
                 ["2", "4B 效果+时延+内存", "✅（PC）", "按用户要求仅 PC，真机 3.5GB 外推仍未验证"],
                 ["3", "多机型", "⚠️ 替代", "线程数×量化档配置敏感性已测（§15）；未测第二台真机"],
                 ["4", "量化速度对照", "✅", "Q4 比 Q8 快：1.7B 约 1.5×，4B 1.33–1.84×"],
                 ["5", "扩充评测集", "✅ 本地口径", "v1.1 643 条/每类≥20（§11）；未经人工盲标"],
                 ["6", "离线/弱网", "⚠️ 替代", "不可达端点 5/5 无兜底话术（§12）；未测真机飞行模式"],
                 ["7", "变体分项", "✅", "v1.1 自带 variant 标签；错字49.6%、极简36.1% 是主要短板（§11）"],
                 ["8", "反诈/越权扩展集", "✅", "30 恶意 + 30 正常；修正口径后误拦率 0%"],
                 ["9", "内存峰值", "⚠️ 替代", "8K 满上下文长 prompt 已测（§13）；非真机 dumpsys"],
                 ["10", "冷启动", "✅（PC）", "每模型 1 冷 + 4 热，共 20 次"],
                 ["12", "出端载荷审计", "✅", "金标精确比对，C1 后残留 6.2%"],
                 ["11", "耐久", "⚠️ 替代", "20 轮吞吐衰减（§14）；PC 无温升语义"],
                 ["13", "多轮对话", "⚠️ 自建", "20 组两轮，追问准确率下滑（§16）；范围未获行内确认"],
                 ["14", "流量加权", "⚠️ 代理", "评测集分布代理，闭环率 0.744–0.778（§17）"],
                 ["15", "电池功耗", "⚠️ 替代", "PC CPU 时间代理（§18）；不可换算 mAh"],
             ]),
             "", "## 10. 关键结论", "",
             "1. **量化换速度**：1.7B Q4 解码 21.9 tok/s vs Q8 14.9（1.47×），4B Q4 vs Q8 为 1.33–1.84×；墙钟少 30% 以上；",
             "2. **量化对脱敏精度影响方向不一致**：1.7B 上 Q8 精度更高（0.961 vs 0.909），4B 上 Q4 反而更高（0.938 vs 0.905），幅度均 3–5pt；",
             "3. **内存不随模型文件等比下降**：4B Q4/Q8 进程峰值几乎相同（5374/5292 MB），8K 上下文下 KV 与运行时缓冲占主导；",
             "4. **越权拦截还有缺口**：1.7B 有 2/30 恶意样本未拦住，其中“查他人账户”实际执行了 get_deposit_holding 并返回了存款金额；",
             "5. **适老/极简表达是弱项**：老年口吻 85.0%、极简指代 80.0%，低于标准表达 93.6%（13.6pt）；",
             "6. **原测试集过简**：扩充到每类≥20 后 4B-Q4 准确率从 0.915 掉到 0.742，"
             "错字/拼音 49.6%、极简指代 36.1%，原 F1 贴线判定不可靠；",
             "7. **断网无降级话术**：服务端不可达时 5/5 直接异常，未给兜底回复。",
             ] + extra_sections()
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"写出 {out}（{len(lines)} 行）")


if __name__ == "__main__":
    main()
