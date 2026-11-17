"""#12 出端载荷审计：对归档输出离线统计，零模型调用。

统计对象是 harness 处理后的 masked_text（即"若要上送云端时实际会发出去的文本"），
回答两个问题：
  1. 载荷有多大（字节数、相对原文的压缩比）；
  2. 上送文本里还剩多少 PII（手机号/身份证/银行卡号）。

产物：
  05-载荷审计/payload_audit.csv      每个 run 一行
  05-载荷审计/payload_audit.json     汇总
"""

from __future__ import annotations

import collections
import json
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1] / "JSNC202611" / "edge-harness-poc"
OUT = Path(__file__).resolve().parent / "05-载荷审计"

def audit_run(run_dir: Path) -> dict | None:
    """按金标实体比对：只有"标注 PII 的原文仍出现在脱敏后文本里"才算泄漏。

    不用正则会把手动保留的干扰项（订单号/金额）误判为 PII。
    """
    raw = run_dir / "raw.jsonl"
    run_json = run_dir / "run.json"
    if not raw.exists() or not run_json.exists():
        return None
    meta = json.loads(run_json.read_text(encoding="utf-8"))
    if meta.get("subset") != "mask":
        return None

    n = n_masked = 0
    orig_bytes = out_bytes = 0
    leak_rows = 0
    leak_entities = 0
    leak_detail: list[str] = []
    by_type_total: collections.Counter = collections.Counter()
    by_type_leak: collections.Counter = collections.Counter()

    for line in raw.open(encoding="utf-8"):
        if not line.strip():
            continue
        rec = json.loads(line)
        out = rec.get("output") or {}
        if "__error__" in out:
            continue
        n += 1
        src = rec.get("text") or ""
        dst = out.get("pred_text") or ""
        orig_bytes += len(src.encode("utf-8"))
        out_bytes += len(dst.encode("utf-8"))
        if out.get("action") == "masked":
            n_masked += 1

        ents = (rec.get("meta") or {}).get("entities", [])
        for e in ents:
            by_type_total[e.get("type", "?")] += 1
        hit = []
        for e in ents:
            orig = e.get("original", "")
            if orig and orig in dst:
                by_type_leak[e.get("type", "?")] += 1
                hit.append(orig)
        if hit:
            leak_rows += 1
            leak_entities += len(hit)
            if len(leak_detail) < 10:
                leak_detail.append(f"{rec.get('id')}:{'/'.join(hit[:2])}")

    return {
        "run": run_dir.name,
        "model": meta.get("model"),
        "n": n,
        "n_masked": n_masked,
        "orig_bytes": orig_bytes,
        "sent_bytes": out_bytes,
        "byte_ratio": round(out_bytes / orig_bytes, 4) if orig_bytes else None,
        "leak_rows": leak_rows,
        "leak_entities": leak_entities,
        "leak_rate": round(leak_rows / n, 4) if n else None,
        "leak_examples": ";".join(leak_detail),
        **{f"total_{t}": v for t, v in by_type_total.items()},
        **{f"leak_{t}": v for t, v in by_type_leak.items()},
        "_by_type": {"total": dict(by_type_total), "leak": dict(by_type_leak)},
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for d in sorted((HARNESS / "eval" / "reports").iterdir()):
        r = audit_run(d)
        if r:
            rows.append(r)

    if not rows:
        print("没有找到 mask 运行归档")
        return

    cols = [k for k in rows[0].keys() if not k.startswith("_")]
    with (OUT / "payload_audit.csv").open("w", encoding="utf-8-sig", newline="") as f:
        f.write(",".join(cols) + "\n")
        for r in rows:
            f.write(",".join(str(r.get(c, "")) for c in cols) + "\n")

    total_rows = sum(r["n"] for r in rows)
    total_leak = sum(r["leak_rows"] for r in rows)
    total_ents = sum(r["leak_entities"] for r in rows)
    agg_total: collections.Counter = collections.Counter()
    agg_leak: collections.Counter = collections.Counter()
    for r in rows:
        agg_total.update(r["_by_type"]["total"])
        agg_leak.update(r["_by_type"]["leak"])
    by_type = {
        t: {
            "entities": agg_total[t],
            "leaked": agg_leak.get(t, 0),
            "leak_rate": round(agg_leak.get(t, 0) / agg_total[t], 4) if agg_total[t] else None,
        }
        for t in sorted(agg_total)
    }

    # 每个 model 只取最新一轮（run 名含时间戳），避免混入 C1 之前的历史版本
    latest = {}
    for r in rows:
        m = r.get("model") or "?"
        if m not in latest or r["run"] > latest[m]["run"]:
            latest[m] = r
    lt_total: collections.Counter = collections.Counter()
    lt_leak: collections.Counter = collections.Counter()
    for r in latest.values():
        lt_total.update(r["_by_type"]["total"])
        lt_leak.update(r["_by_type"]["leak"])
    by_type_latest = {
        t: {
            "entities": lt_total[t],
            "leaked": lt_leak.get(t, 0),
            "leak_rate": round(lt_leak.get(t, 0) / lt_total[t], 4) if lt_total[t] else None,
        }
        for t in sorted(lt_total)
    }

    summary = {
        "runs_audited": len(rows),
        "rows_total": total_rows,
        "residual_entities": total_ents,
        "rows_with_residual_pii": total_leak,
        "residual_pii_rate": round(total_leak / total_rows, 4) if total_rows else None,
        "method": "按金标 meta.entities.original 精确比对，非正则匹配（避免干扰项误判）",
        "avg_byte_ratio": round(
            sum(r["byte_ratio"] for r in rows if r["byte_ratio"]) / len([r for r in rows if r["byte_ratio"]]), 4
        ),
        "by_entity_type": by_type,
        "by_entity_type_latest": by_type_latest,
        "latest_runs": {m: r["run"] for m, r in latest.items()},
        "note": "sent_bytes 为脱敏后文本字节数；leak_* 为脱敏后文本中残留的 PII 计数",
    }
    (OUT / "payload_audit.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"明细: {OUT / 'payload_audit.csv'}（{len(rows)} 个 run）")


if __name__ == "__main__":
    main()
