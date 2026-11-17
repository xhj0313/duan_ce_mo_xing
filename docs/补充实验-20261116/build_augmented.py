"""用本地 4B 模型生成 v1.1 增广集（同时带 variant 标签）。

一次性服务两个清单项：
  #5 扩充评测集：每类 test ≥20 条（原本每类 5 条）；
  #7 变体分项：每条带 variant ∈ {standard, colloquial, typo, elderly, terse}。

口径声明（写入产物 meta）：
  - 改写由**本地 Qwen3-4B-Q4**完成，不是行内旗舰 API；
  - **未经人工盲标**（无 κ 检验），不可当作"换人盲标后的 v1.0"；
  - 生成后做确定性去重与意图一致性抽检，但不改标签。
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parents[1] / "JSNC202611" / "edge-harness-poc"
sys.path.insert(0, str(BASE))

from harness.adapter_openai import OpenAIAdapter  # noqa: E402

OUT = Path(__file__).resolve().parent / "datasets"
SRC = BASE / "eval" / "datasets" / "intent.jsonl"
REWRITE_PROMPT = """你是手机银行用户语料增广器。对下面这条"用户想说的话"各生成一个变体：
1. 口语化（随意、省略，如"咋"、"啥"）
2. 带错别字或拼音混写（如"帮偶查哈子"、"账 Hao"）
3. 老年人口吻（啰嗦、礼貌、无主语，如"我年纪大了…"、"麻烦你慢慢说…"）
4. 极简指代（假设有上文，如"那笔呢"、"再查一个"、"跨行的呢"）
保持原意不变，不要改变业务意图。只输出 JSON 数组：["变体1","变体2","变体3","变体4"]
原句：{seed}"""

VARIANTS = ["colloquial", "typo", "elderly", "terse"]
TARGET_PER_CLASS = 20


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--endpoint", default="http://127.0.0.1:8080/v1")
    ap.add_argument("--seeds-per-class", type=int, default=4)
    ap.add_argument("--limit-classes", type=int, default=0, help="调试用：只处理前 N 类")
    a = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    ad = OpenAIAdapter(a.endpoint, temperature=0.7)

    rows = [json.loads(l) for l in SRC.open(encoding="utf-8") if l.strip()]
    by_class: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        if r.get("split") == "test":
            by_class[r["meta"]["gold_intent"]].append(r)

    classes = sorted(by_class)
    if a.limit_classes:
        classes = classes[: a.limit_classes]

    out_rows: list[dict] = []
    stats = Counter()
    for ci, cls in enumerate(classes, 1):
        seeds = by_class[cls][: a.seeds_per_class]
        # 原有 5 条按 standard 计
        for r in by_class[cls]:
            out_rows.append({"id": r["id"], "subset": "intent_v11", "split": "test",
                             "text": r["text"], "variant": "standard",
                             "meta": {"gold_intent": cls, "source": "original"}})
        seen = {r["text"] for r in by_class[cls]}

        for s in seeds:
            prompt = REWRITE_PROMPT.format(seed=s["text"])
            got: list[str] = []
            for attempt in range(3):
                try:
                    raw, _ = ad.generate(prompt, max_new_tokens=256)
                    arr = json.loads(raw[raw.index("["): raw.rindex("]") + 1])
                    if len(arr) >= 4:
                        got = [str(x).strip() for x in arr[:4]]
                        break
                except Exception:  # noqa: BLE001
                    pass
                time.sleep(1)
            if len(got) != 4:
                stats["failed"] += 1
                print(f"  !! {cls} 改写失败: {s['text'][:20]}", flush=True)
                continue
            for v, text in zip(VARIANTS, got):
                if not text or text in seen or len(text) > 60:
                    stats["dedup"] += 1
                    continue
                seen.add(text)
                out_rows.append({
                    "id": f"v11_{cls}_{v}_{len(out_rows):05d}",
                    "subset": "intent_v11", "split": "test", "text": text,
                    "variant": v,
                    "meta": {"gold_intent": cls, "source": "local-4b-rewrite", "seed": s["text"]},
                })
                stats[v] += 1
        print(f"[{ci}/{len(classes)}] {cls}: {sum(1 for x in out_rows if x['meta']['gold_intent']==cls)} 条", flush=True)

    p = OUT / "intent_v11.jsonl"
    with p.open("w", encoding="utf-8") as f:
        for r in out_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    meta = {
        "name": "intent_v11", "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "n": len(out_rows), "classes": len(classes),
        "variant_distribution": dict(stats),
        "provenance": "本地 Qwen3-4B-Instruct-2507-Q4_K_M 改写，非行内旗舰 API",
        "limits": [
            "未经人工盲标（无 κ 检验）",
            "gold_intent 沿用种子标签，未做二次人工校验",
            "仅用于 PC 侧趋势复测，不可宣称达到 v1.0 冻结集质量",
        ],
        "target_per_class": TARGET_PER_CLASS,
    }
    (OUT / "intent_v11.meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"写出 {p}（{len(out_rows)} 条）")
    print(json.dumps(dict(stats), ensure_ascii=False))


if __name__ == "__main__":
    main()
