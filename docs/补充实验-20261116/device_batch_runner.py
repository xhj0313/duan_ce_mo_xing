"""真机分批续跑调度器：跑批 → 去重 → 统计 → 循环，直到子集完成或设备离线。

用法：python device_batch_runner.py 192.168.100.185 faq 91
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HARNESS = Path("D:/Users/34919/Desktop/武研/1-AI/2-技术内参/2026/20261022端侧部署/JSNC202611/edge-harness-poc")
PY = "C:/Users/34919/.workbuddy/binaries/python/envs/default/Scripts/python.exe"
IP = sys.argv[1] if len(sys.argv) > 1 else "192.168.100.185"
SUBSET = sys.argv[2] if len(sys.argv) > 2 else "faq"
TOTAL = int(sys.argv[3]) if len(sys.argv) > 3 else 91
BATCH = 30
EP = f"http://{IP}:8081/v1"


def alive() -> bool:
    try:
        with urllib.request.urlopen(f"http://{IP}:8081/health", timeout=4) as r:
            return b"ok" in r.read()
    except Exception:  # noqa: BLE001
        return False


def latest_run() -> Path | None:
    ds = sorted(HARNESS.glob(f"eval/reports/*device-1.7b-q8_{SUBSET}_*"),
                key=lambda p: p.stat().st_mtime, reverse=True)
    return ds[0] if ds else None


def dedup(p: Path) -> int:
    """按 seq 去重，优先保留无 error 的一条；返回有效条目数。"""
    if not p.exists():
        return 0
    rows = []
    for line in p.open(encoding="utf-8"):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    best: dict[int, dict] = {}
    for r in rows:
        s = r.get("seq")
        if s is None:
            continue
        cur = best.get(s)
        if cur is None:
            best[s] = r
        elif "__error__" in (cur.get("output") or {}) and "__error__" not in (r.get("output") or {}):
            best[s] = r
    keep = [best[s] for s in sorted(best)]
    with p.open("w", encoding="utf-8") as f:
        for r in keep:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return sum(1 for r in keep if "__error__" not in (r.get("output") or {}))


def main() -> None:
    run = latest_run()          # 已有则续跑，避免丢弃已完成数据
    if run:
        print(f"  续跑已有 run: {run.name}")
    rounds = 0
    while rounds < 12:
        rounds += 1
        if not alive():
            print("  设备离线，停止")
            break
        if run is None:
            print(f"  第{rounds}批：新建 run，跑 {BATCH} 条")
            subprocess.run(
                [PY, str(HARNESS / "eval/run_eval.py"), "--backend", "openai",
                 "--endpoint", EP, "--subset", SUBSET, "--model", "device-1.7b-q8",
                 "--device", "mid", "--limit", str(BATCH)],
                cwd=str(HARNESS), capture_output=True, timeout=900)
            run = latest_run()
        else:
            done = dedup(run / "raw.jsonl")
            print(f"  第{rounds}批：已有 {done}/{TOTAL}")
            if done >= TOTAL:
                break
            subprocess.run(
                [PY, str(HARNESS / "eval/run_eval.py"), "--backend", "openai",
                 "--endpoint", EP, "--subset", SUBSET, "--model", "device-1.7b-q8",
                 "--device", "mid", "--resume-run", run.name, "--limit", str(BATCH)],
                cwd=str(HARNESS), capture_output=True, timeout=900)
        if run:
            done = dedup(run / "raw.jsonl")
            print(f"    -> {done}/{TOTAL}")

    if run:
        done = dedup(run / "raw.jsonl")
        print(f"=== {SUBSET} 结束：{done}/{TOTAL} | run={run.name} ===")


if __name__ == "__main__":
    main()
