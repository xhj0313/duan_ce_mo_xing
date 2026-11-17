"""汇总真机逐请求性能（#1 的核心数据）。

从 device-1.7b-q8 的四个 run 提取 calls，输出：
  14-真机/<IP>/per_call.csv     逐次调用
  14-真机/<IP>/summary.csv      子集聚合
  14-真机/<IP>/device_vs_pc.csv 真机 vs PC（同模型 Q8）
"""

from __future__ import annotations

import csv
import json
import statistics as st
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1] / "JSNC202611" / "edge-harness-poc"
IP = "192.168.100.185"
OUT = Path(__file__).resolve().parent / "14-真机" / IP
SUBSETS = ["intent", "faq", "mask", "tool"]

# PC 同模型基线（本轮 11-16 实测，见 01-性能与timings/summary.csv）
PC_BASE = {
    "intent": {"acc": 0.8807, "f1": 0.8657, "decode": 14.9, "wall": 1452},
    "faq": {"hit": 0.5962, "decode": 18.1, "wall": 1407},
    "mask": {"p": 0.9610, "r": 0.9610, "decode": 18.4, "wall": 4829},
    "tool": {"a": 1.0, "b": 0.875, "decode": 18.4, "wall": 1728},
}


def run_dir(subset: str) -> Path | None:
    ds = sorted(HARNESS.glob(f"eval/reports/*device-1.7b-q8_{subset}_*"),
                key=lambda p: p.stat().st_mtime, reverse=True)
    return ds[0] if ds else None


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    all_rows, summ = [], []
    for s in SUBSETS:
        d = run_dir(s)
        if not d:
            continue
        rows = [json.loads(l) for l in (d / "raw.jsonl").open(encoding="utf-8") if l.strip()]
        calls = [c for r in rows for c in (r.get("calls") or [])]
        for c in calls:
            all_rows.append({"subset": s, "run": d.name, **c})
        cold = [c for c in calls if (c.get("prompt_n") or 0) > 1000]
        warm = [c for c in calls if (c.get("prompt_n") or 0) <= 1000]
        dec = [c["predicted_per_second"] for c in warm if c.get("predicted_per_second")]
        wall = [c["wall_ms"] for c in warm if c.get("wall_ms")]
        summ.append({
            "subset": s, "n_rows": len(rows), "n_calls": len(calls),
            "decode_tps_median": round(st.median(dec), 2) if dec else None,
            "wall_ms_median": round(st.median(wall)) if wall else None,
            "wall_ms_p90": round(sorted(wall)[int(len(wall) * 0.9) - 1]) if wall else None,
            "cold_prefill_ms": round(cold[0]["prompt_ms"]) if cold else None,
            "cold_prefill_tps": round(cold[0]["prompt_per_second"], 1) if cold else None,
        })

    if all_rows:
        cols = ["subset", "run", "wall_ms", "prompt_n", "prompt_ms", "prompt_per_second",
                "predicted_n", "predicted_ms", "predicted_per_second"]
        with (OUT / "per_call.csv").open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            w.writerows(all_rows)
    if summ:
        with (OUT / "summary.csv").open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(summ[0]))
            w.writeheader()
            w.writerows(summ)

    # 真机 vs PC
    cmp_rows = []
    for r in summ:
        pc = PC_BASE.get(r["subset"], {})
        cmp_rows.append({
            "subset": r["subset"],
            "device_decode_tps": r["decode_tps_median"],
            "pc_decode_tps": pc.get("decode"),
            "ratio": round(r["decode_tps_median"] / pc["decode"], 2)
            if r["decode_tps_median"] and pc.get("decode") else None,
            "device_wall_ms": r["wall_ms_median"],
            "pc_wall_ms": pc.get("wall"),
        })
    with (OUT / "device_vs_pc.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(cmp_rows[0]))
        w.writeheader()
        w.writerows(cmp_rows)

    (OUT / "device_meta.json").write_text(json.dumps({
        "device": "一加 Ace 2 (PHK110, Snapdragon 8+ Gen1, 16GB, Android 16)",
        "model": "Qwen3-1.7B-Q8_0", "n_ctx": 8192, "total_slots": 1,
        "threads": 6, "fa": "on", "endpoint": f"http://{IP}:8081/v1",
        "note": "--parallel 1 硬约束已满足；中途两次因 Android 回收进程中断，已用 seq 续跑补齐",
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=== 子集聚合 ===")
    for r in summ:
        print(f"  {r['subset']:8s} decode {r['decode_tps_median']} tok/s | wall {r['wall_ms_median']} ms | cold {r['cold_prefill_ms']} ms")
    print("=== 真机 vs PC ===")
    for r in cmp_rows:
        print(f"  {r['subset']:8s} {r['device_decode_tps']} vs {r['pc_decode_tps']} tok/s (×{r['ratio']})")


if __name__ == "__main__":
    main()
