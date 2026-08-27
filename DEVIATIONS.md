# Deviations and Run Management Log

This file records changes or operational events after the preregistered benchmark
infrastructure was frozen. It distinguishes scientific deviations from
engineering run-management events.

## Scientific Rule Changes

None after the formal generation started.

- Corpus files were not changed.
- Task specifications were not changed.
- Prompt files were not changed.
- Judge rules were not changed.
- Model identifiers in `config/models.yaml` were not changed.

## Formal Run Management Event

During the first formal run on 2026-06-11, the shell command reached the tool
timeout while the Python process continued running in the background. A second
formal runner was started before the first background process was stopped. This
created duplicate records for some `run_id` values.

Resolution:

- Both overlapping `run_formal.py` processes were stopped.
- The full pre-cleanup log was archived as
  `runs/raw/formal/formal_with_duplicates_20260611_184306.jsonl`.
- Duplicate records were archived as
  `runs/raw/formal/formal_duplicates_archive_20260611_184306.jsonl`.
- The final `runs/raw/formal/formal.jsonl` was deduplicated by keeping the first
  record observed for each `run_id`.
- Completion sidecar files in `runs/raw/formal/completions/` were regenerated
  from the final deduplicated `formal.jsonl`.
- A lock-file guard was added to `run_formal.py` to prevent overlapping formal
  processes in future runs.

Justification:

The duplicate event was a process-management issue, not a change to treatment
assignment, prompting, corpus, judge logic, or model configuration. The retained
records preserve the original first completion for each planned `run_id`.

## Final Formal Dataset Integrity

- Planned jobs: 2160.
- Final records: 2160.
- Unique `run_id` values: 2160.
- API transport failures remaining: 0.
- Model coverage: 720 records per model.
- Condition coverage: 540 records per condition.
- Task coverage: 120 records per task.
- API key leakage scan for the OpenRouter key prefix: no matches in formal logs.

## Analysis Additions

The following analysis scripts and tables were added after formal generation as
first-pass statistical outputs:

- `analysis/formal_summary.py`
- `analysis/inferential_analysis.py`
- `runs/raw/formal/tables/analysis_dataset.csv`
- `runs/raw/formal/tables/bootstrap_condition_rates.csv`
- `runs/raw/formal/tables/bootstrap_condition_contrasts.csv`
- `runs/raw/formal/tables/gee_logistic.csv`
- `runs/raw/formal/tables/stage3_analysis_report.md`

These additions summarize the frozen formal log and do not alter any generation
or judging rule.
