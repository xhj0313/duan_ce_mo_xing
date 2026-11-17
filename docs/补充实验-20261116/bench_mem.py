"""内存峰值测量：每模型启动 → 打 20 条混合请求 → 读工作集与峰值。

替代 run_all_models.sh 里的 PowerShell 记录（那边 `{0:N0}` 会输出千分位逗号，破坏 CSV）。

产物：03-内存采样/rss_peak.csv
  model,working_set_mb,peak_working_set_mb,note
"""

from __future__ import annotations

import csv
import json
import subprocess
import time
import urllib.request
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1] / "JSNC202611" / "edge-harness-poc"
LLAMA = Path("C:/Users/34919/llama.cpp")
OUT = Path(__file__).resolve().parent / "03-内存采样"
PORT = 8080
EP = f"http://127.0.0.1:{PORT}/v1"

MODELS = [
    ("Qwen3-1.7B-Q8_0.gguf", "qwen3-1.7b-q8"),
    ("Qwen3-1.7B-Q4_K_M.gguf", "qwen3-1.7b-q4"),
    ("Qwen3-4B-Instruct-2507-Q4_K_M.gguf", "qwen3-4b-q4"),
    ("Qwen3-4B-Instruct-2507-Q8_0.gguf", "qwen3-4b-q8"),
]


def kill_all() -> None:
    subprocess.run(["taskkill", "/F", "/IM", "llama-server.exe"], capture_output=True)
    time.sleep(1.0)


def health(timeout: float = 1.0) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=timeout) as r:
            return b'"ok"' in r.read()
    except Exception:  # noqa: BLE001
        return False


def chat(text: str, max_tokens: int = 200) -> None:
    body = json.dumps({"model": "m", "messages": [{"role": "user", "content": text}],
                       "temperature": 0, "max_tokens": max_tokens}).encode()
    req = urllib.request.Request(f"{EP}/chat/completions", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        r.read()


def mem_of() -> tuple[int, int] | None:
    """返回 (working_set_mb, peak_working_set_mb)，整数无千分位。"""
    ps = ("$p = Get-Process llama-server -ErrorAction SilentlyContinue; "
          "if ($p) { '{0} {1}' -f [int]($p.WorkingSet64/1MB), [int]($p.PeakWorkingSet64/1MB) }")
    out = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                         capture_output=True, text=True).stdout.strip()
    if not out:
        return None
    parts = out.split()
    if len(parts) != 2:
        return None
    return int(parts[0]), int(parts[1])


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None, help="只测指定模型标签，如 qwen3-4b-q4")
    a = ap.parse_args()
    models = [m for m in MODELS if a.only in (None, m[1])]

    OUT.mkdir(parents=True, exist_ok=True)
    # 混合负载：长上下文（文件操作）+ 中等（FAQ）+ 短（意图），把 KV cache 撑起来
    probes = [
        ("请把下面这句话里的身份证号和手机号脱敏后原样返回："
         "客户王小明，身份证 310104199001011234，手机 13812345678，卡号 6222021234567890123。", 200),
        ("跨行转账 1 万元以下收手续费吗？请说明依据。", 200),
        ("查一下我的余额", 80),
    ]

    rows = []
    for mf, tag in models:
        kill_all()
        proc = subprocess.Popen(
            [str(LLAMA / "llama-server.exe"), "-m", f"models/{mf}", "-c", "8192",
             "--port", str(PORT), "--host", "127.0.0.1", "-fa", "on",
             "--reasoning", "off", "--parallel", "1"],
            cwd=str(LLAMA), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(1200):
            if health():
                break
            if proc.poll() is not None:
                break
            time.sleep(0.05)

        base = mem_of()
        for text, mt in probes * 7:            # 21 次请求，覆盖三类负载
            try:
                chat(text, mt)
            except Exception:  # noqa: BLE001
                pass
        peak = mem_of()
        rows.append({
            "model": tag,
            "working_set_mb": peak[0] if peak else "",
            "peak_working_set_mb": peak[1] if peak else "",
            "note": f"加载后 {base[0] if base else '?'} MB；负载=21 次混合请求",
        })
        print(f"  {tag}: WS {peak[0] if peak else '?'} MB / Peak {peak[1] if peak else '?'} MB")

    kill_all()
    csv_path = OUT / "rss_peak.csv"
    fields = ["model", "working_set_mb", "peak_working_set_mb", "note"]
    old = []
    if csv_path.exists():
        with csv_path.open(encoding="utf-8-sig") as f:
            old = [r for r in csv.DictReader(f) if r["model"] not in {x["model"] for x in rows}]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(old + rows)
    print(f"写出 {csv_path}（本次 {len(rows)} 个模型）")


if __name__ == "__main__":
    main()
