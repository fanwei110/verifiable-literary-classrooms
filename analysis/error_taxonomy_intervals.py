"""Error-taxonomy descriptive intervals for the formal verifiable-classroom run.

The formal judge assigns one candidate error class to each non-strict
generation. This script deliberately treats those labels as descriptive
mechanism evidence rather than as a confirmatory endpoint. It reports:

* candidate error shares among strict-failed generations;
* mechanically confirmed lower-bound shares based on the judge's match details;
* task-cluster bootstrap confidence intervals for the candidate shares.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from collections import defaultdict
from pathlib import Path
from statistics import quantiles

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_JSONL = ROOT / "runs" / "raw" / "formal" / "formal.jsonl"
DEFAULT_OUTDIR = ROOT / "runs" / "raw" / "formal" / "tables"

ERROR_CLASSES = (
    "fabricated_quotation",
    "context_displacement",
    "misattribution",
    "version_drift",
    "format_failure",
)


def load_rows(path: Path) -> list[dict]:
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    k = (len(values) - 1) * p
    lo = int(k)
    hi = min(lo + 1, len(values) - 1)
    frac = k - lo
    return values[lo] * (1 - frac) + values[hi] * frac


def is_strict_failure(row: dict) -> bool:
    return not bool(row.get("judge", {}).get("strict_correct"))


def candidate_class(row: dict) -> str:
    judge = row.get("judge", {})
    bucket = judge.get("bucket")
    if bucket == "format_failure":
        return "format_failure"
    return judge.get("error_class_candidate") or "format_failure"


def mechanically_confirmed(row: dict, error_class: str) -> bool:
    """Return whether the row contains deterministic evidence for the class.

    The automated class is still a candidate class. The lower-bound count below
    only includes rows where the stored match details expose a direct mechanical
    predicate for the same class.
    """

    judge = row.get("judge", {})
    details = judge.get("match_details") or []
    if error_class == "format_failure":
        return judge.get("bucket") == "format_failure"
    if not details:
        return False
    if error_class == "fabricated_quotation":
        return any(d.get("quote_found") is False and float(d.get("approx_score", 0.0)) < 0.72 for d in details)
    if error_class == "version_drift":
        return any(d.get("quote_found") is False and float(d.get("approx_score", 0.0)) >= 0.72 for d in details)
    if error_class == "misattribution":
        return any(
            d.get("quote_found") is True
            and (d.get("claimed_author_ok") is False or d.get("claimed_work_ok") is False)
            for d in details
        )
    if error_class == "context_displacement":
        return any(
            d.get("quote_found") is True
            and (
                d.get("locator_ok") is False
                or d.get("speaker_ok") is False
                or d.get("grounded_ok") is False
            )
            for d in details
        )
    return False


def share_for(rows: list[dict], error_class: str) -> float:
    failed = [row for row in rows if is_strict_failure(row)]
    if not failed:
        return 0.0
    return sum(1 for row in failed if candidate_class(row) == error_class) / len(failed)


def cluster_bootstrap_ci(rows: list[dict], error_class: str, reps: int, seed: int) -> tuple[float, float]:
    by_task: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_task[row["task_id"]].append(row)
    task_ids = sorted(by_task)
    if not task_ids:
        return 0.0, 0.0
    rng = random.Random(seed)
    draws: list[float] = []
    for _ in range(reps):
        sampled: list[dict] = []
        for task_id in (rng.choice(task_ids) for _ in task_ids):
            sampled.extend(by_task[task_id])
        draws.append(share_for(sampled, error_class))
    return percentile(draws, 0.025), percentile(draws, 0.975)


def build_table(rows: list[dict], reps: int, seed: int) -> list[dict]:
    by_condition: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_condition[row["condition"]].append(row)

    output: list[dict] = []
    for condition in sorted(by_condition):
        condition_rows = by_condition[condition]
        failures = [row for row in condition_rows if is_strict_failure(row)]
        failure_n = len(failures)
        for error_class in ERROR_CLASSES:
            candidate_n = sum(1 for row in failures if candidate_class(row) == error_class)
            mechanical_n = sum(
                1
                for row in failures
                if candidate_class(row) == error_class and mechanically_confirmed(row, error_class)
            )
            ci_low, ci_high = cluster_bootstrap_ci(condition_rows, error_class, reps, seed)
            output.append(
                {
                    "condition": condition,
                    "error_class_candidate": error_class,
                    "strict_failure_n": failure_n,
                    "candidate_n": candidate_n,
                    "candidate_share": f"{candidate_n / failure_n:.4f}" if failure_n else "0.0000",
                    "mechanically_confirmed_n": mechanical_n,
                    "mechanical_lower_bound_share": f"{mechanical_n / failure_n:.4f}" if failure_n else "0.0000",
                    "task_cluster_bootstrap_ci_low": f"{ci_low:.4f}",
                    "task_cluster_bootstrap_ci_high": f"{ci_high:.4f}",
                    "interpretation": "automated candidate class; descriptive mechanism evidence only",
                }
            )
    return output


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(path: Path, rows: list[dict]) -> None:
    lines = [
        "# Error Taxonomy Intervals",
        "",
        "Error classes are automated candidate classes. Shares are descriptive and should be interpreted as mechanically verifiable lower-bound/interval evidence rather than manually adjudicated prevalence estimates.",
        "",
        "| Condition | Error class | Failures | Candidate n | Candidate share | Lower-bound share | Task-cluster 95% CI |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            "| {condition} | {error_class_candidate} | {strict_failure_n} | {candidate_n} | {candidate_share} | {mechanical_lower_bound_share} | [{task_cluster_bootstrap_ci_low}, {task_cluster_bootstrap_ci_high}] |".format(
                **row
            )
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jsonl", type=Path, default=DEFAULT_JSONL)
    parser.add_argument("--outdir", type=Path, default=DEFAULT_OUTDIR)
    parser.add_argument("--bootstrap-reps", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=20260615)
    args = parser.parse_args()

    rows = load_rows(args.jsonl)
    table = build_table(rows, args.bootstrap_reps, args.seed)
    args.outdir.mkdir(parents=True, exist_ok=True)
    write_csv(args.outdir / "table_error_taxonomy_intervals.csv", table)
    write_markdown(args.outdir / "table_error_taxonomy_intervals.md", table)
    print(f"wrote {len(table)} rows to {args.outdir / 'table_error_taxonomy_intervals.csv'}")


if __name__ == "__main__":
    main()
