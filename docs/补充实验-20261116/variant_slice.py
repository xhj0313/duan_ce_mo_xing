"""#7 语言变体分项成绩（启发式打标，非人工标注）。

背景：intent.jsonl 每条只有 gold_intent，**没有 variant 字段**，id 后缀也不是变体序，
因此无法直接切片。这里用规则给每条打标，事后分组统计，用于看趋势而非精确归因。

标签优先级（先匹配先生效）：
  elderly    老年口吻：老人家/不会用/慢慢说/眼睛…
  typo       错别字/拼音混写：含连续英文字母
  colloquial 口语化：咋/啥/呗/嘛/麻烦/帮我…
  terse      极简：≤8 字且无上述特征
  standard   其余（书面/完整句）

产物（06-变体切片/）：
  variant_tagged.csv      逐条标签与对错
  variant_accuracy.csv    模型 × 标签 准确率
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1] / "JSNC202611" / "edge-harness-poc"
OUT = Path(__file__).resolve().parent / "06-变体切片"

RULES = [
    ("elderly", re.compile(r"老人家|老人|年纪|岁数|眼花|眼睛|耳朵背|听不清|不会用|不太会|慢慢说|孙子|孙女")),
    # 说明：本版数据集实际不含拼音/错别字混写样本（含字母的仅为 "XX市""App" 等干扰），
    # 故不设 typo 类；报告中如实说明该变体无法评估。
    ("colloquial", re.compile(r"咋|啥|呗|嘛|啊|呀|呃|那个|麻烦|帮我|哈子|嘞|咧|唉")),
]


def tag(text: str) -> str:
    for name, pat in RULES:
        if pat.search(text):
            return name
    return "terse" if len(text) <= 8 else "standard"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    gold = {}
    for line in (HARNESS / "eval" / "datasets" / "intent.jsonl").open(encoding="utf-8"):
        r = json.loads(line)
        if r.get("split") == "test":
            gold[r["id"]] = r["meta"]["gold_intent"]

    rows = []
    for d in sorted((HARNESS / "eval" / "reports").glob("20261116_*_intent_*")):
        meta_p, raw_p = d / "run.json", d / "raw.jsonl"
        if not (meta_p.exists() and raw_p.exists()):
            continue
        model = json.loads(meta_p.read_text(encoding="utf-8")).get("model")
        if not model or not model.startswith("qwen3-"):   # 排除 smoke 等临时跑测
            continue
        for line in raw_p.open(encoding="utf-8"):
            if not line.strip():
                continue
            rec = json.loads(line)
            out = rec.get("output") or {}
            pred = out.get("pred_intent")
            g = gold.get(rec["id"])
            rows.append({
                "model": model, "id": rec["id"], "variant": tag(rec["text"]),
                "text": rec["text"], "gold": g, "pred": pred,
                "ok": int(pred is not None and pred == g),
            })

    if not rows:
        print("未找到 20261116 的 intent 数据")
        return

    with (OUT / "variant_tagged.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    models = sorted({r["model"] for r in rows})
    variants = ["standard", "colloquial", "elderly", "terse"]   # typo 类数据集中不存在
    out = []
    for m in models:
        for v in variants:
            sub = [r for r in rows if r["model"] == m and r["variant"] == v]
            if not sub:
                continue
            out.append({"model": m, "variant": v, "n": len(sub),
                        "accuracy": round(sum(r["ok"] for r in sub) / len(sub), 4)})
    with (OUT / "variant_accuracy.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)

    print(f"标注 {len(rows)} 条；变体分布：")
    for v in variants:
        n = sum(1 for r in rows if r["variant"] == v and r["model"] == models[0])
        print(f"  {v:12s} {n}")


if __name__ == "__main__":
    main()
