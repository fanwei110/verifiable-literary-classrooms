"""Summarize runner JSONL logs.

This script is intentionally lightweight for stage 1. It reports condition-
and model-level strict/defensible correctness and bucket counts.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("jsonl", type=Path)
    args = ap.parse_args()

    rows = []
    for line in args.jsonl.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))

    by_key: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        by_key[(row["model"], row["condition"])].append(row)

    for key in sorted(by_key):
        group = by_key[key]
        n = len(group)
        strict = sum(1 for r in group if r["judge"].get("strict_correct"))
        defensible = sum(1 for r in group if r["judge"].get("defensible_correct"))
        buckets = Counter(r["judge"].get("bucket") for r in group)
        print(
            f"{key[0]} {key[1]}: n={n} strict={strict/n:.1%} "
            f"defensible={defensible/n:.1%} buckets={dict(buckets)}"
        )


if __name__ == "__main__":
    main()

