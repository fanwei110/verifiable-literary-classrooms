# Revision R1 analysis additions

Analyses added during the first revision round (IEEE Access Access-2026-33385).

- `gee_appendix/fit_gee.py` rebuilds the GEE of Section IV-B and Appendix A from the
  confirmatory logs (1,319 observations, 12 task clusters) and writes the coefficient
  table with task-cluster case-bootstrap intervals; running it reproduces Table 15.
  It also writes `gee_appendix/analysis_sample.csv`, the exact analysis sample the
  appendix is fitted on, so the sample can be inspected or refitted in other software
  without rerunning the pipeline. The sample is reconstructed deterministically from
  the frozen logs by three rules, applied in this order: (i) read
  `runs/raw/ext_e1c_m{1,2,3,4}/ext_e1c_m{1,2,3,4}.jsonl`; (ii) keep only records whose
  `arm` field is `F3`, and take each record's k=0 outcome `k0_strict` as the response,
  so that every observation is a first-attempt generation rather than a repaired one;
  (iii) drop records whose `task_id` begins with `TGU2` or `TGU4`, the two development
  units used for pipeline tuning, leaving the four confirmatory units. Grounding is
  coded 1 for C3/C4, structure 1 for C2/C4, and M1 is the reference model. These three
  rules alone yield 1,319 observations in 12 task clusters; no manual selection,
  reweighting, or exclusion is applied at any point.
- `factor_and_policy/run_analyses.py` produces the factor-level heterogeneity tables
  (task type, teaching goal unit, feedback arm), the equal-budget policy-mixing replay,
  the repairer coverage table, and the quotation-length audit, all recomputed from the
  frozen logs under `runs/raw/` with no model calls.
- `pipeline_figure/make_pipeline_fig.py` regenerates the system overview figure (Fig. 1).
- `llm_judge_openbook/` holds the frozen prompts, raw responses, per-item records,
  acceptance report and statistics for the 360-judgment LLM-judge experiment
  (two judges x three evidence conditions x 60 items) reported in Section IV-E.

Run with Python 3.11 and the packages in `requirements.txt` (statsmodels is required
for the GEE refit).
