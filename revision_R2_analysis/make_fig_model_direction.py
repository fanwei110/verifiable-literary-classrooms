"""重画正文 Fig. 3（逐模型 C1→C3 提升）（回应 R3.2）。

R1 版本的增幅标签放在两柱较高者上方，M3 柱最矮，导致标签纵向顺序（+55, +45, +37）
与模型顺序（M2, M3, M4）不一致，容易被误读。数值本身无误。本版：
标签带模型前缀、置于统一高度；只画有完整 C1/C3 对比的三个模型（M1 未运行 C1）。
数据直算自主样本，与 Table 3 同源。输出 out/figures/fig2_model_direction.pdf/png。
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

import r2_common as C  # noqa: E402

OUT = Path(__file__).resolve().parent / "out" / "figures"


def main() -> None:
    C.utf8_stdout()
    by = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    for r in C.load_primary():
        if r["condition"] in ("C1", "C3"):
            by[r["model"]][r["condition"]][0] += 1
            by[r["model"]][r["condition"]][1] += int(r["k0_strict"])
    models = [m for m in ("M2", "M3", "M4") if by[m]["C1"][0] and by[m]["C3"][0]]
    c1 = [100 * by[m]["C1"][1] / by[m]["C1"][0] for m in models]
    c3 = [100 * by[m]["C3"][1] / by[m]["C3"][0] for m in models]
    x = range(len(models))
    w = 0.35
    fig, ax = plt.subplots(figsize=(5.5, 4))
    ax.bar([i - w / 2 for i in x], c1, w, label="C1 (no source)", color="#bbbbbb")
    ax.bar([i + w / 2 for i in x], c3, w, label="C3 (grounded)", color="#2b7bba")
    for i, m in zip(x, models):
        ax.text(i, 88, f"{m}: +{c3[i] - c1[i]:.0f}pp", ha="center", fontsize=9, color="crimson")
    ax.set_xticks(list(x))
    ax.set_xticklabels(models)
    ax.set_ylabel("Strict quotation rate (%)")
    ax.set_ylim(0, 100)
    ax.legend(fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.1), ncol=2, frameon=False)
    ax.grid(axis="y", alpha=0.3)
    OUT.mkdir(parents=True, exist_ok=True)
    for ext in ("pdf", "png"):
        fig.savefig(OUT / f"fig2_model_direction.{ext}", dpi=200, bbox_inches="tight")
    plt.close(fig)
    print({m: (round(a, 1), round(b, 1), round(b - a, 1)) for m, a, b in zip(models, c1, c3)})


if __name__ == "__main__":
    main()
