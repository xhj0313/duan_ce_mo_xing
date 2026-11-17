"""#14 替代口径：用评测集意图分布当"流量分布"，计算加权承接率。

**口径声明**：真实业务流量分布未到位，这里用 intent 测试集的类别占比作代理，
不能宣称"真实流量加权的 97.8% 承接率"。仅为方法论演示与相对比较。

承接定义：注册表 route=faq/tool 视为本地闭环；route=cloud 视为转人工（非完全闭环）。
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parents[1] / "JSNC202611" / "edge-harness-poc"
OUT = Path(__file__).resolve().parent / "12-流量加权"
MODELS = ["qwen3-1.7b-q8", "qwen3-1.7b-q4", "qwen3-4b-q4", "qwen3-4b-q8"]


def load_routes() -> dict[str, str]:
    import re
    text = (BASE / "registry" / "intents.yaml").read_text(encoding="utf-8")
    routes: dict[str, str] = {}
    cur = None
    for line in text.splitlines():
        m = re.match(r"^\s*-?\s*id:\s*([A-Za-z0-9_]+)", line)
        if m:
            cur = m.group(1)
            continue
        m = re.match(r"^\s*route:\s*([a-z_]+)", line)
        if m and cur:
            routes[cur] = m.group(1)
            cur = None
    return routes


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    routes = load_routes()
    ds = [json.loads(l) for l in (BASE / "eval" / "datasets" / "intent.jsonl").open(encoding="utf-8") if l.strip()]
    test = [r for r in ds if r.get("split") == "test"]
    dist = Counter(r["meta"]["gold_intent"] for r in test)
    n = sum(dist.values())

    rows, detail = [], {}
    for m in MODELS:
        dirs = sorted((BASE / "eval" / "reports").glob(f"20261116_*{m}_intent_*"))
        if not dirs:
            continue
        rows_raw = [json.loads(l) for l in (dirs[-1] / "raw.jsonl").open(encoding="utf-8") if l.strip()]
        cls_ok: dict[str, list[float]] = defaultdict(list)
        for r in rows_raw:
            out = r.get("output") or {}
            gold = r["meta"]["gold_intent"]
            route = routes.get(out.get("pred_intent"), "cloud")
            cls_ok[gold].append(1.0 if route != "cloud" else 0.0)

        weighted = 0.0
        per_class = {}
        for cls, cnt in dist.items():
            rate = sum(cls_ok.get(cls, [])) / max(len(cls_ok.get(cls, [])), 1)
            w = cnt / n
            weighted += w * rate
            per_class[cls] = {"n": cnt, "weight": round(w, 4), "local_rate": round(rate, 4)}
        rows.append({"model": m, "weighted_local_rate": round(weighted, 4),
                     "unweighted": round(sum(sum(cls_ok.get(c, [])) / max(len(cls_ok.get(c, [])), 1)
                                             for c in dist) / len(dist), 4)})
        detail[m] = per_class

    with (OUT / "traffic_weighted.csv").open("w", encoding="utf-8-sig", newline="") as f:
        import csv
        w = csv.DictWriter(f, fieldnames=["model", "weighted_local_rate", "unweighted"])
        w.writeheader(); w.writerows(rows)
    (OUT / "traffic_weighted_detail.json").write_text(
        json.dumps(detail, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "traffic_weighted.meta.json").write_text(json.dumps({
        "proxy": "intent 测试集类别占比（n=%d）代替真实业务流量分布" % n,
        "local_definition": "registry route=faq/tool 为本地闭环；route=cloud 为转人工",
        "limits": ["未使用真实流量分布", "不可宣称 97.8% 承接率已按流量验证",
                   "仅作方法论演示与模型间相对比较"],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"写出 {OUT / 'traffic_weighted.csv'}")
    for r in rows:
        print(f"  {r['model']}: 加权 {r['weighted_local_rate']} | 不加权 {r['unweighted']}")


if __name__ == "__main__":
    main()
