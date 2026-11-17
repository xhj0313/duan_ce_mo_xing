"""冷/热启动测量：每模型连续启动 5 次，记录 启动→/health 就绪 的耗时。

Windows 下无法真正清空文件页缓存，"冷"只能近似为本进程首次启动；
第 2 次起为热启动（页缓存命中）。报告里按 cold_1 / warm_2..5 区分。

产物：04-冷启动/cold_warm.csv
"""

from __future__ import annotations

import csv
import json
import subprocess
import time
import urllib.request
from pathlib import Path

LLAMA = Path("C:/Users/34919/llama.cpp")
OUT = Path(__file__).resolve().parent / "04-冷启动"
PORT = 8080
HEALTH = f"http://127.0.0.1:{PORT}/health"

MODELS = [
    ("Qwen3-1.7B-Q8_0.gguf", "qwen3-1.7b-q8"),
    ("Qwen3-1.7B-Q4_K_M.gguf", "qwen3-1.7b-q4"),
    ("Qwen3-4B-Instruct-2507-Q4_K_M.gguf", "qwen3-4b-q4"),
    ("Qwen3-4B-Instruct-2507-Q8_0.gguf", "qwen3-4b-q8"),
]


def kill_all() -> None:
    subprocess.run(["taskkill", "/F", "/IM", "llama-server.exe"],
                   capture_output=True, shell=False)
    time.sleep(1.0)


def health_ok(timeout: float = 0.6) -> bool:
    try:
        with urllib.request.urlopen(HEALTH, timeout=timeout) as r:
            return b'"ok"' in r.read()
    except Exception:  # noqa: BLE001
        return False


def one_round(model_file: str) -> float | None:
    proc = subprocess.Popen(
        [str(LLAMA / "llama-server.exe"), "-m", f"models/{model_file}",
         "-c", "8192", "--port", str(PORT), "--host", "127.0.0.1",
         "-fa", "on", "--reasoning", "off", "--parallel", "1"],
        cwd=str(LLAMA), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    t0 = time.perf_counter()
    for _ in range(1200):                    # 最多等 120 秒
        if health_ok():
            return time.perf_counter() - t0
        if proc.poll() is not None:          # 进程已退出（端口占用/权限等）
            return None
        time.sleep(0.05)
    return None


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / "cold_warm.csv"
    rows = []
    for mf, tag in MODELS:
        for rnd in range(1, 6):
            kill_all()
            secs = one_round(mf)
            kind = "cold" if rnd == 1 else "warm"
            if secs is None:
                print(f"  {tag} round{rnd} 启动失败")
                continue
            rows.append({"model": tag, "round": rnd, "kind": kind, "seconds": round(secs, 2)})
            print(f"  {tag} round{rnd} {kind} {secs:.2f}s")
    kill_all()

    with out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["model", "round", "kind", "seconds"])
        w.writeheader()
        w.writerows(rows)
    print(f"写出 {out}（{len(rows)} 次启动）")


if __name__ == "__main__":
    main()
