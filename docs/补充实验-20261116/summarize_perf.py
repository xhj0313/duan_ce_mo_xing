"""汇总逐请求性能：从 raw.jsonl 的 calls 提取 token 级指标。

产出（01-性能与timings/、02-量化速度对照/）：
  per_call.csv     每次模型调用一行（模型/子集/题号/prompt/生成/wall/速率）
  summary.csv      模型 × 子集 的聚合（中位/均值 tok/s、TTFT、wall）
  quant_speed.csv  同系列 Q4 vs Q8 的速度对照

口径说明（写进报告时必须带上）：
  - prompt_n 为本次实际 prefill 的 token 数；命中 prompt cache 时远小于完整 prompt；
  - 因此 "TTFT" 用 prompt_ms 表示（服务端 prefill 耗时），不等于首条冷启动的完整 prefill；
  - 首个请求（每模型首条）为冷 prefill，另行标注。
"""

from __future__ import annotations

import csv
import glob
import json
import statistics as st
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1] / "JSNC202611" / "edge-harness-poc"
OUT1 = Path(__file__).resolve().parent / "01-性能与timings"
OUT2 = Path(__file__).resolve().parent / "02-量化速度对照"

MODEL_ORDER = ["qwen3-1.7b-q8", "qwen3-1.7b-q4", "qwen3-4b-q4", "qwen3-4b-q8"]
SUBSETS = ["intent", "faq", "mask", "tool"]


def collect() -> list[dict]:
    rows = []
    for d in sorted((HARNESS / "eval" / "reports").glob("20261116_*")):
        meta_p = d / "run.json"
        raw_p = d / "raw.jsonl"
        if not meta_p.exists() or not raw_p.exists():
            continue
        meta = json.loads(meta_p.read_text(encoding="utf-8"))
        model = meta.get("model")
        if model not in MODEL_ORDER:
            continue
        subset = meta.get("subset")
        first = True
        for line in raw_p.open(encoding="utf-8"):
            if not line.strip():
                continue
            rec = json.loads(line)
            for c in rec.get("calls") or []:
                rows.append({
                    "model": model, "subset": subset, "id": rec["id"],
                    "cold": first,
                    "prompt_n": c.get("prompt_n"),
                    "prompt_ms": c.get("prompt_ms"),
                    "predicted_n": c.get("predicted_n"),
                    "predicted_ms": c.get("predicted_ms"),
                    "wall_ms": c.get("wall_ms"),
                    "prefill_tps": round(c["prompt_per_second"], 1) if c.get("prompt_per_second") else None,
                    "decode_tps": round(c["predicted_per_second"], 1) if c.get("predicted_per_second") else None,
                })
                first = False
    return rows


def write_per_call(rows: list[dict]) -> None:
    cols = ["model", "subset", "id", "cold", "prompt_n", "prompt_ms", "prefill_tps",
            "predicted_n", "predicted_ms", "decode_tps", "wall_ms"]
    with (OUT1 / "per_call.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in cols})


def agg(rows: list[dict]) -> list[dict]:
    out = []
    for m in MODEL_ORDER:
        for s in SUBSETS:
            sub = [r for r in rows if r["model"] == m and r["subset"] == s and not r["cold"]]
            if not sub:
                continue
            dec = [r["decode_tps"] for r in sub if r["decode_tps"]]
            pre = [r["prefill_tps"] for r in sub if r["prefill_tps"]]
            wall = [r["wall_ms"] for r in sub if r["wall_ms"]]
            out.append({
                "model": m, "subset": s, "n_calls": len(sub),
                "decode_tps_median": round(st.median(dec), 1) if dec else None,
                "decode_tps_mean": round(st.mean(dec), 1) if dec else None,
                "prefill_tps_median": round(st.median(pre), 1) if pre else None,
                "wall_ms_median": round(st.median(wall), 0) if wall else None,
                "wall_ms_p90": round(sorted(wall)[int(len(wall) * 0.9) - 1], 0) if wall else None,
                "cold_prompt_ms": next(
                    (r["prompt_ms"] for r in rows if r["model"] == m and r["subset"] == s and r["cold"]), None),
            })
    return out


def write_summary(summary: list[dict]) -> None:
    with (OUT1 / "summary.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(summary[0].keys()))
        w.writeheader()
        w.writerows(summary)


def write_quant(summary: list[dict]) -> None:
    """同系列 Q4 vs Q8：以 intent 子集为主（同 prompt 结构、样本量最大）。"""
    rows = []
    for series, q4, q8 in [("1.7B", "qwen3-1.7b-q4", "qwen3-1.7b-q8"),
                           ("4B", "qwen3-4b-q4", "qwen3-4b-q8")]:
        for s in SUBSETS:
            a = next((x for x in summary if x["model"] == q4 and x["subset"] == s), None)
            b = next((x for x in summary if x["model"] == q8 and x["subset"] == s), None)
            if not a or not b:
                continue
            d4, d8 = a["decode_tps_median"], b["decode_tps_median"]
            rows.append({
                "series": series, "subset": s,
                "q4_decode_tps": d4, "q8_decode_tps": d8,
                "speedup": round(d4 / d8, 2) if d4 and d8 else None,
                "q4_prefill_tps": a["prefill_tps_median"], "q8_prefill_tps": b["prefill_tps_median"],
                "q4_wall_ms": a["wall_ms_median"], "q8_wall_ms": b["wall_ms_median"],
            })
    if rows:
        with (OUT2 / "quant_speed.csv").open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)


def main() -> None:
    OUT1.mkdir(parents=True, exist_ok=True)
    OUT2.mkdir(parents=True, exist_ok=True)
    rows = collect()
    if not rows:
        print("未找到 20261116 的跑测数据")
        return
    write_per_call(rows)
    summary = agg(rows)
    write_summary(summary)
    write_quant(summary)
    print(f"per_call {len(rows)} 行 / summary {len(summary)} 行 / quant_speed 已生成")


if __name__ == "__main__":
    main()
