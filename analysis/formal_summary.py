"""Validate and summarize formal generation logs."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_BUCKETS = {"strict_correct", "defensible_correct", "wrong", "format_failure", "transport_failure"}


def load_rows(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def load_task_types() -> dict[str, str]:
    out = {}
    for path in (ROOT / "tasks").glob("TGU*_T*.yaml"):
        task = yaml.safe_load(path.read_text(encoding="utf-8"))
        out[task["task_id"]] = task["task_type"]
    return out


def pct(num: int, den: int) -> float:
    return round(num / den, 4) if den else 0.0


def summarize_group(rows: list[dict], keys: tuple[str, ...]) -> list[dict]:
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for row in rows:
        groups[tuple(row[key] for key in keys)].append(row)
    output = []
    for key, group in sorted(groups.items()):
        n = len(group)
        strict = sum(1 for row in group if row["judge"].get("strict_correct"))
        defensible = sum(1 for row in group if row["judge"].get("defensible_correct"))
        buckets = Counter(row["judge"].get("bucket") for row in group)
        record = {name: value for name, value in zip(keys, key)}
        record.update(
            {
                "n": n,
                "strict_correct": strict,
                "strict_rate": pct(strict, n),
                "defensible_correct": defensible,
                "defensible_rate": pct(defensible, n),
            }
        )
        for bucket in sorted(ALLOWED_BUCKETS):
            record[f"bucket_{bucket}"] = buckets.get(bucket, 0)
        output.append(record)
    return output


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jsonl", type=Path, default=ROOT / "runs" / "raw" / "formal" / "formal.jsonl")
    parser.add_argument("--outdir", type=Path, default=ROOT / "runs" / "raw" / "formal" / "tables")
    parser.add_argument("--expect-complete", action="store_true")
    args = parser.parse_args()

    rows = load_rows(args.jsonl)
    task_types = load_task_types()
    for row in rows:
        row["task_type"] = task_types.get(row["task_id"], "unknown")

    ids = [row["run_id"] for row in rows]
    duplicate_ids = sorted(run_id for run_id, count in Counter(ids).items() if count > 1)
    buckets = Counter(row.get("judge", {}).get("bucket") for row in rows)
    bad_buckets = sorted(bucket for bucket in buckets if bucket not in ALLOWED_BUCKETS)
    coverage = {
        "records": len(rows),
        "unique_run_ids": len(set(ids)),
        "duplicate_run_ids": duplicate_ids,
        "by_model": dict(Counter(row["model"] for row in rows)),
        "by_condition": dict(Counter(row["condition"] for row in rows)),
        "by_task": dict(Counter(row["task_id"] for row in rows)),
        "buckets": dict(buckets),
        "bad_buckets": bad_buckets,
    }

    args.outdir.mkdir(parents=True, exist_ok=True)
    (args.outdir / "coverage.json").write_text(json.dumps(coverage, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(args.outdir / "table_condition.csv", summarize_group(rows, ("condition",)))
    write_csv(args.outdir / "table_model_condition.csv", summarize_group(rows, ("model", "condition")))
    write_csv(args.outdir / "table_task_type_condition.csv", summarize_group(rows, ("task_type", "condition")))
    write_csv(args.outdir / "table_task_condition.csv", summarize_group(rows, ("task_id", "condition")))

    print(json.dumps(coverage, ensure_ascii=False, indent=2))
    if args.expect_complete:
        errors = []
        if coverage["records"] != 2160 or coverage["unique_run_ids"] != 2160:
            errors.append("formal log does not contain exactly 2160 unique records")
        if coverage["by_model"] != {"M1": 720, "M2": 720, "M3": 720}:
            errors.append(f"model coverage mismatch: {coverage['by_model']}")
        if coverage["by_condition"] != {"C1": 540, "C2": 540, "C3": 540, "C4": 540}:
            errors.append(f"condition coverage mismatch: {coverage['by_condition']}")
        if sorted(set(coverage["by_task"].values())) != [120]:
            errors.append("task coverage is not 120 for every task")
        if coverage["bad_buckets"]:
            errors.append(f"bad buckets: {coverage['bad_buckets']}")
        if coverage["buckets"].get("transport_failure", 0):
            errors.append("transport_failure records remain")
        if errors:
            raise SystemExit("Formal summary validation failed:\n- " + "\n- ".join(errors))


if __name__ == "__main__":
    main()

