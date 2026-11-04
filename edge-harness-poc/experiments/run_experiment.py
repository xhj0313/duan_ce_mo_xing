"""实验执行与登记：一条命令完成 评测 → 判分 → 落账 → 生成详细报告文档。

落账三层：
  1) experiments/results.jsonl   机器可读原始台账（append-only）
  2) experiments/results.md      全局汇总表（自动重生成）
  3) <workspace>/评测记录/        每次实验一份详细文档 + 索引 README.md（体例同 评测-01/02）

用法：
  # ① 跑真实评测并登记 + 出文档（PC 或真机，仅换 --endpoint / --env）
  python experiments/run_experiment.py --scheme T1 --label "intent→tool 直给工具名" \
      --endpoint http://127.0.0.1:8080/v1 --subsets intent,tool --env pc

  # ② 登记已有结果（不重跑）
  python experiments/run_experiment.py --scheme baseline --label "PC 基线" --env pc \
      --from-run intent=<run_id> faq=<run_id>

  # ③ 只补文档/索引（不改台账）
  python experiments/run_experiment.py --regen

  # ④ 查看汇总表
  python experiments/run_experiment.py --show

约定（见 experiments/README.md）：
- 单变量：一次实验只改一处；
- 尺子与系统分离：判分器口径变更（F0）单独登记，并在 label 里注明；
- 记录 git commit 与 dirty 文件数，便于回溯改动。
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # edge-harness-poc/
WORKSPACE = Path(__file__).resolve().parents[3]        # 20261022端侧部署/（仓库外，报告归档处）
EXP = ROOT / "experiments"
RESULTS_JSONL = EXP / "results.jsonl"
RESULTS_MD = EXP / "results.md"
SCHEMES = EXP / "schemes.yaml"
REPORTS = ROOT / "eval" / "reports"
REPORT_DIR = WORKSPACE / "评测记录"
PY = sys.executable

JUDGES = {"intent": "rule_judge.py", "faq": "faq_judge.py",
          "tool": "tool_judge.py", "mask": "mask_judge.py"}

COLS = [("intent.macro_f1", "intent F1"), ("intent.oos_reject", "OOS拒识"),
        ("faq.info_point_hit", "faq命中"), ("tool.A", "tool A"),
        ("mask.precision", "mask P"), ("mask.recall", "mask R")]

EXTRA_COLS = [("intent.accuracy", "intent acc"), ("intent.false_reject", "intent 误拒"),
              ("faq.intent_route_ok", "faq 路由"), ("faq.refuse_rate", "faq 转云"),
              ("tool.B", "tool B"), ("tool.C", "tool C"), ("tool.D", "tool D"),
              ("mask.f1", "mask F1")]

THRESHOLDS = {
    "intent.macro_f1": 0.90, "intent.oos_reject": 0.85,
    "faq.info_point_hit": 0.80,
    "tool.A": 0.80, "tool.B": 0.80, "tool.C": 1.00,
    "mask.precision": 0.90, "mask.recall": 0.95,
}


def sh(cmd: list[str], cwd: Path = ROOT) -> str:
    r = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"命令失败: {' '.join(cmd)}\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}")
    return r.stdout


def git_info() -> tuple[str, int]:
    try:
        commit = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
                                capture_output=True, text=True).stdout.strip()
        dirty = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain"],
                               capture_output=True, text=True).stdout.strip()
        return commit, len([l for l in dirty.splitlines() if l.strip()])
    except Exception:
        return "", 0


def load_schemes() -> dict:
    try:
        import yaml
        d = yaml.safe_load(SCHEMES.read_text(encoding="utf-8"))
        return {s["id"]: s for s in d.get("schemes", [])}
    except Exception:
        return {}


def run_eval(subset: str, endpoint: str, limit: int | None) -> tuple[str, int, int, float]:
    cmd = [PY, "eval/run_eval.py", "--backend", "openai",
           "--endpoint", endpoint, "--subset", subset]
    if limit:
        cmd += ["--limit", str(limit)]
    t0 = dt.datetime.now()
    out = sh(cmd)
    elapsed = (dt.datetime.now() - t0).total_seconds()
    m = re.search(r"done: (\d+) rows \((\d+) errors\) -> (.+)$", out, re.M)
    if not m:
        raise RuntimeError(f"无法解析 run_eval 输出:\n{out[-1500:]}")
    return Path(m.group(3).strip()).name, int(m.group(1)), int(m.group(2)), elapsed


def run_judge(subset: str, run_dir: str) -> dict:
    sh([PY, f"eval/judges/{JUDGES[subset]}", "--run", run_dir])
    return json.loads((REPORTS / run_dir / "report.json").read_text(encoding="utf-8"))


def flatten(subset: str, rep: dict) -> dict:
    if subset == "intent":
        return {"intent.accuracy": rep.get("accuracy"),
                "intent.macro_f1": rep.get("macro_f1"),
                "intent.oos_reject": rep.get("oos_reject_rate"),
                "intent.false_reject": rep.get("false_reject_rate"),
                "intent.worst_class": rep.get("worst_recall_class")}
    if subset == "faq":
        return {"faq.info_point_hit": rep.get("info_point_hit"),
                "faq.intent_route_ok": rep.get("intent_route_ok"),
                "faq.refuse_rate": rep.get("refuse_rate")}
    if subset == "tool":
        return {f"tool.{t}": (rep.get(t) or {}).get("rate") for t in "ABCD"}
    if subset == "mask":
        return {"mask.precision": rep.get("precision"),
                "mask.recall": rep.get("recall"),
                "mask.f1": rep.get("f1"),
                "mask.false_mask_rows": rep.get("rows_with_false_mask"),
                "mask.no_pii_masked_rows": rep.get("no_pii_but_masked_rows")}
    raise ValueError(subset)


def fmt(v) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.3f}"
    return str(v)


def load_records() -> list[dict]:
    if not RESULTS_JSONL.exists():
        return []
    return [json.loads(l) for l in RESULTS_JSONL.read_text(encoding="utf-8").splitlines() if l.strip()]


def baseline_metrics(records: list[dict], env: str) -> dict:
    for r in records:
        if r["scheme"] == "baseline" and r["env"] == env:
            return r["metrics"]
    return {}


# ---------------- 汇总表 ----------------

def render_md(records: list[dict]) -> str:
    lines = ["# 实验结果登记表", "",
             "> 由 `python experiments/run_experiment.py` 自动生成，请勿手改；方案定义见 `schemes.yaml`。",
             "> 括号内为相对**同环境基线**的差值（pt）。详细报告见工作区 `评测记录/`。", ""]
    if not records:
        lines.append("（暂无记录）")
        return "\n".join(lines) + "\n"
    head = "| # | 实验ID | 方案 | 说明 | 环境 | 时间 | " + " | ".join(c[1] for c in COLS) + " | 判定 | 备注 |"
    sep = "|" + "---|" * (7 + len(COLS) + 2)
    lines += [head, sep]
    for i, r in enumerate(records, 1):
        base = baseline_metrics(records, r["env"])
        cells = []
        for key, _ in COLS:
            v, b = r["metrics"].get(key), base.get(key)
            if v is None:
                cells.append("—")
            elif b is None or r["scheme"] == "baseline":
                cells.append(fmt(v))
            else:
                cells.append(f"{fmt(v)} ({'+' if v - b >= 0 else ''}{100 * (v - b):.1f})")
        lines.append("| {} | {} | {} | {} | {} | {} | {} | {}".format(
            i, r["id"], r["scheme"], r["label"], r["env"], r["ts"][5:16],
            " | ".join(cells), r.get("verdict", "pending"), r.get("notes", "")))
    lines.append("")
    return "\n".join(lines) + "\n"


# ---------------- 详细文档 ----------------

def doc_name(idx: int, rec: dict) -> str:
    return f"评测-{idx:02d}-{rec['env']}-{rec['scheme']}-{rec['ts'][:10].replace('-', '')}.md"


ROOT_DOCS = {1: "../评测-01-Qwen3-1.7B首轮四子集结果.md",
             2: "../评测-02-真机端侧验证报告（PC对比）.md"}


def error_digest(rec: dict) -> list[str]:
    """从 report.json / raw.jsonl 自动摘录错误模式，供回看时快速定位问题。"""
    from collections import Counter
    out: list[str] = []
    runs = rec.get("runs", {})

    intent_run = runs.get("intent")
    if intent_run:
        rp = REPORTS / intent_run / "report.json"
        if rp.exists():
            rep = json.loads(rp.read_text(encoding="utf-8"))
            per = rep.get("per_class", {})
            worst = sorted([(c, v) for c, v in per.items() if v.get("support")],
                           key=lambda kv: kv[1]["recall"])[:5]
            if worst:
                out += ["**意图最差 5 类（按召回）**", "",
                        "| 类 | P | R | F1 | n |", "|---|---|---|---|---|"]
                out += [f"| {c} | {v['precision']:.2f} | {v['recall']:.2f} | {v['f1']:.2f} | {v['support']} |"
                        for c, v in worst]
                out.append("")
        raw = REPORTS / intent_run / "raw.jsonl"
        if raw.exists():
            pairs: Counter = Counter()
            for line in raw.read_text(encoding="utf-8").splitlines():
                r = json.loads(line)
                g, p = r["meta"].get("gold_intent"), r["output"].get("pred_intent")
                if g and p and g != p:
                    pairs[(g, p)] += 1
            if pairs:
                out += ["**高频混淆对（gold → pred）**", ""]
                out += [f"- `{g}` → `{p}` ×{n}" for (g, p), n in pairs.most_common(5)]
                out.append("")

    tool_run = runs.get("tool")
    if tool_run:
        rp = REPORTS / tool_run / "report.json"
        if rp.exists():
            rep = json.loads(rp.read_text(encoding="utf-8"))
            fails = (rep.get("A") or {}).get("fails", [])[:5]
            if fails:
                out += ["**tool A 类失败样本（前 5）**", ""]
                out += [f"- {f['id']}：{f['text']} —— {f['why']}" for f in fails]
                out.append("")

    return out


def write_doc(idx: int, rec: dict, records: list[dict], schemes: dict) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    base = baseline_metrics(records, rec["env"])
    sch = schemes.get(rec["scheme"], {})
    is_base = rec["scheme"] == "baseline"
    L = [f"# 评测-{idx:02d}：{rec['label']}", "",
         f"> 自动生成于 {dt.datetime.now():%Y-%m-%d %H:%M} ｜ 实验ID `{rec['id']}` ｜ "
         f"原始台账 `experiments/results.jsonl`（第 {idx} 条）", ""]

    L += ["## 基本信息", "", "| 项 | 值 |", "|---|---|",
          f"| 方案 | `{rec['scheme']}` |",
          f"| 环境 | {rec['env']} |",
          f"| 模型 | {rec.get('model', '—')} |",
          f"| 端点 | {('`' + rec['endpoint'] + '`') if rec.get('endpoint') else '（离线登记，原始运行见第六节）'} |",
          f"| 时间 | {rec['ts']} |",
          f"| 代码版本 | `{rec.get('commit') or '?'}`（dirty {rec.get('dirty_files', 0)} 个文件） |",
          f"| 判分器版本 | {', '.join(f'{k}={v}' for k, v in (rec.get('judges') or {}).items()) or '默认'} |",
          f"| 取样限制 | {rec.get('limit') or '全量（test split）'} |", ""]

    counter = [0]
    numerals = ["一", "二", "三", "四", "五", "六", "七", "八"]

    def h(title: str) -> str:
        counter[0] += 1
        return f"## {numerals[counter[0] - 1]}、{title}"

    if sch:
        L += [h(f"方案与改动（{rec['scheme']}：{sch.get('title', '')}）"), ""]
        if sch.get("why"):
            L.append(f"- **动机**：{sch['why']}")
        if sch.get("hypothesis"):
            L.append(f"- **假设**：{sch['hypothesis']}")
        if sch.get("change"):
            L.append("- **改动**：")
            L += [f"  - {c}" for c in sch["change"]]
        if sch.get("expected"):
            L.append(f"- **预期增益**：{json.dumps(sch['expected'], ensure_ascii=False)}")
        if sch.get("risk"):
            L.append(f"- **风险**：{sch['risk']}")
        L.append("")

    L += [h("指标结果"), "",
          "| 指标 | 本次 | 基线 | 差值(pt) | 阈值 | 达标 |", "|---|---|---|---|---|---|"]
    for key, name in COLS + EXTRA_COLS:
        v, b = rec["metrics"].get(key), base.get(key)
        if v is None and b is None:
            continue
        if is_base:
            delta = "（基线）"
        elif isinstance(v, (int, float)) and isinstance(b, (int, float)):
            delta = f"{100 * (v - b):+.1f}"
        else:
            delta = "—"
        th = THRESHOLDS.get(key)
        th_s = f"{th:.2f}" if th is not None else "—"
        ok = "—"
        if th is not None and isinstance(v, (int, float)):
            ok = "✅" if v >= th else "❌"
        L.append(f"| {name} | {fmt(v)} | {fmt(b)} | {delta} | {th_s} | {ok} |")
    L += ["", "> 阈值口径见各判分器 `THRESHOLDS`；`tool.C` 为安全底线（必须 100%）。", ""]

    digest = error_digest(rec)
    if digest:
        L += [h("错误模式（自动摘录）"), ""] + digest

    if rec.get("n"):
        L += [h("子集明细"), "", "| 子集 | 样本数 | 错误行 | 耗时(s) | run_id |", "|---|---|---|---|---|"]
        for subset, meta in rec["n"].items():
            n_v = meta.get("n")
            e_v = meta.get("errors")
            w_v = meta.get("wall_s")
            L.append(f"| {subset} | {n_v if n_v is not None else '—'} | "
                     f"{e_v if e_v is not None else '—'} | "
                     f"{w_v if w_v is not None else '—'} | `{rec['runs'].get(subset, '—')}` |")
        L.append("")

    L += [h("判定与结论"), "",
          f"- **判定**：`{rec.get('verdict', 'pending')}`",
          f"- **备注**：{rec.get('notes') or '（无）'}",
          "", "> 判定规则：adopt = 目标指标提升 ≥3pt 且其余回退 <1pt；iterating = 有提升未达阈；"
          "reject = 无提升或明显副作用（方案保留在 schemes.yaml，不删除）。", ""]

    L += [h("复现命令"), "", "```bash"]
    if rec.get("endpoint"):
        subsets = ",".join(rec["runs"].keys()) or "intent"
        L.append(f"python experiments/run_experiment.py --scheme {rec['scheme']} "
                 f"--label \"{rec['label']}\" --endpoint {rec['endpoint']} "
                 f"--subsets {subsets} --env {rec['env']}"
                 + (f" --limit {rec['limit']}" if rec.get("limit") else ""))
    else:
        runs = " ".join(f"{k}={v}" for k, v in rec["runs"].items())
        L.append(f"python experiments/run_experiment.py --scheme {rec['scheme']} "
                 f"--label \"{rec['label']}\" --env {rec['env']} --from-run {runs}")
    L += ["```", ""]

    L += [h("原始数据位置"), ""]
    for subset, run_id in rec.get("runs", {}).items():
        L.append(f"- {subset}：`JSNC202611/edge-harness-poc/eval/reports/{run_id}/`"
                 f"（`raw.jsonl` 逐条输出、`report.json` 判分结果）")
    for art in rec.get("artifacts") or []:
        L.append(f"- 产物：`{art}`")
    L.append("")

    p = REPORT_DIR / doc_name(idx, rec)
    p.write_text("\n".join(L), encoding="utf-8")
    return p


def write_index(records: list[dict]) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    L = ["# 评测记录索引", "",
         "> 由 `python experiments/run_experiment.py` 自动维护。编号接续根目录的 "
         "`评测-01`（PC 首轮叙事报告）与 `评测-02`（真机对比叙事报告）；"
         "基线记录不重复生成文档，直接链接原报告，新实验自 03 起编号。", "",
         "| 编号 | 日期 | 环境 | 方案 | 说明 | intent F1 | OOS | faq命中 | tool A | mask P/R | 判定 | 文档 |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for i, r in enumerate(records, 1):
        m = r["metrics"]
        if r["scheme"] == "baseline" and i in ROOT_DOCS:
            link = f"[评测-{i:02d}]({ROOT_DOCS[i]})"
        else:
            link = f"[评测-{i:02d}]({doc_name(i, r)})"
        L.append("| {:02d} | {} | {} | {} | {} | {} | {} | {} | {} | {}/{} | {} | {} |".format(
            i, r["ts"][:10], r["env"], r["scheme"], r["label"],
            fmt(m.get("intent.macro_f1")), fmt(m.get("intent.oos_reject")),
            fmt(m.get("faq.info_point_hit")), fmt(m.get("tool.A")),
            fmt(m.get("mask.precision")), fmt(m.get("mask.recall")),
            r.get("verdict", "pending"), link))
    L += ["", "---", "",
          "## 说明", "",
          "- `experiments/results.jsonl`：机器可读台账（append-only，含 commit/endpoint/run_id）；",
          "- `experiments/results.md`：跨环境汇总表；",
          "- 每份文档的第六节给出 `eval/reports/<run_id>/` 原始输出位置（逐条模型回复可追溯）。", ""]
    (REPORT_DIR / "README.md").write_text("\n".join(L), encoding="utf-8")


def regen_docs() -> None:
    records = load_records()
    schemes = load_schemes()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    # 清理旧的自动文档（避免改名/重编号残留）
    for old in REPORT_DIR.glob("评测-*.md"):
        old.unlink()
    n_doc = 0
    for i, rec in enumerate(records, 1):
        if rec["scheme"] == "baseline" and i in ROOT_DOCS:
            continue
        write_doc(i, rec, records, schemes)
        n_doc += 1
    write_index(records)
    print(f"已生成 {n_doc} 份文档 + 索引 -> {REPORT_DIR}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scheme", help="方案ID（schemes.yaml）")
    ap.add_argument("--label", help="本次实验的一句话说明")
    ap.add_argument("--endpoint", help="OpenAI 兼容端点（真机填设备 IP）")
    ap.add_argument("--subsets", help="逗号分隔：intent,faq,tool,mask")
    ap.add_argument("--from-run", nargs="*", default=None, help="登记已有结果：subset=run_id ...")
    ap.add_argument("--env", default="pc", choices=["pc", "device", "pc4b"], help="pc=1.7B / pc4b=4B-2507 / device=真机")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--model-label", default="qwen3-1.7b-q8_0-llamacpp-b11669")
    ap.add_argument("--verdict", default="pending",
                    choices=["pending", "adopt", "iterating", "reject"])
    ap.add_argument("--notes", default="")
    ap.add_argument("--show", action="store_true", help="仅打印汇总表")
    ap.add_argument("--regen", action="store_true", help="仅重新生成详细文档与索引")
    ap.add_argument("--metrics-file", help="离线模拟指标 JSON（含 metrics 字段或直接 {metric:value}）")
    ap.add_argument("--attach", nargs="*", default=[], help="关联产物（如扫描表/图表），随文档归档")
    a = ap.parse_args()

    if a.show:
        print(render_md(load_records()))
        return
    if a.regen:
        regen_docs()
        return
    if not (a.scheme and a.label):
        ap.error("需要 --scheme 与 --label（或 --regen / --show）")

    metrics, runs, subset_meta, judges = {}, {}, {}, {}
    if a.from_run:
        for subset, run_id in dict(x.split("=", 1) for x in a.from_run).items():
            rep = json.loads((REPORTS / run_id / "report.json").read_text(encoding="utf-8"))
            metrics |= flatten(subset, rep)
            runs[subset] = run_id
            if rep.get("judge_version"):
                judges[subset] = rep["judge_version"]
            n_rows = rep.get("n")
            if n_rows is None and subset == "tool":       # tool_judge 无顶层 n，按 A~D 求和
                n_rows = sum((rep.get(t) or {}).get("n", 0) for t in "ABCD") or None
            subset_meta[subset] = {"n": n_rows, "errors": None, "wall_s": None}
    else:
        if not (a.endpoint and a.subsets):
            ap.error("需要 --endpoint 与 --subsets（或 --from-run / --show / --regen）")
        for subset in [s.strip() for s in a.subsets.split(",") if s.strip()]:
            run_id, n, n_err, wall = run_eval(subset, a.endpoint, a.limit)
            rep = run_judge(subset, run_id)
            metrics |= flatten(subset, rep)
            runs[subset] = run_id
            if rep.get("judge_version"):
                judges[subset] = rep["judge_version"]
            subset_meta[subset] = {"n": n, "errors": n_err, "wall_s": round(wall, 1)}
            print(f"[{subset}] n={n} errors={n_err} wall={wall:.0f}s -> {run_id}")

    if a.metrics_file:
        mf = json.loads(Path(a.metrics_file).read_text(encoding="utf-8"))
        metrics |= mf.get("metrics", mf)
        print(f"已合并离线模拟指标: {a.metrics_file}")

    commit, dirty = git_info()
    rec = {
        "id": f"{dt.datetime.now():%Y%m%d_%H%M%S}_{a.scheme}",
        "scheme": a.scheme, "label": a.label, "env": a.env,
        "ts": dt.datetime.now().isoformat(timespec="seconds"),
        "model": a.model_label, "endpoint": a.endpoint, "limit": a.limit,
        "commit": commit, "dirty_files": dirty,
        "runs": runs, "n": subset_meta, "metrics": metrics,
        "judges": judges, "artifacts": a.attach,
        "verdict": a.verdict, "notes": a.notes,
    }
    with RESULTS_JSONL.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    records = load_records()
    RESULTS_MD.write_text(render_md(records), encoding="utf-8")
    regen_docs()

    base = baseline_metrics(records, a.env)
    print(f"\n已登记实验 {rec['id']}（commit {commit or '?'}, dirty={dirty}）")
    for key, name in COLS:
        v, b = metrics.get(key), base.get(key)
        if v is not None:
            d = f"  (Δ {100 * (v - b):+.1f}pt vs 基线)" if (b is not None and a.scheme != "baseline") else ""
            print(f"  {name:10s} {fmt(v)}{d}")
    print(f"\n详细文档：{REPORT_DIR / doc_name(len(records), rec)}")


if __name__ == "__main__":
    main()
