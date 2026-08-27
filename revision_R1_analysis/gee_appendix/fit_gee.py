# -*- coding: utf-8 -*-
"""R1.3 · 重构正文 GEE 并固化 Appendix A / Table A1（零 API）。

背景：审稿人 R1.3 指出正文承诺 "full GEE coefficient table ... in the appendix" 但附录不存在。
首投复现包中的 runs/raw/formal/tables/gee_logistic.csv 对应旧的 2,160 冻结网格
(grounding OR=1.69)，与正文报告的 1,319 条确认性样本 (OR=7.24) 不是同一分析，
因此必须从确认性日志重建可复现的拟合链。

分析样本（与正文完全一致）：
  runs/raw/ext_e1c_m{1,2,3,4}/*.jsonl 中 arm == "F3" 的 k=0 记录，
  排除开发集 TGU2/TGU4 → 1,319 观测、12 个 task cluster。

模型：GEE，Binomial family，logit link，exchangeable working correlation，
      cluster = task_id；结果变量 = k0_strict。
设计：grounding (C3/C4=1)、structure (C2/C4=1)、grounding×structure、model 哑元。

用法：python revision_R1/new_analysis/gee_appendix/fit_gee.py
输出：results_table.csv / table_a1.tex / gee_report.md（同目录）
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
DEV = {"TGU2", "TGU4"}
TAGS = ["e1c_m1", "e1c_m2", "e1c_m3", "e1c_m4"]
# 参考组 = M1。经排查确认：原分析采用按模型标识排序后的默认参考组（M1），
# 该设定可精确复现正文全部已报数字（含 model term M4 OR=1.71, p=0.04）；
# 若改用 M2 为参考组，grounding/structure/interaction 不变，但 model 项数值会改变。
REF_MODEL = "M1"


def load() -> pd.DataFrame:
    recs = []
    for tag in TAGS:
        p = ROOT / "runs" / "raw" / f"ext_{tag}" / f"{tag}.jsonl"
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("arm") != "F3":
                continue
            if r["task_id"].split("_")[0] in DEV:
                continue
            recs.append(
                {
                    "model": r["model"],
                    "condition": r["condition"],
                    "task_id": r["task_id"],
                    "y": int(bool(r["k0_strict"])),
                }
            )
    df = pd.DataFrame(recs)
    df["grounding"] = df["condition"].isin(["C3", "C4"]).astype(int)
    df["structure"] = df["condition"].isin(["C2", "C4"]).astype(int)
    df["g_x_s"] = df["grounding"] * df["structure"]
    for m in sorted(df["model"].unique()):
        if m != REF_MODEL:
            df[f"is_{m}"] = (df["model"] == m).astype(int)
    return df


def fit(df: pd.DataFrame):
    cols = ["grounding", "structure", "g_x_s"] + [
        c for c in df.columns if c.startswith("is_")
    ]
    X = sm.add_constant(df[cols].astype(float), has_constant="add")
    model = sm.GEE(
        df["y"].astype(float),
        X,
        groups=df["task_id"],
        family=sm.families.Binomial(),
        cov_struct=sm.cov_struct.Exchangeable(),
    )
    return model.fit(), cols


def cluster_bootstrap(df: pd.DataFrame, cols, n_boot=2000, seed=20260823):
    """任务聚类（case/pairs）自助：整簇重抽后重拟合，给系数的经验分位区间。

    正文原先笼统称 'wild-cluster bootstrap'；项目中未发现该实现。此处改为
    实际执行、可复现的 task-cluster case bootstrap，并据此修正正文表述。
    """
    rng = np.random.default_rng(seed)
    tasks = df["task_id"].unique()
    by_task = {t: df[df["task_id"] == t] for t in tasks}
    draws = []
    for _ in range(n_boot):
        pick = rng.choice(tasks, size=len(tasks), replace=True)
        parts = []
        for i, t in enumerate(pick):
            d = by_task[t].copy()
            d["task_id"] = f"{t}__b{i}"  # 保证重复簇被视为独立簇
            parts.append(d)
        bs = pd.concat(parts, ignore_index=True)
        try:
            X = sm.add_constant(bs[cols].astype(float), has_constant="add")
            res = sm.GEE(
                bs["y"].astype(float),
                X,
                groups=bs["task_id"],
                family=sm.families.Binomial(),
                cov_struct=sm.cov_struct.Exchangeable(),
            ).fit()
            draws.append(res.params.reindex(["const"] + cols).values)
        except Exception:
            continue
    arr = np.array([d for d in draws if not np.isnan(d).any()])
    lo = np.percentile(arr, 2.5, axis=0)
    hi = np.percentile(arr, 97.5, axis=0)
    return arr.shape[0], lo, hi


LABELS = {
    "const": "Intercept (reference: M1, ungrounded/unstructured cell)",
    "grounding": "Grounding (C3/C4 vs C1/C2)",
    "structure": "Structure (C2/C4 vs C1/C3)",
    "g_x_s": "Grounding x Structure",
    "is_M2": "Model M2 (DeepSeek-chat) vs M1",
    "is_M3": "Model M3 (Qwen3-235B) vs M1",
    "is_M4": "Model M4 (DeepSeek-reasoner) vs M1",
}


def main():
    df = load()
    res, cols = fit(df)
    order = ["const"] + cols

    p = res.params.reindex(order)
    se = res.bse.reindex(order)
    pv = res.pvalues.reindex(order)
    ci = res.conf_int().reindex(order)

    nb, blo, bhi = cluster_bootstrap(df, cols)

    tab = pd.DataFrame(
        {
            "term": [LABELS.get(k, k) for k in order],
            "beta": p.values,
            "SE": se.values,
            "OR": np.exp(p.values),
            "OR_CI_low": np.exp(ci[0].values),
            "OR_CI_high": np.exp(ci[1].values),
            "p": pv.values,
            "boot_OR_CI_low": np.exp(blo),
            "boot_OR_CI_high": np.exp(bhi),
        }
    )
    tab.to_csv(OUT / "results_table.csv", index=False, encoding="utf-8")

    # ---- 导出确认性分析样本（1,319 obs / 12 clusters）----
    # 附录 A 的每一格都由这张表拟合而来；导出它是为了让审稿人无需重跑
    # 即可核对 n、簇数与每条观测的来源，也便于第三方用其他软件复算。
    sample_cols = ["task_id", "model", "condition", "grounding", "structure", "g_x_s", "y"]
    df[sample_cols].to_csv(OUT / "analysis_sample.csv", index=False, encoding="utf-8")


    # ---- LaTeX Table A1 ----
    lines = []
    for _, r in tab.iterrows():
        pstr = f"{r['p']:.3f}" if r["p"] >= 1e-3 else f"{r['p']:.1e}"
        lines.append(
            f"{r['term']} & {r['beta']:.3f} & {r['SE']:.3f} & {r['OR']:.2f} & "
            f"[{r['OR_CI_low']:.2f}, {r['OR_CI_high']:.2f}] & {pstr} & "
            f"[{r['boot_OR_CI_low']:.2f}, {r['boot_OR_CI_high']:.2f}] \\\\"
        )
    (OUT / "table_a1_rows.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # ---- 复现校验 ----
    g = tab[tab["term"].str.startswith("Grounding (")].iloc[0]
    s = tab[tab["term"].str.startswith("Structure (")].iloc[0]
    x = tab[tab["term"].str.startswith("Grounding x")].iloc[0]
    m4 = tab[tab["term"].str.startswith("Model M4")].iloc[0]
    checks = [
        ("grounding OR", g["OR"], 7.24, 0.05),
        ("grounding CI low", g["OR_CI_low"], 2.29, 0.05),
        ("grounding CI high", g["OR_CI_high"], 22.86, 0.5),
        ("structure OR", s["OR"], 1.28, 0.05),
        ("structure p", s["p"], 0.23, 0.02),
        ("interaction OR", x["OR"], 0.86, 0.05),
        ("interaction p", x["p"], 0.53, 0.03),
        ("M4 OR", m4["OR"], 1.71, 0.05),
        ("M4 p", m4["p"], 0.04, 0.02),
    ]
    md = [
        "# Appendix A · GEE 重构与复现校验（R1.3）",
        "",
        f"- 分析样本：{len(df)} 观测，{df['task_id'].nunique()} 个 task cluster（confirmatory，排除 dev TGU2/TGU4）",
        f"- 模型：GEE binomial/logit，exchangeable working correlation，cluster = task_id；参考组 = {REF_MODEL}，C1（ungrounded, unstructured）",
        f"- 任务聚类 case bootstrap：{nb}/2000 次成功重拟合（整簇重抽）",
        "",
        "## 与正文已报数字的复现校验",
        "",
        "| 量 | 重构值 | 正文值 | 容差 | 判定 |",
        "|---|---|---|---|---|",
    ]
    allok = True
    for name, got, want, tol in checks:
        ok = abs(got - want) <= tol
        allok &= ok
        md.append(f"| {name} | {got:.4g} | {want} | ±{tol} | {'✅' if ok else '❌'} |")
    md += ["", f"**总体判定：{'全部复现一致 ✅' if allok else '存在不一致 ❌ 需排查'}**", "",
           "## 完整系数表", "", tab.to_markdown(index=False, floatfmt=".4g")]
    (OUT / "gee_report.md").write_text("\n".join(md), encoding="utf-8")

    print(f"n={len(df)} clusters={df['task_id'].nunique()} bootstrap_ok={nb}")
    print(tab[["term", "OR", "OR_CI_low", "OR_CI_high", "p"]].to_string(index=False))
    print("\n复现校验：")
    for name, got, want, tol in checks:
        print(f"  {'OK ' if abs(got-want)<=tol else 'FAIL'} {name}: {got:.4g} vs 正文 {want}")


if __name__ == "__main__":
    main()
