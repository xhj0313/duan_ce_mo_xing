"""批量评测驱动：四子集 × 三后端（dry / mnn / openai）→ 落盘原始结果。

子集口径：
- intent：直接对原文做意图分类（干净归因；生产链路含脱敏，两者差异另行分析）
- mask  ：只跑脱敏能力，比对实体
- faq   ：全链路 route，考察知识卡应答
- tool  ：全链路 route，考察工具调用行为（含追问/拒调）

用法：
  python eval/run_eval.py --backend dry --subset intent
  python eval/run_eval.py --backend openai --endpoint http://127.0.0.1:8080/v1 --subset intent
  python eval/run_eval.py --backend mnn --model qwen3-1.7b --device <serial> --subset tool
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from harness.pipeline import Harness, extract_json          # noqa: E402

DATASETS = ROOT / "eval" / "datasets"
REPORTS = ROOT / "eval" / "reports"


def make_adapter(backend: str, model: str, device: str, endpoint: str):
    if backend == "dry":
        from harness.adapter_mnn import DryAdapter
        return DryAdapter()
    if backend == "openai":
        from harness.adapter_openai import OpenAIAdapter
        return OpenAIAdapter(endpoint)
    if backend == "mnn":
        from harness.adapter_mnn import MNNAdapter
        serial = None if device in ("mid", "default") else device
        return MNNAdapter(model, serial)
    raise ValueError(backend)


# ---------- 子集驱动 ----------

def drive_intent(h: Harness, rec: dict) -> dict:
    obj, trace = h.classify(rec["text"])
    return {"pred_intent": obj.get("intent"), "confidence": obj.get("confidence"),
            "slots": obj.get("slots"), "ok_json": bool(obj),
            "raw_keys": list(obj.keys()) if obj else []}


def drive_mask(h: Harness, rec: dict) -> dict:
    m = h.mask(rec["text"])
    return {"pred_text": m.masked_text, "action": m.action,
            "pred_entities": m.entities, "fallback": m.fallback_reason}


def drive_faq(h: Harness, rec: dict) -> dict:
    r = h.route(rec["text"])
    return {"action": r.action, "intent": r.intent, "reply": r.reply}


def drive_tool(h: Harness, rec: dict) -> dict:
    r = h.route(rec["text"])
    executed = [c for c in r.tool_calls if not (c.get("result") or {}).get("error")]
    return {"action": r.action, "intent": r.intent, "reply": r.reply,
            "tool_calls": r.tool_calls, "executed_any": bool(executed)}


DRIVERS = {"intent": drive_intent, "mask": drive_mask,
           "faq": drive_faq, "tool": drive_tool}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--subset", required=True, choices=list(DRIVERS))
    ap.add_argument("--backend", default="dry", choices=["dry", "mnn", "openai"])
    ap.add_argument("--model", default="qwen3-1.7b")
    ap.add_argument("--device", default="mid")
    ap.add_argument("--endpoint", default="http://127.0.0.1:8080/v1")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--include-dev", action="store_true")
    ap.add_argument("--dataset", default=None, help="覆盖默认数据集路径（用于增广集/变体集复测）")
    ap.add_argument("--offset", type=int, default=0, help="跳过前 N 条（断点续跑）")
    ap.add_argument("--resume-run", default=None, help="续跑到已有 run 目录（追加 raw.jsonl）")
    a = ap.parse_args()

    ds = Path(a.dataset) if a.dataset else DATASETS / f"{a.subset}.jsonl"
    if not ds.exists():
        sys.exit(f"dataset missing: {ds}（先运行 build/build_*.py）")

    adapter = make_adapter(a.backend, a.model, a.device, a.endpoint)
    h = Harness(adapter)

    if a.resume_run:
        run_id = a.resume_run
        out_dir = REPORTS / run_id
        if not out_dir.exists():
            sys.exit(f"续跑目标不存在: {out_dir}")
    else:
        ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        run_id = f"{ts}_{a.model}_{a.subset}_{a.device}_{a.backend}"
        out_dir = REPORTS / run_id
        out_dir.mkdir(parents=True, exist_ok=True)

    n, n_err = 0, 0
    skipped = 0
    done_seq: set[int] = set()
    if a.resume_run and (out_dir / "raw.jsonl").exists():
        for line in (out_dir / "raw.jsonl").open(encoding="utf-8"):
            if not line.strip():
                continue
            try:
                rr = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "__error__" not in (rr.get("output") or {}) and rr.get("seq") is not None:
                done_seq.add(rr["seq"])
    mode = "a" if a.resume_run else "w"
    with ds.open(encoding="utf-8") as f, (out_dir / "raw.jsonl").open(mode, encoding="utf-8") as out:
        seq = -1
        for line in f:
            if a.limit and n >= a.limit:
                break
            rec = json.loads(line)
            if rec.get("split") == "dev" and not a.include_dev:
                continue
            seq += 1
            if skipped < a.offset:
                skipped += 1
                continue
            if seq in done_seq:
                continue
            n_calls0 = len(getattr(getattr(h, "adapter", None), "calls", []) or [])
            try:
                output = DRIVERS[a.subset](h, rec)
            except Exception as e:                    # 单条异常不中断整批
                # 端侧 503/超时多为"并发槽被占"或瞬时抖动，重试 2 次再判失败
                output, ok = None, False
                for attempt in range(2):
                    time.sleep(3 * (attempt + 1))
                    try:
                        output = DRIVERS[a.subset](h, rec)
                        ok = True
                        break
                    except Exception as e2:  # noqa: BLE001
                        e = e2
                if not ok:
                    n_err += 1
                    output = {"__error__": f"{type(e).__name__}: {e}"}
            all_calls = getattr(getattr(h, "adapter", None), "calls", []) or []
            out.write(json.dumps({"seq": seq, "id": rec["id"], "text": rec["text"],
                                  "meta": rec.get("meta", {}),
                                  "output": output,
                                  "calls": all_calls[n_calls0:]}, ensure_ascii=False) + "\n")
            n += 1
            if n % 50 == 0:
                print(f"... {n}", file=sys.stderr)

    prev_n = 0
    if a.resume_run:
        try:
            prev_n = json.loads((out_dir / "run.json").read_text(encoding="utf-8")).get("n", 0)
        except Exception:  # noqa: BLE001
            prev_n = 0
    meta = {"run_id": run_id, "subset": a.subset, "backend": a.backend,
            "model": a.model, "device": a.device,
            "endpoint": a.endpoint if a.backend == "openai" else None,
            "n": prev_n + n, "n_error": n_err, "resumed": bool(a.resume_run),
            "created": dt.datetime.now().isoformat(timespec="seconds"),
            "note": "dry 后端数字仅验证管线，不代表模型能力"}
    (out_dir / "run.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                                      encoding="utf-8")
    print(f"done: {n} rows ({n_err} errors) -> {out_dir}")


if __name__ == "__main__":
    main()
