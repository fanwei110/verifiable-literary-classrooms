"""补充主图 F5 / F7（英文标签，风格同 make_figures.py）。
数据来源与口径（均可由 make_extra_tables.py 复算，逐格已与冻结正文核对）：
- F5 best-of-k：修正后 2160 网格 hypergeometric（各 cell 平均），C3 k1=61%→k10=76%。
- F7 检索/接地阶梯：语料正确率 C1 19% / BM25 27% / dense 37% / oracle 78%。
输出 figures/fig5_best_of_k.{png,pdf}、figures/fig7_retrieval_ladder.{png,pdf}。
"""
from __future__ import annotations
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

FIGDIR = Path(__file__).resolve().parents[1] / "figures"

# ---- F5 数据（make_extra_tables.py 输出，corrected grid, hypergeometric）----
K = list(range(1, 11))
BOK = {
    "C1 (no source)":      [37, 43, 46, 49, 50, 52, 53, 54, 55, 56],
    "C2 (schema)":         [43, 47, 49, 51, 52, 52, 53, 53, 54, 54],
    "C3 (grounded)":       [61, 68, 71, 72, 74, 74, 75, 75, 76, 76],
    "C4 (grounded+templ)": [63, 69, 71, 73, 74, 74, 75, 75, 76, 76],
}
STYLE = {
    "C1 (no source)":      ("#bbbbbb", "o", "--"),
    "C2 (schema)":         ("#888888", "s", "--"),
    "C3 (grounded)":       ("#2b7bba", "o", "-"),
    "C4 (grounded+templ)": ("#5aa469", "^", "-"),
}


def save(fig, name):
    FIGDIR.mkdir(exist_ok=True)
    for ext in ("png", "pdf"):
        fig.savefig(FIGDIR / f"{name}.{ext}", dpi=200, bbox_inches="tight")
    plt.close(fig)


def fig5_best_of_k():
    fig, ax = plt.subplots(figsize=(6, 4.2))
    for label, ys in BOK.items():
        c, mk, ls = STYLE[label]
        ax.plot(K, ys, marker=mk, ls=ls, color=c, lw=1.8, ms=5, label=label)
    ax.axhline(76, color="crimson", ls=":", lw=1, alpha=0.7)
    ax.annotate("grounded ceiling ~76%", (10, 76), xytext=(6.2, 79),
                fontsize=8, color="crimson")
    ax.set_xlabel("Blind best-of-k budget (draws)")
    ax.set_ylabel("Strict quotation rate (%)")
    ax.set_xticks(K); ax.set_ylim(30, 85)
    ax.legend(fontsize=8, loc="center right"); ax.grid(alpha=0.3)
    save(fig, "fig5_best_of_k")


def fig7_retrieval_ladder():
    labels = ["C1\n(no window)", "BM25-RAG\n(lexical)", "dense-RAG\n(semantic)", "C3 oracle\nwindow"]
    vals = [19, 27, 37, 78]
    colors = ["#cccccc", "#9ecae1", "#4292c6", "#08519c"]
    fig, ax = plt.subplots(figsize=(5.6, 4))
    bars = ax.bar(range(4), vals, color=colors, width=0.62)
    for i, v in enumerate(vals):
        ax.annotate(f"{v}%", (i, v + 1.5), ha="center", fontsize=9)
    ax.set_xticks(range(4)); ax.set_xticklabels(labels, fontsize=8.5)
    ax.set_ylabel("Corpus-correct rate (%)"); ax.set_ylim(0, 88)
    ax.grid(axis="y", alpha=0.3)
    save(fig, "fig7_retrieval_ladder")


if __name__ == "__main__":
    fig5_best_of_k()
    fig7_retrieval_ladder()
    print(f"figures -> {FIGDIR} (fig5_best_of_k, fig7_retrieval_ladder .png/.pdf)")
