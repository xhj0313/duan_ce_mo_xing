"""#15 替代口径：PC 侧 CPU 占用率（不是手机电池功耗）。

Windows 无标准 API 取 CPU 实际瓦数（需硬件电表），这里采 llama-server 进程的
CPU 使用率与工作集作为"算力消耗代理指标"。**不可换算为手机 mAh 或续航。**

产物：11-功耗/power_proxy.csv
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import subprocess
import time
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parent / "11-功耗"
LLAMA = Path("C:/Users/34919/llama.cpp")
PORT = 8080
EP = f"http://127.0.0.1:{PORT}/v1"
MODELS = [
    ("Qwen3-1.7B-Q8_0.gguf", "qwen3-1.7b-q8"),
    ("Qwen3-4B-Instruct-2507-Q4_K_M.gguf", "qwen3-4b-q4"),
]


def kill_all() -> None:
    subprocess.run(["taskkill", "/F", "/IM", "llama-server.exe"], capture_output=True)
    time.sleep(1)


def wait_health(timeout_s: int = 120) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=1) as r:
                if b'"ok"' in r.read():
                    return True
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.1)
    return False


def ask(text: str) -> None:
    body = json.dumps({"model": "m", "messages": [{"role": "user", "content": text}],
                       "temperature": 0, "max_tokens": 96}).encode()
    req = urllib.request.Request(f"{EP}/chat/completions", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        r.read()


def cpu_percent(proc_id: int) -> float:
    ps = f"(Get-Process -Id {proc_id} -ErrorAction SilentlyContinue).CPU"
    out = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                         capture_output=True, text=True).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return 0.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, choices=[m[1] for m in MODELS])
    ap.add_argument("--seconds", type=int, default=60)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    mf = dict((tag, f) for f, tag in MODELS)[a.model]
    kill_all()
    proc = subprocess.Popen(
        [str(LLAMA / "llama-server.exe"), "-m", f"models/{mf}", "-c", "8192",
         "--port", str(PORT), "--host", "127.0.0.1", "-fa", "on",
         "--reasoning", "off", "--parallel", "1"],
        cwd=str(LLAMA), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not wait_health():
        print("启动失败"); return

    cpu0 = cpu_percent(proc.pid)
    t0, n = time.time(), 0
    while time.time() - t0 < a.seconds:
        ask("查一下我的余额" if n % 2 else "跨行转账收手续费吗")
        n += 1
    elapsed = time.time() - t0
    cpu1 = cpu_percent(proc.pid)
    cores = subprocess.run(["powershell", "-NoProfile", "-Command",
                            "(Get-CimInstance Win32_Processor).NumberOfLogicalProcessors"],
                           capture_output=True, text=True).stdout.strip()
    avg_pct = (cpu1 - cpu0) / elapsed / max(int(cores or 1), 1) * 100
    kill_all()

    row = {"model": a.model, "seconds": round(elapsed, 1), "requests": n,
           "cpu_seconds": round(cpu1 - cpu0, 1), "logical_cores": cores,
           "avg_cpu_pct_per_core": round(avg_pct, 1),
           "note": "PC 进程 CPU 时间，非手机电池 mAh；不可换算续航"}
    p = OUT / "power_proxy.csv"
    with p.open("a", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(row))
        if f.tell() == 0:
            w.writeheader()
        w.writerow(row)
    (OUT / f"power_proxy_{a.model}.json").write_text(
        json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(row, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
