"""Run adversarial validation for the frozen judge."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))
from judge import judge  # noqa: E402


def main() -> None:
    cases_path = ROOT / "harness" / "adversarial_cases.jsonl"
    cases = [json.loads(line) for line in cases_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    failures = []
    for case in cases:
        verdict = judge(case["task_id"], case["completion"], case.get("condition"))
        got_bucket = verdict["bucket"]
        if got_bucket != case["expected_bucket"]:
            failures.append((case["case_id"], "bucket", case["expected_bucket"], got_bucket, verdict))
            continue
        expected_error = case.get("expected_error_class_candidate")
        if expected_error and verdict.get("error_class_candidate") != expected_error:
            failures.append(
                (
                    case["case_id"],
                    "error",
                    expected_error,
                    verdict.get("error_class_candidate"),
                    verdict,
                )
            )
    report_lines = [f"# Harness adversarial validation report", "", f"Result: **{len(cases) - len(failures)}/{len(cases)}**", ""]
    if failures:
        for case_id, field, expected, got, verdict in failures:
            report_lines.append(f"- {case_id} {field}: expected {expected}, got {got}; verdict={json.dumps(verdict, ensure_ascii=False)}")
    else:
        report_lines.append("All adversarial cases passed.")
    report = "\n".join(report_lines) + "\n"
    (ROOT / "harness" / "validation_report.md").write_text(report, encoding="utf-8")
    print(report)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

