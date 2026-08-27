"""Paper-level inferential analysis for the formal run.

Outputs:
- cluster-bootstrap condition rates and contrasts
- GEE logistic models clustered by task
- error/bucket distributions
- a compact markdown result report
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
import yaml

ROOT = Path(__file__).resolve().parents[1]
CONDITIONS = ["C1", "C2", "C3", "C4"]
CONTRASTS = [
    ("C4-C1", "C4", "C1"),
    ("C3-C1", "C3", "C1"),
    ("C2-C1", "C2", "C1"),
    ("C4-C2", "C4", "C2"),
    ("C4-C3", "C4", "C3"),
]


def load_task_meta() -> dict[str, dict]:
    out = {}
    for path in (ROOT / "tasks").glob("TGU*_T*.yaml"):
        task = yaml.safe_load(path.read_text(encoding="utf-8"))
        out[task["task_id"]] = {
            "task_type": task["task_type"],
            "task_type_label": task.get("task_type_label", task["task_type"]),
            "work_id": task["work_id"],
            "work_title": task["work_title"],
            "genre": task["genre"],
        }
    return out


def load_rows(path: Path) -> pd.DataFrame:
    task_meta = load_task_meta()
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        judge = rec.get("judge", {})
        meta = task_meta.get(rec["task_id"], {})
        rows.append(
            {
                "run_id": rec["run_id"],
                "model": rec["model"],
                "condition": rec["condition"],
                "task_id": rec["task_id"],
                "variant": rec["variant"],
                "repetition": rec["repetition"],
                "task_type": meta.get("task_type"),
                "work_id": meta.get("work_id"),
                "work_title": meta.get("work_title"),
                "genre": meta.get("genre"),
                "strict": int(bool(judge.get("strict_correct"))),
                "defensible": int(bool(judge.get("defensible_correct"))),
                "bucket": judge.get("bucket"),
                "error_class_candidate": judge.get("error_class_candidate") or "none",
                "latency_api_s": rec.get("latency_s", {}).get("api"),
            }
        )
    df = pd.DataFrame(rows)
    df["grounding"] = df["condition"].isin(["C3", "C4"]).astype(int)
    df["structure"] = df["condition"].isin(["C2", "C4"]).astype(int)
    return df


def rate_table(df: pd.DataFrame, outcome: str, keys: list[str]) -> pd.DataFrame:
    group = df.groupby(keys, dropna=False)[outcome].agg(["sum", "count"]).reset_index()
    group = group.rename(columns={"sum": "correct", "count": "n"})
    group["rate"] = group["correct"] / group["n"]
    return group


def cluster_bootstrap(df: pd.DataFrame, outcome: str, b: int, seed: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    tasks = sorted(df["task_id"].unique())
    task_groups = {task: df[df["task_id"] == task] for task in tasks}

    rate_draws = {condition: [] for condition in CONDITIONS}
    contrast_draws = {name: [] for name, _, _ in CONTRASTS}

    for _ in range(b):
        sampled_tasks = rng.choice(tasks, size=len(tasks), replace=True)
        boot = pd.concat([task_groups[task] for task in sampled_tasks], ignore_index=True)
        rates = boot.groupby("condition")[outcome].mean().to_dict()
        for condition in CONDITIONS:
            rate_draws[condition].append(rates.get(condition, np.nan))
        for name, hi, lo in CONTRASTS:
            contrast_draws[name].append(rates.get(hi, np.nan) - rates.get(lo, np.nan))

    point_rates = df.groupby("condition")[outcome].agg(["sum", "count", "mean"]).reindex(CONDITIONS)
    rate_rows = []
    for condition in CONDITIONS:
        draws = np.asarray(rate_draws[condition], dtype=float)
        rate_rows.append(
            {
                "outcome": outcome,
                "condition": condition,
                "n": int(point_rates.loc[condition, "count"]),
                "correct": int(point_rates.loc[condition, "sum"]),
                "rate": float(point_rates.loc[condition, "mean"]),
                "ci_low": float(np.nanpercentile(draws, 2.5)),
                "ci_high": float(np.nanpercentile(draws, 97.5)),
            }
        )

    point_condition = df.groupby("condition")[outcome].mean().to_dict()
    contrast_rows = []
    for name, hi, lo in CONTRASTS:
        draws = np.asarray(contrast_draws[name], dtype=float)
        contrast_rows.append(
            {
                "outcome": outcome,
                "contrast": name,
                "delta": float(point_condition[hi] - point_condition[lo]),
                "ci_low": float(np.nanpercentile(draws, 2.5)),
                "ci_high": float(np.nanpercentile(draws, 97.5)),
            }
        )

    return pd.DataFrame(rate_rows), pd.DataFrame(contrast_rows)


def fit_gee(df: pd.DataFrame, outcome: str) -> pd.DataFrame:
    model = smf.gee(
        f"{outcome} ~ grounding + structure + grounding:structure + C(model)",
        groups="task_id",
        data=df,
        family=sm.families.Binomial(),
        cov_struct=sm.cov_struct.Exchangeable(),
    )
    result = model.fit()
    ci = result.conf_int()
    rows = []
    for term in result.params.index:
        coef = float(result.params[term])
        rows.append(
            {
                "outcome": outcome,
                "term": term,
                "coef": coef,
                "se": float(result.bse[term]),
                "p_value": float(result.pvalues[term]),
                "odds_ratio": float(np.exp(coef)),
                "or_ci_low": float(np.exp(ci.loc[term, 0])),
                "or_ci_high": float(np.exp(ci.loc[term, 1])),
            }
        )
    return pd.DataFrame(rows)


def write_csv(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def bucket_tables(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    bucket = (
        df.groupby(["condition", "bucket"]).size().rename("n").reset_index()
    )
    bucket["share_within_condition"] = bucket["n"] / bucket.groupby("condition")["n"].transform("sum")

    failed = df[~df["strict"].astype(bool)].copy()
    error = (
        failed.groupby(["condition", "error_class_candidate"]).size().rename("n").reset_index()
    )
    error["share_within_failed"] = error["n"] / error.groupby("condition")["n"].transform("sum")
    return bucket, error


def markdown_report(
    outdir: Path,
    df: pd.DataFrame,
    strict_rates: pd.DataFrame,
    strict_contrasts: pd.DataFrame,
    gee_strict: pd.DataFrame,
) -> None:
    bucket_counts = Counter(df["bucket"])
    condition_lines = []
    for row in strict_rates.itertuples(index=False):
        condition_lines.append(
            f"| {row.condition} | {row.n} | {row.correct} | {row.rate:.3f} | [{row.ci_low:.3f}, {row.ci_high:.3f}] |"
        )
    contrast_lines = []
    for row in strict_contrasts.itertuples(index=False):
        contrast_lines.append(
            f"| {row.contrast} | {row.delta:.3f} | [{row.ci_low:.3f}, {row.ci_high:.3f}] |"
        )
    gee_terms = gee_strict[gee_strict["term"].isin(["grounding", "structure", "grounding:structure"])]
    gee_lines = []
    for row in gee_terms.itertuples(index=False):
        gee_lines.append(
            f"| {row.term} | {row.odds_ratio:.3f} | [{row.or_ci_low:.3f}, {row.or_ci_high:.3f}] | {row.p_value:.4g} |"
        )

    text = f"""# Stage 3 Formal Analysis Report

## Coverage

- Records: {len(df)}
- Unique run IDs: {df['run_id'].nunique()}
- Buckets: {dict(bucket_counts)}

## Strict Correctness by Condition

| condition | n | correct | rate | cluster bootstrap 95% CI |
|---|---:|---:|---:|---:|
{chr(10).join(condition_lines)}

## Strict-Correctness Contrasts

| contrast | delta | cluster bootstrap 95% CI |
|---|---:|---:|
{chr(10).join(contrast_lines)}

## GEE Logistic Model, Strict Correctness

| term | odds ratio | robust 95% CI | p |
|---|---:|---:|---:|
{chr(10).join(gee_lines)}

## Interpretation

Grounding improves strict quotation fidelity relative to the improvised baseline, but the full TGU template does not outperform grounded-only prompting in this run. The C4-C3 contrast is negative and should be reported as a real result, not repaired after the fact.

"""
    (outdir / "stage3_analysis_report.md").write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jsonl", type=Path, default=ROOT / "runs" / "raw" / "formal" / "formal.jsonl")
    parser.add_argument("--outdir", type=Path, default=ROOT / "runs" / "raw" / "formal" / "tables")
    parser.add_argument("--bootstrap", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=20260611)
    args = parser.parse_args()

    df = load_rows(args.jsonl)
    args.outdir.mkdir(parents=True, exist_ok=True)
    write_csv(args.outdir / "analysis_dataset.csv", df)

    all_rates = []
    all_contrasts = []
    all_gee = []
    for outcome in ("strict", "defensible"):
        rates, contrasts = cluster_bootstrap(df, outcome, args.bootstrap, args.seed)
        all_rates.append(rates)
        all_contrasts.append(contrasts)
        all_gee.append(fit_gee(df, outcome))

    rates_df = pd.concat(all_rates, ignore_index=True)
    contrasts_df = pd.concat(all_contrasts, ignore_index=True)
    gee_df = pd.concat(all_gee, ignore_index=True)
    write_csv(args.outdir / "bootstrap_condition_rates.csv", rates_df)
    write_csv(args.outdir / "bootstrap_condition_contrasts.csv", contrasts_df)
    write_csv(args.outdir / "gee_logistic.csv", gee_df)

    by_task_type = rate_table(df, "strict", ["task_type", "condition"])
    by_model_condition = rate_table(df, "strict", ["model", "condition"])
    write_csv(args.outdir / "strict_by_task_type_condition.csv", by_task_type)
    write_csv(args.outdir / "strict_by_model_condition.csv", by_model_condition)

    bucket, error = bucket_tables(df)
    write_csv(args.outdir / "bucket_distribution_by_condition.csv", bucket)
    write_csv(args.outdir / "error_candidate_distribution_by_condition.csv", error)

    markdown_report(
        args.outdir,
        df,
        rates_df[rates_df["outcome"] == "strict"],
        contrasts_df[contrasts_df["outcome"] == "strict"],
        gee_df[gee_df["outcome"] == "strict"],
    )
    print(f"wrote inferential analysis outputs to {args.outdir}")


if __name__ == "__main__":
    main()

