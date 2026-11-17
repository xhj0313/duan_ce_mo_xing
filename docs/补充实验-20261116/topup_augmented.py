"""补齐 v1.1 增广集中不足 20 条的类别（去重后差额）。

对每类用不同 temperature 再生成一轮，只要不与已有文本重复就追加。
保持同一 provenance 声明：本地 4B 改写，未盲标。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parents[1] / "JSNC202611" / "edge-harness-poc"
sys.path.insert(0, str(BASE))
from harness.adapter_openai import OpenAIAdapter  # noqa: E402
from build_augmented import REWRITE_PROMPT, TARGET_PER_CLASS, VARIANTS  # noqa: E402

OUT = Path(__file__).resolve().parent / "datasets"
DS = OUT / "intent_v11.jsonl"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--endpoint", default="http://127.0.0.1:8080/v1")
    a = ap.parse_args()
    ad = OpenAIAdapter(a.endpoint, temperature=1.0)

    rows = [json.loads(l) for l in DS.open(encoding="utf-8") if l.strip()]
    by_class: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_class[r["meta"]["gold_intent"]].append(r)

    seeds: dict[str, list[str]] = defaultdict(list)
    for r in rows:
        if "seed" in r["meta"]:
            seeds[r["meta"]["gold_intent"]].append(r["meta"]["seed"])

    added = Counter()
    for cls, cur in by_class.items():
        need = TARGET_PER_CLASS - len(cur)
        if need <= 0:
            continue
        seen = {r["text"] for r in cur}
        tries = 0
        while need > 0 and tries < 8:
            seed = seeds[cls][tries % len(seeds[cls])] if seeds[cls] else cls
            try:
                raw, _ = ad.generate(REWRITE_PROMPT.format(seed=seed), max_new_tokens=256)
                arr = json.loads(raw[raw.index("["): raw.rindex("]") + 1])
            except Exception:  # noqa: BLE001
                tries += 1
                time.sleep(1)
                continue
            for v, text in zip(VARIANTS, arr[:4]):
                text = str(text).strip()
                if need <= 0:
                    break
                if not text or text in seen or len(text) > 60:
                    continue
                seen.add(text)
                rows.append({"id": f"v11t_{cls}_{v}_{len(rows):05d}", "subset": "intent_v11",
                             "split": "test", "text": text, "variant": v,
                             "meta": {"gold_intent": cls, "source": "local-4b-rewrite-topup",
                                      "seed": seed}})
                added[v] += 1
                need -= 1
            tries += 1
        print(f"  {cls}: +{sum(added.values()) if False else TARGET_PER_CLASS - need}/{len(cur)}", flush=True)

    with DS.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    meta_p = OUT / "intent_v11.meta.json"
    meta = json.loads(meta_p.read_text(encoding="utf-8"))
    c = Counter(r["meta"]["gold_intent"] for r in rows)
    meta["n"] = len(rows)
    meta["variant_distribution"] = dict(Counter(r["variant"] for r in rows))
    meta["classes_below_20"] = {k: n for k, n in c.items() if n < TARGET_PER_CLASS}
    meta["topup"] = dict(added)
    meta_p.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"总数 {len(rows)}；补入 {sum(added.values())} 条；仍不足20的类：{meta['classes_below_20']}")


if __name__ == "__main__":
    main()
