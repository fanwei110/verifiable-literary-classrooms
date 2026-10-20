# Verifiable Classroom: Classical-Literature Quotation Fidelity Benchmark

This repository is the replication package for:

**Toward Verifiable Literary Classrooms: Deterministic Corpus-Anchored Verification, Grounding, and In-Loop Repair for LLM Quotation Fidelity**

It contains everything needed to recompute the headline numbers, tables, and figures
of the article, including the analyses added in the first revision round: the full GEE
coefficient table and its exact analysis sample (Appendix A), the factor-level
heterogeneity and equal-budget policy-mixing analyses (Appendix B), the quotation-length
distribution audit, and the complete records of the 360-judgment, two-judge,
three-evidence-condition experiment reported in Section IV-E. Version 1.1.0 adds the
second-revision analyses in `revision_R2_analysis/` and the stage-1 protocol
`preregistration.md`; it changes no frozen log, corpus, task, prompt, or judge file.
See `REPRODUCE.md` for a result-by-result traceability map and `DEVIATIONS.md` for
every correction and post hoc analysis.

It adapts the finance `computable classroom` benchmark pattern to a humanities setting where the verifiable substrate is not an equation but a frozen source corpus. The benchmark measures whether LLMs can produce classroom-facing literary explanations with real quotations, correct attribution, and correct textual grounding.

## Layout

```text
analysis/               Result summarization scripts.
config/                 Model configuration and price snapshot.
corpus/, corpus_zh/     Frozen public-domain texts with manifest and SHA256 hashes.
harness/, harness_zh/   Task validation and the deterministic quotation judges.
journal_extension/      Extension runs, retrieval baselines, the non-destructive
                        locator-correction layer, and gold_locator_audit.py, which
                        doubles as a machine-decidable acceptance check.
prompts/                The four prompt conditions C1-C4.
revision_R1_analysis/   Analyses added in the first revision round: the GEE appendix
                        with its exact analysis sample, factor-level heterogeneity and
                        equal-budget policy mixing, the quotation-length audit, the
                        pipeline figure, and the complete 360-judgment LLM-judge
                        experiment (prompts, raw responses, per-item records).
revision_R2_analysis/   Second-revision analyses (all re-score frozen outputs; see
                        DEVIATIONS.md): criterion ladder and scoring-rule
                        sensitivity, H1a under its preregistered definition, the
                        LLM-judge reference-label audit, C3/C4 repairability, the
                        cost-utility accounting, redrawn figures, and executable
                        tests of the verifier's rules.
runs/                   Frozen run logs for every reported analysis. These are
                        released with the package, not excluded.
scripts/                Builders for corpus, tasks, prompts, and the model snapshot.
tasks/, tasks_zh/       Task specifications: 6 TGUs x 3 task types, plus the Chinese probe.
```

## Stage-1 Build

Run from this directory:

```powershell
python scripts/build_corpus.py
python scripts/generate_tasks_prompts.py
python scripts/snapshot_models.py
python harness/validate_tasks.py
python harness/run_validation.py
```

The expected stage-1 targets are:

- 6 frozen public-domain source texts.
- 18 task specs.
- C1/C2/C3/C4 prompt sets.
- 40 adversarial validation cases.
- 40/40 adversarial judge acceptance.

## Pilot Run

The pilot verifies API access, JSON parsing, and logging. It is not part of the paper's confirmatory evidence.

```powershell
python runner.py --tag pilot --key-file ..\api.txt --models M1,M2,M3 --conditions C1,C2,C3,C4 --tasks TGU1_T1,TGU2_T1 --reps 1
```

The API key is read from `--key-file` or `OPENROUTER_API_KEY`; it is never written to logs.

