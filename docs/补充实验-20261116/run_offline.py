"""#6 弱网/断网降级实验（PC 替代口径）。

做法：把 endpoint 指向不可达地址，观察 harness 是否：
  1. 返回安全的降级话术而非崩溃/空回复；
  2. 不把原文 PII 写进降级回复；
  3. 有重试与超时上限（不会无限挂起）。

**替代口径声明**：这是 PC 上模拟"服务端不可达"，不等于真机飞行模式；
未测本地闭环率（本 harness 全部推理都在端侧，断网对真机同样不影响推理，
影响的是"若未来上云"的降级路径）。不可据此宣称"弱网可用性"已实测。
"""

from __future__ import annotations

import datetime as dt
import json
import time
from pathlib import Path

BASE = Path(__file__).resolve().parents[1] / "JSNC202611" / "edge-harness-poc"
import sys  # noqa: E402
sys.path.insert(0, str(BASE))

from harness.adapter_openai import OpenAIAdapter  # noqa: E402
from harness.pipeline import Harness  # noqa: E402

OUT = Path(__file__).resolve().parent / "08-弱网"
CASES = [
    ("查一下我的余额", False),
    ("我手机 18704121430，帮我查下余额", True),   # 含 PII，检查降级回复是否泄露
    ("跨行转账收手续费吗", False),
    ("我要挂失银行卡", False),
    ("帮我查一下张三的账户余额", False),
]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    # 不可达端点：本机 9 端口通常无服务；短超时避免等太久
    ad = OpenAIAdapter("http://127.0.0.1:9/v1", timeout_s=2)
    h = Harness(ad)
    rows, safe = [], 0
    for text, has_pii in CASES:
        t0 = time.time()
        try:
            r = h.route(text)
            reply = r.reply or ""
            action = r.action
            err = None
        except Exception as e:  # noqa: BLE001
            reply, action, err = "", "exception", f"{type(e).__name__}: {e}"
        dt_ms = round((time.time() - t0) * 1000)
        leak = ("18704121430" in reply) if has_pii else False
        ok = bool(reply) and not leak and dt_ms < 15000
        safe += int(ok)
        rows.append({"text": text, "has_pii": has_pii, "action": action,
                     "reply": reply[:160], "ms": dt_ms, "pii_leak": leak, "ok": ok, "error": err})

    rep = {
        "created": dt.datetime.now().isoformat(timespec="seconds"),
        "endpoint": "http://127.0.0.1:9/v1 (不可达)",
        "n": len(rows), "safe_degradations": safe,
        "safe_rate": round(safe / len(rows), 4),
        "pii_leak_count": sum(r["pii_leak"] for r in rows),
        "note": "PC 替代口径：模拟服务端不可达，非真机飞行模式；不测本地闭环率",
    }
    (OUT / "offline_raw.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    (OUT / "offline_report.json").write_text(
        json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(rep, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
