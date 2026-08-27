"""补证 C5：各错误认识论类别的 cell 计数 + 修复率 + 95% CI（零 API）。

回应"点估计冒充真率、各错误类别 n 未报"的攻击：对 F3 臂、confirmatory、k0 失败、
非 C1 的池，按初始错误类别（rounds[0] 的 error_class_candidate）报告
n / 修复数 / 修复率 / Wilson 95% CI。小 cell 用 Wilson 区间（比正态更稳）。
同时给出任务级聚类自助 CI 作对照（与主稿其他 CI 口径一致）。

用法：python journal_extension/error_class_cells.py
"""
from __future__ import annotations

import json
import math
import random
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEV = {"TGU2", "TGU4"}
TAGS = ["e1c_m2", "e1c_m3", "e1c_m4", "e1c_m1"]
ORDER = ["format_failure", "version_drift", "misattribution",
         "fabricated_quotation", "context_displacement"]


def load():
    rows = []
    for tag in TAGS:
        p = ROOT / "runs" / "raw" / f"ext_{tag}" / f"{tag}.jsonl"
        if p.exists():
            rows += [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    return [r for r in rows if r.get("arm") == "F3"]


def conf(r):
    return r["task_id"].split("_")[0] not in DEV


def wilson(k, n, z=1.96):
    """Wilson score 区间（比例，小样本更稳）。"""
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - h) / d, (c + h) / d)


def cluster_boot(items, B=2000):
    """任务级聚类自助 CI（items: list[(task_id, y)]）。"""
    by = defaultdict(list)
    for t, y in items:
        by[t].append(y)
    tasks = list(by)
    if len(tasks) < 2:
        return (float("nan"), float("nan"))
    rng = random.Random(20260705)
    means = []
    for _ in range(B):
        pool = []
        for _ in range(len(tasks)):
            pool += by[tasks[rng.randrange(len(tasks))]]
        if pool:
            means.append(sum(pool) / len(pool))
    means.sort()
    lo = means[int(0.025 * len(means))]
    hi = means[int(0.975 * len(means))]
    return (lo, hi)


def main():
    rows = load()
    # 池：confirmatory、k0 失败、非 C1
    cells = defaultdict(list)          # ec -> [(task_id, final_strict)]
    for r in rows:
        if not conf(r) or r["k0_strict"] or r["condition"] == "C1":
            continue
        ec = (r["rounds"][0]["judge"].get("error_class_candidate") or "unknown")
        cells[ec].append((r["task_id"], int(r["final_strict"])))

    lines = []
    lines.append("| 初始错误类别 | n | 修复数 | 修复率 | Wilson 95% CI | 任务聚类自助 95% CI |")
    lines.append("|---|---|---|---|---|---|")
    total_n = total_k = 0
    keys = [e for e in ORDER if e in cells] + [e for e in cells if e not in ORDER]
    for ec in keys:
        items = cells[ec]
        n = len(items)
        k = sum(y for _, y in items)
        total_n += n
        total_k += k
        rate = k / n if n else float("nan")
        wl, wh = wilson(k, n)
        bl, bh = cluster_boot(items)
        lines.append(
            f"| {ec} | {n} | {k} | {rate*100:.0f}% | "
            f"[{wl*100:.0f}, {wh*100:.0f}] | [{bl*100:.0f}, {bh*100:.0f}] |"
        )
    lines.append(f"| **合计池** | {total_n} | {total_k} | {total_k/total_n*100:.0f}% | — | — |")

    out = "\n".join(lines)
    print(out)
    print(f"\n池定义：F3 臂 · confirmatory(排除 TGU2/TGU4 dev) · k0 严格失败 · 排除 C1(无源)条件。")
    print(f"错误类别取修复前(rounds[0])的 error_class_candidate；'修复'=第 3 轮内任一轮 final_strict。")
    dst = ROOT / "journal_extension" / "error_class_cells.md"
    dst.write_text("# C5 补证：错误类别 cell 计数 + CI\n\n" + out +
                   "\n\n池：F3 · confirmatory · k0 失败 · 非 C1；修复率=final_strict；CI 见列。\n",
                   encoding="utf-8")
    print(f"\n-> 写出 {dst}")


if __name__ == "__main__":
    main()
