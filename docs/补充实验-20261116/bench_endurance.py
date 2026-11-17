"""#11 耐久/吞吐衰减实验（PC 替代口径）。

20 轮 × 每轮若干条请求，统计每轮解码 tok/s 与 wall，看是否随轮次衰减。
**PC 无"温升"传感器语义，本实验测的是吞吐衰减，不等于真机温升降频。**

产物：09-耐久/endurance_<model>.csv、endurance_<model>_report.json
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import statistics as st
import subprocess
import time
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parent / "09-耐久"
LLAMA = Path("C:/Users/34919/llama.cpp")
PORT = 8080
EP = f"http://127.0.0.1:{PORT}/v1"
FILES = {
    "qwen3-1.7b-q8": "Qwen3-1.7B-Q8_0.gguf",
    "qwen3-4b-q4": "Qwen3-4B-Instruct-2507-Q4_K_M.gguf",
}
PROMPTS = ["查一下我的余额", "跨行转账收手续费吗", "我要挂失银行卡",
           "密码忘了怎么办", "附近网点在哪里", "转账限额是多少",
           "查最近交易明细", "电子回单在哪开"]


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


def ask(text: str) -> dict | None:
    body = json.dumps({"model": "m", "messages": [{"role": "user", "content": text}],
                       "temperature": 0, "max_tokens": 64}).encode()
    req = urllib.request.Request(f"{EP}/chat/completions", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return (json.loads(r.read()).get("timings") or {})


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, choices=list(FILES))
    ap.add_argument("--rounds", type=int, default=20)
    ap.add_argument("--per-round", type=int, default=8)
    a = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    kill_all()
    proc = subprocess.Popen(
        [str(LLAMA / "llama-server.exe"), "-m", f"models/{FILES[a.model]}", "-c", "8192",
         "--port", str(PORT), "--host", "127.0.0.1", "-fa", "on",
         "--reasoning", "off", "--parallel", "1"],
        cwd=str(LLAMA), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not wait_health():
        print("服务启动失败"); return

    rows = []
    for rd in range(1, a.rounds + 1):
        tps, walls = [], []
        for j in range(a.per_round):
            try:
                tm = ask(PROMPTS[j % len(PROMPTS)])
                if tm and tm.get("predicted_per_second"):
                    tps.append(tm["predicted_per_second"])
                if tm and tm.get("predicted_ms"):
                    walls.append(tm["predicted_ms"])
            except Exception:  # noqa: BLE001
                pass
        rows.append({"round": rd, "n": len(tps),
                     "decode_tps": round(st.median(tps), 2) if tps else None,
                     "predicted_ms": round(st.median(walls), 1) if walls else None})
        if rd % 5 == 0 or rd == 1:
            print(f"  round {rd}: {rows[-1]['decode_tps']} tok/s", flush=True)

    kill_all()
    p = OUT / f"endurance_{a.model}.csv"
    with p.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["round", "n", "decode_tps", "predicted_ms"])
        w.writeheader(); w.writerows(rows)

    first = [r["decode_tps"] for r in rows[:3] if r["decode_tps"]]
    last = [r["decode_tps"] for r in rows[-3:] if r["decode_tps"]]
    f0, l0 = st.mean(first) if first else 0, st.mean(last) if last else 0
    rep = {
        "model": a.model, "rounds": a.rounds, "per_round": a.per_round,
        "created": dt.datetime.now().isoformat(timespec="seconds"),
        "first3_tps": round(f0, 2), "last3_tps": round(l0, 2),
        "decay_pct": round((1 - l0 / f0) * 100, 1) if f0 else None,
        "note": "PC 替代口径：测吞吐衰减，不等于真机温升降频；每轮请求数固定",
    }
    (OUT / f"endurance_{a.model}_report.json").write_text(
        json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(rep, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
