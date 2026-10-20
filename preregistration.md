# Preregistration Draft

This file is the stage-1 preregistration draft. It should be frozen before any formal model generation is collected.

## Registered Bundle

1. **Corpus**: public-domain source texts listed in `corpus/corpus_manifest.csv`, with raw-text hashes in `corpus/SHA256SUMS.txt`.
2. **Task specifications**: `tasks/*.yaml`, 18 tasks from 6 textual grounding units (TGUs) and 3 task types.
3. **Prompt sets**: four conditions crossing `grounding` and `structure`.
   - C1: improvised, no grounding, no structure beyond the common JSON output contract.
   - C2: structured-generic, no source passage, evidence template supplied.
   - C3: grounded-only, source passage supplied, no detailed evidence protocol beyond the common JSON output contract.
   - C4: TGU-templated, source passage plus evidence protocol.
4. **Judging harness**: `harness/judge.py`, with quote normalization, corpus lookup, strict/defensible/wrong tiers, and error-class candidates.
5. **Adversarial validation**: `harness/adversarial_cases.jsonl`, 20 correct-but-format-hostile and 20 planted-error cases.
6. **Model configuration**: `config/models.yaml`, queried via OpenRouter with provider-default decoding and no custom temperature/top-p.

## Confirmatory Hypotheses

- H1: C4 TGU-templated correctness exceeds C1 improvised correctness.
- H2: Grounding has a positive effect: C3 > C1 and C4 > C2.
- H3: Structure improves auditability and correctness, especially when paired with grounding: C4 > C3.

## Primary Outcome

`strict_correct` equals 1 if all required evidence records in a generation satisfy:

1. The quoted text is found in the frozen source corpus after preregistered normalization.
2. Claimed author and work match the located corpus item.
3. Claimed locator matches the located segment.
4. Claimed speaker/narrator matches the task's expected speaker/narrator.
5. In grounded conditions, the quote is drawn from the supplied source window.

## Secondary Outcomes

- `defensible_correct`
- quote existence rate
- attribution accuracy
- locator accuracy
- grounding compliance
- format adherence
- clarifying/version-note behavior
- latency

## Error Classes

Each failed generation receives one candidate primary error class:

- `fabricated_quotation`
- `misattribution`
- `version_drift`
- `context_displacement`
- `format_failure`

The final paper may double-code failures manually for publication-level reliability statistics, but the automated candidate classes are frozen here as the stage-1 operationalization.

## Formal Grid

Formal scale follows the finance benchmark:

`18 tasks x 4 conditions x 3 models x 10 repetitions = 2160 generations`.

All formal comparisons use task-clustered intervals and mixed-effects or clustered logistic models. Model rankings and genre/task-type breakdowns are exploratory.

## Freeze Rules

- The corpus, tasks, prompt sets, judge thresholds, and model config must be frozen before formal generation.
- Any post-freeze change must be logged as a disclosed deviation.
- Pilot runs may be used to debug API plumbing and output parsing, but no pilot result enters confirmatory analysis.

