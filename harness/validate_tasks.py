"""Validate task specs, prompt files, and gold quote retrievability."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))
from judge import find_in_segments, load_corpus  # noqa: E402


REQUIRED = {
    "task_id",
    "tgu_id",
    "work_id",
    "work_title",
    "author",
    "task_type",
    "theme",
    "required_evidence_count",
    "expected_evidence",
}


def main() -> None:
    corpus = load_corpus()
    tasks = sorted((ROOT / "tasks").glob("*.yaml"))
    errors = []
    for path in tasks:
        task = yaml.safe_load(path.read_text(encoding="utf-8"))
        missing = REQUIRED - set(task)
        if missing:
            errors.append(f"{path.name}: missing {sorted(missing)}")
            continue
        if task["work_id"] not in corpus:
            errors.append(f"{path.name}: unknown work_id {task['work_id']}")
            continue
        if len(task["expected_evidence"]) != task["required_evidence_count"]:
            errors.append(f"{path.name}: evidence count mismatch")
        for ev in task["expected_evidence"]:
            for key in ("quote", "locator", "speaker_or_narrator", "source_window"):
                if key not in ev or not ev[key]:
                    errors.append(f"{path.name}: evidence missing {key}")
            if find_in_segments(ev["quote"], corpus[task["work_id"]]) is None:
                errors.append(f"{path.name}: quote not retrievable: {ev['quote'][:60]}")
        tid = task["task_id"]
        expected_prompts = [
            ROOT / "prompts" / "C1_simulated" / f"{tid}_A.md",
            ROOT / "prompts" / "C1_simulated" / f"{tid}_B.md",
            ROOT / "prompts" / "C2_structured" / f"{tid}.md",
            ROOT / "prompts" / "C3_grounded" / f"{tid}_A.md",
            ROOT / "prompts" / "C3_grounded" / f"{tid}_B.md",
            ROOT / "prompts" / "C4_tgu" / f"{tid}.md",
        ]
        for prompt in expected_prompts:
            if not prompt.exists():
                errors.append(f"{path.name}: missing prompt {prompt}")
    if len(tasks) != 18:
        errors.append(f"expected 18 tasks, found {len(tasks)}")
    if errors:
        print("\n".join(errors))
        raise SystemExit(1)
    print("task validation PASS: 18/18 specs and prompt sets")


if __name__ == "__main__":
    main()

