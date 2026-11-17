"""统计 raw.jsonl 中已有效完成的行数（排除 error 行，按 seq 去重）。"""
from __future__ import annotations
import json, sys
from pathlib import Path

def done_count(p: Path) -> int:
    if not p.exists():
        return 0
    seqs = set()
    for line in p.open(encoding="utf-8"):
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "__error__" in (r.get("output") or {}):
            continue
        if r.get("seq") is None:
            continue
        seqs.add(r["seq"])
    return len(seqs)

if __name__ == "__main__":
    print(done_count(Path(sys.argv[1])))
