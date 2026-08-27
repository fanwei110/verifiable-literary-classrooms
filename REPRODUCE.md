# Reproduction Guide

This package supports the IEEE Access submission "Toward Verifiable Literary Classrooms: Deterministic Corpus-Anchored Verification, Grounding, and In-Loop Repair for LLM Quotation Fidelity."

## Package Contents

- `corpus/`, `corpus_zh/`: frozen English and Chinese corpora.
- `tasks/`, `tasks_zh/`: task definitions and oracle windows.
- `prompts/`: prompt templates used by the English grid and extension runs.
- `harness/`, `harness_zh/`: deterministic quotation judges.
- `analysis/`, `journal_extension/`, `scripts/`: analysis and extension scripts.
- `runs/raw/`: raw run logs used for the reported analyses, excluding `authentic_teacher` human-material boundary files.
- `figures/`: generated figures used by the manuscript.
- `preregistration_v2.md`: preregistered journal-extension analysis plan.
- `MANIFEST_SHA256.txt`: SHA256 checksums for all files in this package.

`prompts_zh/` is not present in the current project tree; Chinese prompts are embedded in the Chinese task/harness workflow rather than released as a separate directory.

## Environment

Install Python dependencies:

```bash
python -m pip install -r requirements.txt
```

Some optional analyses use additional common scientific packages such as `pandas`, `numpy`, `matplotlib`, and `statsmodels`. If an analysis script reports a missing package, install it in the same environment and rerun the command.

## Core Checks

Run deterministic judge tests and smoke analyses:

```bash
python -m pytest journal_extension/tests
python analysis/formal_summary.py
python analysis/inferential_analysis.py
python journal_extension/e1_analysis.py
python journal_extension/baselines_analysis.py
python journal_extension/ingest_llm_judge_foil.py
```

The exact command-line interface of individual scripts follows the local project conventions encoded in each script. The package preserves the original directory layout so that relative paths used by the scripts continue to resolve.

## Headline Result Traceability

Each entry maps a result reported in the article to the script and data that regenerate it.

**Main grounding effect and its inference**

- Grounding effect of about +42 percentage points (CI [21, 63]): `analysis/inferential_analysis.py`, `journal_extension/make_figures.py`.
- Full GEE coefficient table (Appendix A, Table 15), including grounding OR 7.24 [2.29, 22.86] and the task-cluster case-bootstrap intervals: `revision_R1_analysis/gee_appendix/fit_gee.py`. Running it also writes `analysis_sample.csv`, the exact 1,319-observation / 12-cluster sample the appendix is fitted on; the reconstruction rules are documented in `revision_R1_analysis/README.md`.

**Factor-level heterogeneity and repair policy (Appendix B)**

- Grounding gain by task type (Table 4) and the teaching-goal-unit x prompt-condition matrix (Table 16): `revision_R1_analysis/factor_and_policy/run_analyses.py`.
- Repair rate by feedback arm and task type (Table 17), and repairer coverage across all four generator models (Table 18): same script.
- Equal-budget policy-mixing replay at B=3, all four pre-specified allocations (Table 10): same script.
- Quotation-length distribution audit for the anti-Goodhart analysis (Table 13): same script.

**Deterministic verification versus LLM judges (Section IV-E)**

- The 360-judgment experiment: two independent judges (`gpt-5.6-sol`, `deepseek-v4-pro`) x three evidence conditions (closed, RAG top-3, gold-reference) x the same frozen 60-item stratified set. Frozen prompts, raw responses, per-item records, acceptance report, and statistics are in `revision_R1_analysis/llm_judge_openbook/`.
- Gold-reference strict accuracies 58.3% and 61.7%, with error-acceptance rates 37.5% and 43.8% (Table 8): see the acceptance report and analysis scripts in that directory.

**Data quality**

- Gold locator audit over all 24 English gold evidence items: `journal_extension/gold_locator_audit.py`. This script doubles as a machine-decidable acceptance check — it exits non-zero on any membership failure, residual locator mismatch, undecidable item, or work whose structural pattern is not registered.

**Historical analysis, superseded**

- The single closed-book LLM judge foil (54% false acceptance, 92% missed context displacement) reported in the conference version is retained for provenance in `journal_extension/llm_judge_foil/`, `journal_extension/ingest_llm_judge_foil.py`, and `journal_extension/analysis_ext/llm_judge_foil_report.md`. It is **not** a headline result of the present article: it was replaced by the two-judge, three-condition experiment described above.

## Exclusions and Release Boundary

The staging package intentionally excludes `runs/raw/authentic_teacher` and the top-level `teacher_phrasings` materials. Those files relate to teacher-phrasing/human-material preparation and should be reviewed separately before any public release. This exclusion does not affect the manuscript's main confirmatory English grid, extension analyses, Chinese descriptive probe, retrieval baselines, or LLM-judge foil.

Before public archiving, authors should insert the final GitHub URL and Zenodo DOI in the manuscript and submission checklist.
