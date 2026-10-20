"""按初始错误类别的 F3 修复率：更正 grounded 池定义（D9）。

R1 的表与图（e1_analysis.py H2a、make_figures.py fig3_repairability）用"排除 C1"构造
所谓 grounded 池，实际含 C2（无原文窗口）。本脚本：
- 主表：真正有窗口的 C3/C4；
- 补充：R1 发表时的 C2/C3/C4 池（复现原表数字作锚点）与无窗口的 C1/C2；
- context_displacement 另报去掉 TGU6_T2（金标准 speaker 为 Butler 译名 Ulysses）后的值。
错误类别取冻结日志 k=0 判定的 error_class_candidate，不改。

输出 out/error_class_grounded.md 与 out/figures/fig3_repairability.pdf/png（主表口径）。
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

import r2_common as C  # noqa: E402

OUT = Path(__file__).resolve().parent / "out"
ORDER = ["format_failure", "version_drift", "misattribution", "fabricated_quotation", "context_displacement"]


def table(rows, conds, drop_task=None):
    agg = defaultdict(lambda: [0, 0])
    for r in rows:
        if r["k0_strict"] or r["condition"] not in conds:
            continue
        if drop_task and r["task_id"] == drop_task:
            continue
        ec = r["rounds"][0]["judge"].get("error_class_candidate") or "unknown"
        agg[ec][0] += 1
        agg[ec][1] += int(r["final_strict"])
    return agg


def fmt(agg, ec):
    n, s = agg.get(ec, [0, 0])
    if not n:
        return "—", "—", "—"
    lo, hi = C.wilson(s, n)
    return str(n), f"{100*s/n:.0f}% ({s}/{n})", f"[{100*lo:.0f}, {100*hi:.0f}]"


def main() -> None:
    C.utf8_stdout()
    OUT.mkdir(exist_ok=True)
    rows = C.load_primary()
    pools = [("C3/C4 (grounded; primary)", {"C3", "C4"}), ("C2/C3/C4 (as published in R1)", {"C2", "C3", "C4"}),
             ("C1/C2 (no source window)", {"C1", "C2"})]
    md = ["# F3 repair rate by initial error class (confirmatory)", ""]
    for name, conds in pools:
        agg = table(rows, conds)
        md += [f"## {name}", "", "| Initial error class | n | Repair rate | Wilson 95% CI |", "|---|---|---|---|"]
        for ec in ORDER:
            n, rate, ci = fmt(agg, ec)
            md.append(f"| {ec} | {n} | {rate} | {ci} |")
        md.append("")
    for name, conds in pools[:1]:
        agg = table(rows, conds, drop_task="TGU6_T2")
        n, rate, ci = fmt(agg, "context_displacement")
        md += [f"context_displacement in {name} excluding TGU6_T2: n={n}, {rate}, Wilson {ci}", ""]
    # 正文"fabricated：C3 52% vs C1 24%"的复核
    for c in ("C1", "C3"):
        agg = table(rows, {c})
        n, rate, ci = fmt(agg, "fabricated_quotation")
        md.append(f"fabricated_quotation in {c}: n={n}, {rate}, Wilson {ci}")
    (OUT / "error_class_grounded.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))

    # 图：主表口径
    agg = table(rows, {"C3", "C4"})
    order = [e for e in ORDER if agg.get(e, [0])[0]]
    rates = [100 * agg[e][1] / agg[e][0] for e in order]
    cis = [C.wilson(agg[e][1], agg[e][0]) for e in order]
    fig, ax = plt.subplots(figsize=(6.2, 4))
    ax.bar(range(len(order)), rates, color="#5aa469",
           yerr=[[r - 100 * lo for r, (lo, _) in zip(rates, cis)], [100 * hi - r for r, (_, hi) in zip(rates, cis)]],
           capsize=3, ecolor="#555555")
    for i, (rt, e) in enumerate(zip(rates, order)):
        ax.annotate(f"{rt:.0f}%\n(n={agg[e][0]})", (i, 100 * cis[i][1] + 2), ha="center", fontsize=8)
    ax.set_xticks(range(len(order)))
    ax.set_xticklabels([e.replace("_", "\n") for e in order], fontsize=8)
    ax.set_ylabel("F3 repair rate (%), grounded C3/C4")
    ax.set_ylim(0, 110)
    ax.grid(axis="y", alpha=0.3)
    (OUT / "figures").mkdir(exist_ok=True)
    for ext in ("pdf", "png"):
        fig.savefig(OUT / "figures" / f"fig3_repairability.{ext}", dpi=200, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
