"""F2 离线模拟：确定性短路（高置信匹配则直接返回卡片原文，不走生成）。

为什么先模拟：短路改变的是"答案内容"，可以拿已有 raw.jsonl 的题目+卡片，
把高置信行的答案替换成卡片原文后重判，无需重跑模型。跑通再实现进 pipeline。

判据：
  - 覆盖率 = 问题（二元组）被信息点覆盖的比例
  - 取覆盖率 ≥ 阈值的信息点，最多 k 条，拼成"根据行内资料：…（以行内公示为准）"
  - 阈值/ k 做网格扫描，观察 info_hit 与短路率

用法：
  python experiments/sim_f2.py --run 20261103_120438_qwen3-4b2507_faq_mid_openai
"""

from __future__ import annotations

import argparse
import itertools
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "eval" / "judges"))

import faq_judge as J  # noqa: E402

REPORTS = ROOT / "eval" / "reports"


def q_cov(question: str, point: str) -> float:
    """问题被信息点覆盖的比例（问题侧覆盖率更贴近"这条能不能回答我"）。"""
    q = J.canon(question)
    grams = {q[i:i + 2] for i in range(len(q) - 1)}
    if not grams:
        return 0.0
    p = J.canon(point)
    pool = {p[i:i + 2] for i in range(len(p) - 1)}
    return len(grams & pool) / len(grams)


def short_answer(points: list[str]) -> str:
    body = "；".join(re.sub(r"\[占位示例[^\]]*\]", "", t).rstrip("。；; ") for t in points)
    return f"根据行内资料：{body}。（以行内公示为准）"


def simulate(run_dir: Path, thresh: float, k: int) -> tuple[float, float, int]:
    rows = [json.loads(l) for l in (run_dir / "raw.jsonl").open(encoding="utf-8")]
    hit = total = fired = 0
    for r in rows:
        meta = r["meta"]
        pts = J.load_info_points(meta["gold_intent"])
        reply = r["output"].get("reply", "")
        scored = sorted(((q_cov(r["text"], t), pid) for pid, t in pts.items()), reverse=True)
        chosen = [pts[pid] for s, pid in scored[:k] if s >= thresh]
        if chosen:
            reply = short_answer(chosen)
            fired += 1
        rc = J.canon(reply)
        for pid in meta["info_points"]:
            total += 1
            line = pts.get(pid, "")
            toks = J.key_tokens(line)
            ok = any(t in reply for t in toks) or any(J.canon(t) in rc for t in toks)
            if not ok:
                nums = [J.canon(x) for x in re.findall(r"\d+(?:\.\d+)?%?", line)]
                ok = any(J.num_present(rc, n) for n in nums) if nums else any(
                    J.canon(p) in rc or (len(p) >= 4 and J.fuzzy_hit(rc, p)) for p in toks)
            hit += ok
    return hit / total, fired / len(rows), len(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    a = ap.parse_args()
    run_dir = REPORTS / a.run
    base, _, n = simulate(run_dir, 9.9, 0)     # 不短路 = 现状
    print(f"现状（不短路）: info_hit={base:.3f}  n={n}\n")
    print(f"{'阈值':>6} {'k':>2} {'短路率':>8} {'info_hit':>9} {'Δ':>7}")
    best = (base, None)
    for thresh, k in itertools.product([0.3, 0.4, 0.5, 0.6, 0.7, 0.8], [1, 2]):
        rate, fired, _ = simulate(run_dir, thresh, k)
        print(f"{thresh:>6.1f} {k:>2} {fired:>8.1%} {rate:>9.3f} {rate - base:>+7.3f}")
        if rate > best[0]:
            best = (rate, (thresh, k))
    if best[1]:
        print(f"\n最优: 阈值={best[1][0]} k={best[1][1]} → {best[0]:.3f}（{best[0] - base:+.3f}）")
    else:
        print("\n无配置优于现状 → F2 无效")


if __name__ == "__main__":
    main()
