"""生成手稿主图（P0-4）：把 headline 从 GEE OR 转到任务层效应与稳健性可视化。
Fig1 任务层配对差(grounded−ungrounded k0)；Fig2 四模型 C1→C3 提升；
Fig3 错误认识论可修复性；Fig4 F3 存活曲线。数据直算自 runs/raw/ext_e1c_*。
标签全英文（避免 CJK 字体问题）。输出 figures/fig{1..4}.{png,pdf}。
用法：python journal_extension/make_figures.py
"""
from __future__ import annotations

import json
import random
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
FIGDIR = ROOT / "figures"
DEV = {"TGU2", "TGU4"}
TAGS = ["e1c_m2", "e1c_m3", "e1c_m4", "e1c_m1"]


def load():
    rows = []
    for tag in TAGS:
        p = ROOT / "runs" / "raw" / f"ext_{tag}" / f"{tag}.jsonl"
        if p.exists():
            rows += [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    return [r for r in rows if r["arm"] == "F3"]


def conf(r):
    return r["task_id"].split("_")[0] not in DEV


def save(fig, name):
    FIGDIR.mkdir(exist_ok=True)
    for ext in ("png", "pdf"):
        fig.savefig(FIGDIR / f"{name}.{ext}", dpi=200, bbox_inches="tight")
    plt.close(fig)


def fig1_task_lift(rows):
    """每 confirmatory 任务：grounded(C3C4) − ungrounded(C1C2) k0 strict 差。"""
    by = defaultdict(lambda: {"g": [], "u": []})
    for r in rows:
        if not conf(r):
            continue
        (by[r["task_id"]]["g" if r["condition"] in ("C3", "C4") else "u"]).append(int(r["k0_strict"]))
    tasks, lifts = [], []
    for t, d in by.items():
        if d["g"] and d["u"]:
            tasks.append(t)
            lifts.append(100 * (sum(d["g"]) / len(d["g"]) - sum(d["u"]) / len(d["u"])))
    order = sorted(range(len(tasks)), key=lambda i: lifts[i])
    tasks = [tasks[i] for i in order]; lifts = [lifts[i] for i in order]
    fig, ax = plt.subplots(figsize=(6, 4.2))
    ax.barh(range(len(tasks)), lifts, color="#2b7bba")
    ax.set_yticks(range(len(tasks))); ax.set_yticklabels(tasks, fontsize=8)
    ax.axvline(sum(lifts) / len(lifts), color="crimson", ls="--", lw=1.2,
               label=f"mean +{sum(lifts)/len(lifts):.0f}pp")
    ax.set_xlabel("Grounded − ungrounded strict rate (pp)")
    ax.legend(fontsize=8); ax.grid(axis="x", alpha=0.3)
    save(fig, "fig1_task_lift")


def fig2_model_direction(rows):
    """四模型 C1 vs C3 k0 strict（confirmatory）。"""
    by = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    for r in rows:
        if not conf(r) or r["condition"] not in ("C1", "C3"):
            continue
        by[r["model"]][r["condition"]][0] += 1
        by[r["model"]][r["condition"]][1] += int(r["k0_strict"])
    models = ["M2", "M3", "M4", "M1"]
    models = [m for m in models if m in by and by[m]["C1"][0] and by[m]["C3"][0]]
    c1 = [100 * by[m]["C1"][1] / by[m]["C1"][0] for m in models]
    c3 = [100 * by[m]["C3"][1] / by[m]["C3"][0] for m in models]
    x = range(len(models)); w = 0.35
    fig, ax = plt.subplots(figsize=(5.5, 4))
    ax.bar([i - w / 2 for i in x], c1, w, label="C1 (no source)", color="#bbbbbb")
    ax.bar([i + w / 2 for i in x], c3, w, label="C3 (grounded)", color="#2b7bba")
    for i in x:
        ax.annotate(f"+{c3[i]-c1[i]:.0f}", (i, max(c1[i], c3[i]) + 2), ha="center", fontsize=8, color="crimson")
    ax.set_xticks(list(x)); ax.set_xticklabels(models)
    ax.set_ylabel("Strict quotation rate (%)"); ax.set_ylim(0, 105)
    ax.legend(fontsize=8); ax.grid(axis="y", alpha=0.3)
    save(fig, "fig2_model_direction")


def fig3_repairability(rows):
    """按初始错误类别的 F3 修复率（grounded 条件池化，k0 失败组内）。"""
    by = defaultdict(lambda: [0, 0])
    for r in rows:
        if not conf(r) or r["k0_strict"] or r["condition"] == "C1":
            continue
        ec = r["rounds"][0]["judge"].get("error_class_candidate") or "unknown"
        by[ec][0] += 1; by[ec][1] += int(r["final_strict"])
    order = ["format_failure", "version_drift", "misattribution", "fabricated_quotation", "context_displacement"]
    order = [e for e in order if e in by]
    rates = [100 * by[e][1] / by[e][0] for e in order]
    ns = [by[e][0] for e in order]
    fig, ax = plt.subplots(figsize=(6.2, 4))
    bars = ax.bar(range(len(order)), rates, color="#5aa469")
    for i, (rt, n) in enumerate(zip(rates, ns)):
        ax.annotate(f"{rt:.0f}%\n(n={n})", (i, rt + 1.5), ha="center", fontsize=8)
    ax.set_xticks(range(len(order)))
    ax.set_xticklabels([e.replace("_", "\n") for e in order], fontsize=8)
    ax.set_ylabel("F3 repair rate (%)"); ax.set_ylim(0, max(rates) + 12)
    ax.grid(axis="y", alpha=0.3)
    save(fig, "fig3_repairability")


def fig4_survival(rows):
    """F3 存活：confirmatory k0 失败组，累计修复率 by round 1/2/3。"""
    fails = [r for r in rows if conf(r) and not r["k0_strict"]]
    n = len(fails)
    cum = []
    for k in (1, 2, 3):
        fixed = sum(1 for r in fails if any(rd["judge"].get("strict_correct") for rd in r["rounds"][1:k + 1]))
        cum.append(100 * fixed / n)
    fig, ax = plt.subplots(figsize=(5, 3.8))
    ax.plot([0, 1, 2, 3], [0] + cum, marker="o", color="#2b7bba", lw=2)
    for k, v in zip((1, 2, 3), cum):
        ax.annotate(f"+{v:.0f}%", (k, v + 1), ha="center", fontsize=8)
    ax.set_xticks([0, 1, 2, 3]); ax.set_xlabel("Repair round k")
    ax.set_ylabel("Cumulative repaired (%)")
    ax.grid(alpha=0.3)
    save(fig, "fig4_survival")


def main():
    rows = load()
    fig1_task_lift(rows)
    fig2_model_direction(rows)
    fig3_repairability(rows)
    fig4_survival(rows)
    print(f"figures -> {FIGDIR} (fig1..4 .png/.pdf), from {len(rows)} F3 records")


if __name__ == "__main__":
    main()
