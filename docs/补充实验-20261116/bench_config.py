"""#3 替代口径：配置敏感性（多线程数 × 量化档）而非多机型。

PC 上无法造出第二台手机，改用不同线程数模拟"算力配置差异"，
与两个量化档交叉，看吞吐如何随配置变化。**不能外推为多机型实测。**

产物：10-配置对照/config_sweep.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import time
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parent / "10-配置对照"
LLAMA = Path("C:/Users/34919/llama.cpp")
PORT = 8080
EP = f"http://127.0.0.1:{PORT}/v1"
MODELS = [
    ("Qwen3-1.7B-Q8_0.gguf", "1.7B-Q8"),
    ("Qwen3-4B-Instruct-2507-Q4_K_M.gguf", "4B-Q4"),
]
THREADS = [2, 4, 8]
PROMPTS = ["查一下我的余额", "跨行转账收手续费吗", "我要挂失银行卡", "密码忘了怎么办"]


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


def ask(text: str) -> dict:
    body = json.dumps({"model": "m", "messages": [{"role": "user", "content": text}],
                       "temperature": 0, "max_tokens": 64}).encode()
    req = urllib.request.Request(f"{EP}/chat/completions", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read()).get("timings") or {}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only-model", default=None)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    rows = []
    for mf, label in MODELS:
        if a.only_model and a.only_model != label:
            continue
        for nt in THREADS:
            kill_all()
            proc = subprocess.Popen(
                [str(LLAMA / "llama-server.exe"), "-m", f"models/{mf}", "-c", "8192",
                 "--port", str(PORT), "--host", "127.0.0.1", "-fa", "on",
                 "--reasoning", "off", "--parallel", "1", "-t", str(nt)],
                cwd=str(LLAMA), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if not wait_health():
                print(f"{label} t={nt} 启动失败"); continue
            tps, walls = [], []
            for p in PROMPTS * 3:                 # 12 条取中位
                try:
                    tm = ask(p)
                    if tm.get("predicted_per_second"):
                        tps.append(tm["predicted_per_second"])
                    if tm.get("predicted_ms"):
                        walls.append(tm["predicted_ms"])
                except Exception:  # noqa: BLE001
                    pass
            import statistics as st
            rows.append({"model": label, "threads": nt, "n": len(tps),
                         "decode_tps": round(st.median(tps), 2) if tps else None,
                         "predicted_ms": round(st.median(walls), 1) if walls else None})
            print(f"  {label} t={nt}: {rows[-1]['decode_tps']} tok/s", flush=True)

    kill_all()
    p = OUT / "config_sweep.csv"
    with p.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["model", "threads", "n", "decode_tps", "predicted_ms"])
        w.writeheader(); w.writerows(rows)
    (OUT / "config_sweep.meta.json").write_text(json.dumps({
        "note": "PC 替代口径：线程数模拟算力配置，非真机多机型；线程数为 llama.cpp -t 参数",
        "limits": ["未测 8GB 中端机", "未测天玑平台", "不可宣称部署普适性"],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"写出 {p}")


if __name__ == "__main__":
    main()
