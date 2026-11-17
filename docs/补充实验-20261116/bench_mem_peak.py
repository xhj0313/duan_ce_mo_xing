"""#9 内存峰值升级：发长 prompt 撑满 8K KV，测进程峰值工作集。

替代口径：PC Windows 工作集，非真机 dumpsys；但比之前的 21 条短请求更接近真实上限。

产物：03-内存采样/rss_peak_full.csv
"""

from __future__ import annotations

import csv
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parent / "03-内存采样"
LLAMA = Path("C:/Users/34919/llama.cpp")
PORT = 8080
EP = f"http://127.0.0.1:{PORT}/v1"
MODELS = [
    ("Qwen3-1.7B-Q8_0.gguf", "qwen3-1.7b-q8"),
    ("Qwen3-1.7B-Q4_K_M.gguf", "qwen3-1.7b-q4"),
    ("Qwen3-4B-Instruct-2507-Q4_K_M.gguf", "qwen3-4b-q4"),
    ("Qwen3-4B-Instruct-2507-Q8_0.gguf", "qwen3-4b-q8"),
]
LONG_TEXT = ("这是一段用于填充模型上下文的测试文本，包含普通中文语句和银行常见咨询表达，"
             "目的是让本次请求尽可能占满 8192 token 的上下文窗口，以便观测推理进程的内存峰值。"
             "跨行转账手续费、账户余额查询、挂失办理流程、网点营业时间等信息均为演示用例。") * 55


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


def mem() -> tuple[int, int]:
    ps = ("$p = Get-Process llama-server -ErrorAction SilentlyContinue; "
          "if ($p) { '{0} {1}' -f [int]($p.WorkingSet64/1MB), [int]($p.PeakWorkingSet64/1MB) }")
    out = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                         capture_output=True, text=True).stdout.strip().split()
    return (int(out[0]), int(out[1])) if len(out) == 2 else (0, 0)


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None)
    a = ap.parse_args()

    rows = []
    for mf, tag in MODELS:
        if a.only and a.only != tag:
            continue
        kill_all()
        proc = subprocess.Popen(
            [str(LLAMA / "llama-server.exe"), "-m", f"models/{mf}", "-c", "8192",
             "--port", str(PORT), "--host", "127.0.0.1", "-fa", "on",
             "--reasoning", "off", "--parallel", "1"],
            cwd=str(LLAMA), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if not wait_health():
            print(f"{tag} 启动超时"); continue
        base = mem()
        body = json.dumps({"model": "m", "messages": [{"role": "user", "content": LONG_TEXT}],
                           "temperature": 0, "max_tokens": 32}).encode()
        req = urllib.request.Request(f"{EP}/chat/completions", data=body,
                                     headers={"Content-Type": "application/json"})
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                ans = json.loads(r.read())
            ntok = (ans.get("timings") or {}).get("prompt_n")
        except Exception as e:  # noqa: BLE001
            ntok, e = None, str(e)[:60]
            print(f"{tag} 长请求失败: {e}")
        secs = round(time.time() - t0, 1)
        peak = mem()
        rows.append({"model": tag, "base_ws_mb": base[0], "peak_ws_mb": peak[1],
                     "prompt_tokens": ntok, "prefill_s": secs,
                     "note": "8K 上限长 prompt；PC 工作集，非真机 dumpsys"})
        print(f"  {tag}: prompt={ntok} tok, {secs}s, base={base[0]}MB peak={peak[1]}MB")

    kill_all()
    p = OUT / "rss_peak_full.csv"
    old = []
    if p.exists():
        with p.open(encoding="utf-8-sig") as f:
            old = [r for r in csv.DictReader(f) if r["model"] not in {x["model"] for x in rows}]
    with p.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["model", "base_ws_mb", "peak_ws_mb",
                                          "prompt_tokens", "prefill_s", "note"])
        w.writeheader(); w.writerows(old + rows)
    print(f"写出 {p}")


if __name__ == "__main__":
    main()
