# -*- coding: utf-8 -*-
"""R1.1/R1.2 · 系统流程图（matplotlib，避开 TikZ 与 ieeeaccess.cls 的已知冲突）。

明确标注：verifier 是确定性规则程序，不是 LLM（直接回应 R1.6 的误读来源）。
R2 修订：去掉与 0.75 locator 容差矛盾的 'no similarity threshold'，H1a 表述与预注册一致。
输出：revision_R2_analysis/out/figures/fig_pipeline.pdf(.png)
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

OUT = Path(__file__).resolve().parent / "out" / "figures"

BLUE = "#2b6cb0"
GREY = "#4a5568"
GREEN = "#276749"
AMBER = "#975a16"
RED = "#9b2c2c"
LIGHT = "#edf2f7"


def box(ax, x, y, w, h, title, body, ec=GREY, fc="white", tsize=7.2, bsize=6.2, lw=1.0):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.010,rounding_size=0.018",
                                linewidth=lw, edgecolor=ec, facecolor=fc, zorder=2))
    ax.text(x + w / 2, y + h - 0.045, title, ha="center", va="top", fontsize=tsize,
            fontweight="bold", color=ec, zorder=3)
    if body:
        ax.text(x + w / 2, y + h - 0.115, body, ha="center", va="top", fontsize=bsize,
                color="#2d3748", zorder=3, linespacing=1.5)


def arrow(ax, p, q, color=GREY, lw=1.0, rad=0.0, ls="-"):
    ax.add_patch(FancyArrowPatch(p, q, arrowstyle="-|>", mutation_scale=9, linewidth=lw,
                                 color=color, zorder=1, linestyle=ls,
                                 connectionstyle=f"arc3,rad={rad}"))


def main():
    fig, ax = plt.subplots(figsize=(7.1, 4.3))
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")

    # ============ Lane (a): design factors ============
    ax.text(0.005, 0.995, "(a)  Experimental design factors", fontsize=7.8,
            fontweight="bold", color="#1a202c", va="top")

    xs = [0.015, 0.265, 0.515, 0.765]
    w, h, y = 0.222, 0.285, 0.665
    box(ax, xs[0], y, w, h, "Frozen corpus",
        "6 English works,\n2 Chinese classics,\nSHA256-anchored", ec=BLUE, fc=LIGHT)
    box(ax, xs[1], y, w, h, "Tasks",
        "6 TGUs (units)\n$\\times$  3 task types:\nT1 retrieval,\nT2 attribution,\nT3 mini-lesson", ec=BLUE)
    box(ax, xs[2], y, w, h, "Prompt conditions",
        "2$\\times$2 grounding\n$\\times$ structure:\nC1, C2, C3, C4", ec=BLUE)
    box(ax, xs[3], y, w, h, "Generators",
        "M1 Mistral-Large\nM2 DeepSeek-chat\nM3 Qwen3-235B\nM4 DS-reasoner", ec=BLUE)
    for i in range(3):
        arrow(ax, (xs[i] + w, y + h / 2), (xs[i + 1], y + h / 2), color=BLUE)

    # each generation flows down into the verifier
    arrow(ax, (0.42, 0.660), (0.42, 0.605), color=BLUE, lw=1.2)
    ax.text(0.432, 0.632, "every generation", fontsize=6.1, color=BLUE, va="center")

    # ============ Verifier (hub) ============
    box(ax, 0.105, 0.420, 0.79, 0.185,
        "Deterministic verifier   —   a rule-based program, NOT an LLM",
        "normalized exact substring membership in the frozen text, plus attribution, locator, speaker and grounding\n"
        "strict_correct = all five fields pass   (fixed rules, no learned component, no model choice)",
        ec=RED, fc="#fff5f5", tsize=7.6, bsize=6.0, lw=1.7)

    # ============ Verdict split ============
    arrow(ax, (0.22, 0.420), (0.22, 0.348), color=GREEN, lw=1.2)
    ax.text(0.236, 0.384, "pass", fontsize=6.6, color=GREEN, fontweight="bold", ha="left")
    arrow(ax, (0.62, 0.420), (0.62, 0.348), color=AMBER, lw=1.2)
    ax.text(0.632, 0.384, "fail", fontsize=6.6, color=AMBER, fontweight="bold", ha="left")

    # ============ Lane (b): in-loop handling ============
    ax.text(0.005, 0.402, "(b)  In-loop handling", fontsize=7.6,
            fontweight="bold", color="#1a202c", va="top")

    box(ax, 0.015, 0.092, 0.24, 0.250, "Deliver",
        "verified quotation\nreleased to\nthe classroom", ec=GREEN, fc="#f0fff4", bsize=6.2)
    box(ax, 0.305, 0.092, 0.36, 0.250, "Repair arms  (budget $k \\leq 3$)",
        "resample: independent redraw (best-of-$k$)\n"
        "F1: binary 'did not verify'\n"
        "F2: F1 + error class\n"
        "F3: F2 + field-level flags", ec=AMBER, fc="#fffff0", bsize=6.2)
    box(ax, 0.715, 0.092, 0.27, 0.250, "Audit-only guardrail",
        "quotation length,\nevidence count,\nstrict/defensible divergence\n(never fed back)",
        ec=GREY, fc=LIGHT, bsize=6.1)

    # feedback loop back up to verifier
    arrow(ax, (0.335, 0.342), (0.30, 0.417), color=AMBER, lw=1.2, rad=0.30, ls="--")
    ax.text(0.338, 0.368, "re-checked each round",
            fontsize=5.9, color=AMBER, style="italic", va="center", ha="left")

    # audit observes repaired outputs
    arrow(ax, (0.715, 0.217), (0.668, 0.217), color=GREY, ls=":")

    # ============ Footnotes ============
    ax.text(0.015, 0.062, "F4 (oracle feedback, which contains the answer) is physically isolated as a "
                          "capability ceiling and is excluded from every reported pool.",
            fontsize=6.1, color="#4a5568", va="top")
    ax.text(0.015, 0.022, "Preregistered contrasts: H1a is the only primary contrast (C3 strict gain after F3 repair); "
                          "secondary families are controlled with Benjamini-Hochberg FDR.",
            fontsize=6.1, color="#4a5568", va="top")

    OUT.mkdir(parents=True, exist_ok=True)
    for ext in ("pdf", "png"):
        fig.savefig(OUT / f"fig_pipeline.{ext}", dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {OUT/'fig_pipeline.pdf'}")


if __name__ == "__main__":
    main()
