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

## Second Revision (Access-2026-43510): Corrections and Post Hoc Analyses

Recorded 2026-10-20. No generation was re-run and no frozen log, task file,
prompt, corpus file, or judge rule was changed. All items below re-score or
re-describe outputs that were already observed. Scripts are in
`revision_R2_analysis/`; each one reproduces its anchor value from the earlier
analysis before reporting anything new.

### Reporting corrections

1. **H1a reported under its preregistered definition.** `preregistration_v2.md`
   defines H1a as the gain in C3 strict correctness after k<=3 F3 rounds over
   its own k=0 rate (threshold >=10pp, fallback <5pp). The first revision
   reported the conditional repair rate (32/125 = 25.6%, CI [12, 62]) in that
   place. Under the preregistered definition the gain is 32/360 = +8.89pp,
   task-cluster bootstrap 95% CI [5.0, 13.1]: below the 10pp threshold, with
   the interval including it, and at or above the 5pp fallback line. The
   conditional rate is now reported only as a secondary description.
   Script: `h1a_preregistered.py`.
2. **LLM-judge reference labels taken at the displayed record.**
   `journal_extension/build_severity_package.py` shows judges only
   `evidence[0]` but labelled each item with the verdict on the whole
   generation. In 8 of 48 error items (SEV002, SEV003, SEV006, SEV013, SEV024,
   SEV025, SEV046, SEV056; all T3 tasks with two evidence records) the
   displayed record passes the same verifier. The 360 judge responses are
   unchanged; they are re-scored against displayed-record labels (20 correct,
   40 error items). The published labels are retained in `foil_key.csv`.
   Script: `judge_label_audit.py`.
3. **Grounded pool for the error-class repair table.** `e1_analysis.py` (H2a)
   and `make_figures.py::fig3_repairability` built the "grounded" pool by
   excluding C1, which kept C2 (no source window). The table and figure now use
   C3/C4 only; the C2/C3/C4 values are reproduced as the anchor.
   Script: `error_class_grounded.py`.
4. **Bootstrap type.** `preregistration_v2.md` names a wild cluster bootstrap;
   all reported intervals use a task-cluster case (percentile) bootstrap.
5. **Locator wording in the stage-1 protocol.** `preregistration.md` (stage 1,
   file identical to the conference artifact, last modified before the first
   formal generation on 2026-06-11) describes the locator check as a match to
   the "located segment". The frozen `harness/judge.py`, used unchanged
   throughout, compares the locator with the task's curated evidence item. All
   results use the implementation. A segment-based variant cannot be computed
   reliably because the frozen corpus index carries incomplete segment labels
   (Paradise Lost "Chunk N"; Pride and Prejudice starts at Chapter II; Tale of
   Two Cities repeats chapter numbers per book).

### Post hoc analyses (not preregistered)

- Criterion ladder (L0 membership only; L1 + author/work; L2 + speaker/window)
  and four scoring-rule sensitivities (translation alias Ulysses/Odysseus;
  ordered-numeral locator rule; ellipsis-aware fragment matching; NFKD
  diacritic folding): `criterion_ladder.py`. Rules were fixed in
  `r2_common.VariantJudge` before re-scoring.
- Computational cost of repair from frozen `usage` and `latency_s` fields, and
  local verifier timing: `cost_utility.py`.
- Judge self-generation stratification and the model map of the two frozen
  grids: `judge_self_generation.py`.
- Redrawn figures (model-prefixed labels for the per-model C1->C3 figure; C3/C4
  repairability; pipeline figure text): `make_fig_model_direction.py`,
  `error_class_grounded.py`, `make_pipeline_fig_r2.py`.
- Executable specification of the verifier's known permissive and strict cases:
  `test_r2_rules.py`.
- v1.1.1 shortens one line of text in the pipeline figure (`make_pipeline_fig_r2.py`)
  so that it fits its box; no data, rule, or reported number changed.
