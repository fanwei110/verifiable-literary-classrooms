"""Smoke test 分析：两个命门 + 臂间配对对比。

命门 A：修复率是否按初始错误类别拉开（fabrication vs locator/context）——RQ2 成立性。
命门 B：反馈梯度 F1/F2/F3 是否有差——"定向"是否有净价值（对照 resample 派生的 best-of-k）。
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "runs" / "raw" / "ext_smoke" / "smoke.jsonl"
OUT = Path(__file__).resolve().parent / "analysis_ext" / "smoke_report.md"


def load() -> list[dict]:
    return [json.loads(l) for l in LOG.read_text(encoding="utf-8").splitlines() if l.strip()]


def main() -> None:
    rows = load()
    md = ["# Smoke test 报告（dev 任务 TGU2/TGU4 · M2+M4 · k≤2）", ""]

    # ---- k=0 基线（按 group 去重）----
    groups = {}
    for r in rows:
        groups.setdefault(r["group_id"], r)
    by_cond = defaultdict(lambda: [0, 0])
    for g in groups.values():
        by_cond[g["condition"]][0] += 1
        by_cond[g["condition"]][1] += 1 if g["k0_strict"] else 0
    md.append("## k=0 基线（本次新跑）")
    for c, (n, s) in sorted(by_cond.items()):
        md.append(f"- {c}: {s}/{n} = {100*s/n:.0f}% strict")
    md.append("")

    # ---- 修复率（仅 k0 失败组），按臂 ----
    fail_rows = [r for r in rows if not r["k0_strict"]]
    md.append(f"## 修复率（k0 失败组 n={len({r['group_id'] for r in fail_rows})}，臂内各修一次）")
    md.append("")
    md.append("| 臂 | 修复成功/失败组 | 修复率 | 平均额外调用 | 平均额外token(完成) |")
    md.append("|---|---|---|---|---|")
    arm_stats = {}
    for arm in ("resample", "F1", "F2", "F3"):
        sub = [r for r in fail_rows if r["arm"] == arm]
        if not sub:
            continue
        n = len(sub)
        if arm == "resample":
            # best-of-k 派生：额外轮任一 strict 即算该预算下成功
            fixed1 = sum(1 for r in sub if any(
                rd["judge"].get("strict_correct") for rd in r["rounds"][1:2]))
            fixed2 = sum(1 for r in sub if any(
                rd["judge"].get("strict_correct") for rd in r["rounds"][1:3]))
            arm_stats[arm] = (fixed2, n)
            md.append(f"| resample(best-of-1extra) | {fixed1}/{n} | {100*fixed1/n:.0f}% | 1.0 | — |")
            md.append(f"| resample(best-of-2extra) | {fixed2}/{n} | {100*fixed2/n:.0f}% | 2.0 | — |")
            continue
        fixed = sum(1 for r in sub if r["final_strict"])
        extra_calls = sum(len(r["rounds"]) - 1 for r in sub) / n
        toks = [sum(int((rd.get("usage") or {}).get("completion_tokens") or 0)
                    for rd in r["rounds"][1:]) for r in sub]
        arm_stats[arm] = (fixed, n)
        md.append(f"| {arm} | {fixed}/{n} | {100*fixed/n:.0f}% | {extra_calls:.1f} | {sum(toks)/n:.0f} |")
    md.append("")

    # ---- 命门 A：F3 修复率按初始错误类别 ----
    md.append("## 命门 A：修复率 × 初始错误类别（F3 臂）")
    md.append("")
    md.append("| 初始错误类别 | 条件 | 修复成功/n | 修复率 |")
    md.append("|---|---|---|---|")
    cls_gap = {}
    for arm in ("F3", "F2"):
        by_cls = defaultdict(lambda: [0, 0])
        for r in fail_rows:
            if r["arm"] != arm:
                continue
            cls = r["rounds"][0]["judge"].get("error_class_candidate") or "unknown"
            key = (cls, r["condition"])
            by_cls[key][0] += 1
            by_cls[key][1] += 1 if r["final_strict"] else 0
        if arm == "F3":
            for (cls, cond), (n, s) in sorted(by_cls.items()):
                md.append(f"| {cls} | {cond} | {s}/{n} | {100*s/n:.0f}% |")
            # 拉开度：fabrication vs context_displacement（并 C1/C3）
            agg = defaultdict(lambda: [0, 0])
            for (cls, _c), (n, s) in by_cls.items():
                agg[cls][0] += n
                agg[cls][1] += s
            fab = agg.get("fabricated_quotation", [0, 0])
            cd = agg.get("context_displacement", [0, 0])
            if fab[0] and cd[0]:
                cls_gap["fab"] = fab[1] / fab[0]
                cls_gap["cd"] = cd[1] / cd[0]
    md.append("")

    # ---- 判定 ----
    md.append("## 门槛判定")
    f3 = arm_stats.get("F3", (0, 1))
    rs = arm_stats.get("resample", (0, 1))
    f1 = arm_stats.get("F1", (0, 1))
    f3_rate, rs_rate, f1_rate = f3[0] / f3[1], rs[0] / rs[1], f1[0] / f1[1]
    md.append(f"- H1 增益门槛（修复率 vs 盲重采样）：F3 {100*f3_rate:.0f}% vs resample {100*rs_rate:.0f}% "
              f"→ {'PASS' if f3_rate - rs_rate >= 0.05 else 'MARGINAL/FAIL（触发 fallback 评估）'}")
    md.append(f"- H2c 定向价值（F3 vs F1 二值）：{100*f3_rate:.0f}% vs {100*f1_rate:.0f}% "
              f"→ {'分层可见' if f3_rate - f1_rate >= 0.05 else '差异不明显（smoke 样本小，待 E1b 检验）'}")
    if cls_gap:
        gap = cls_gap.get("cd", 0) - cls_gap.get("fab", 0)
        md.append(f"- 命门 A（类别拉开）：context_displacement {100*cls_gap.get('cd',0):.0f}% vs "
                  f"fabrication {100*cls_gap.get('fab',0):.0f}%（差 {100*gap:+.0f}pp）"
                  f"→ {'RQ2 有戏' if abs(gap) >= 0.10 else '拉不开（触发 fallback 评估）'}")

    OUT.write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
