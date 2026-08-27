from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
TABLE_DIR = ROOT / "runs" / "raw" / "formal" / "tables"
FIG_DIR = ROOT / "figures"


def save_condition_correctness() -> None:
    rates = pd.read_csv(TABLE_DIR / "bootstrap_condition_rates.csv")
    strict = rates[rates["outcome"] == "strict"].copy()
    strict["label"] = strict["condition"].map(
        {
            "C1": "C1\nImprovised",
            "C2": "C2\nStructured",
            "C3": "C3\nGrounded",
            "C4": "C4\nGrounded+\nTGU",
        }
    )
    y = strict["rate"].to_numpy()
    yerr = [
        (strict["rate"] - strict["ci_low"]).to_numpy(),
        (strict["ci_high"] - strict["rate"]).to_numpy(),
    ]

    fig, ax = plt.subplots(figsize=(6.2, 3.8), dpi=200)
    colors = ["#6f6f6f", "#4c78a8", "#59a14f", "#f28e2b"]
    ax.bar(strict["label"], y, color=colors, edgecolor="#222222", linewidth=0.8)
    ax.errorbar(
        strict["label"],
        y,
        yerr=yerr,
        fmt="none",
        ecolor="#222222",
        elinewidth=1.2,
        capsize=4,
    )
    ax.set_ylim(0, 0.72)
    ax.set_ylabel("Strict correctness")
    ax.set_title("Quotation/source correctness by prompting condition")
    ax.grid(axis="y", color="#dddddd", linewidth=0.7)
    ax.set_axisbelow(True)
    for i, value in enumerate(y):
        ax.text(i, value + 0.02, f"{value:.1%}", ha="center", va="bottom", fontsize=9)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig1_condition_correctness.png", bbox_inches="tight", dpi=300)
    fig.savefig(FIG_DIR / "fig1_condition_correctness.pdf", bbox_inches="tight")
    plt.close(fig)


def save_error_shift() -> None:
    errors = pd.read_csv(TABLE_DIR / "error_candidate_distribution_by_condition.csv")
    pivot = (
        errors.pivot(
            index="condition",
            columns="error_class_candidate",
            values="share_within_failed",
        )
        .fillna(0.0)
        .loc[["C1", "C2", "C3", "C4"]]
    )
    cols = [
        "fabricated_quotation",
        "context_displacement",
        "misattribution",
        "version_drift",
        "format_failure",
    ]
    labels = {
        "fabricated_quotation": "Fabricated quote",
        "context_displacement": "Context displacement",
        "misattribution": "Misattribution",
        "version_drift": "Version drift",
        "format_failure": "Format failure",
    }
    colors = {
        "fabricated_quotation": "#d95f02",
        "context_displacement": "#1b9e77",
        "misattribution": "#7570b3",
        "version_drift": "#e7298a",
        "format_failure": "#666666",
    }

    fig, ax = plt.subplots(figsize=(6.4, 3.9), dpi=200)
    bottom = [0.0] * len(pivot)
    for col in cols:
        values = pivot[col].to_numpy()
        ax.bar(
            pivot.index,
            values,
            bottom=bottom,
            label=labels[col],
            color=colors[col],
            edgecolor="white",
            linewidth=0.6,
        )
        bottom = [b + v for b, v in zip(bottom, values)]

    ax.set_ylim(0, 1.0)
    ax.set_ylabel("Share among strict-failed generations")
    ax.set_title("Grounding shifts failures from fabrication to context")
    ax.grid(axis="y", color="#dddddd", linewidth=0.7)
    ax.set_axisbelow(True)
    ax.legend(ncol=2, fontsize=8, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.14))
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig2_error_shift.png", bbox_inches="tight", dpi=300)
    fig.savefig(FIG_DIR / "fig2_error_shift.pdf", bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    save_condition_correctness()
    save_error_shift()
    print(f"wrote figures to {FIG_DIR}")


if __name__ == "__main__":
    main()
