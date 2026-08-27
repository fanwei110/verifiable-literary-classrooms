# R1.4 / R1.5 / R1.6 / R1.10 — derived analyses (zero additional model calls)

All results are recomputed from frozen logs under `runs/raw/ext_e1b_*` and `runs/raw/ext_e1c_*`. Development TGUs (TGU2, TGU4) are excluded from every confirmatory cell and reported separately where relevant.

## R1.4 Factor heterogeneity (descriptive; reviewer-requested exploratory)

### (a) Grounding lift by task type (confirmatory 12 tasks, k=0)

| Task type | n (ungrounded) | rate (C1/C2) | n (grounded) | rate (C3/C4) | lift (pp) | 95% CI (task-cluster) |
|---|---|---|---|---|---|---|
| T1 | 200 | 38% | 240 | 95% | +57 | [24, 90] |
| T2 | 200 | 32% | 240 | 71% | +40 | [1, 82] |
| T3 | 199 | 4% | 240 | 33% | +29 | [-1, 68] |

### (b) TGU x condition strict rate — confirmatory set (k=0)

| TGU | C1 | C2 | C3 | C4 |
|---|---|---|---|---|
| TGU1 | 53% (n=75) | 64% (n=75) | 60% (n=90) | 66% (n=90) |
| TGU3 | 29% (n=75) | 31% (n=75) | 80% (n=90) | 71% (n=90) |
| TGU5 | 7% (n=75) | 11% (n=75) | 84% (n=90) | 99% (n=90) |
| TGU6 | 0% (n=75) | 1% (n=74) | 37% (n=90) | 34% (n=90) |

### (b) TGU x condition strict rate — development set (k=0)

| TGU | C1 | C2 | C3 | C4 |
|---|---|---|---|---|
| TGU2 | 67% (n=75) | 65% (n=75) | 77% (n=90) | 74% (n=90) |
| TGU4 | 67% (n=75) | 65% (n=75) | 67% (n=90) | 63% (n=90) |

### (c) Repair rate by feedback arm and task type (k=0 failures, confirmatory; F4 oracle arm excluded by design)

| Arm | T1 | T2 | T3 | pooled |
|---|---|---|---|---|
| resample | 19% (n=26) | 19% (n=47) | 17% (n=76) | 18% (n=149) |
| F1 | 46% (n=26) | 4% (n=47) | 3% (n=76) | 11% (n=149) |
| F2 | 58% (n=26) | 11% (n=47) | 5% (n=76) | 16% (n=149) |
| F3 | 50% (n=26) | 17% (n=47) | 4% (n=76) | 16% (n=149) |

*Note: F4 (oracle feedback) is physically isolated as a capability ceiling and is excluded from all repair pools. Cells are descriptive; no inferential test is applied to the four-way factorial because 12 task clusters cannot support it.*

## R1.5 Equal-budget policy mixing (paired replay, B = 3 additional calls)

Each group branches from the *same* k=0 failure state, so resample and F3 outcomes are paired within group. We fix the total additional-call budget at B = 3 and report all four pre-specified allocations; no allocation is selected post hoc.

| Allocation | M2 (chat) | M4 (reasoner) |
|---|---|---|
| resample x3 + F3 x0 | 21.1% (n=71) [12, 36] | 15.4% (n=78) [5, 27] |
| resample x2 + F3 x1 | 19.7% (n=71) [11, 35] | 23.1% (n=78) [10, 40] |
| resample x1 + F3 x2 | 19.7% (n=71) [11, 35] | 23.1% (n=78) [10, 43] |
| resample x0 + F3 x3 | 12.7% (n=71) [5, 28] | 19.2% (n=78) [6, 40] |

*Intervals are task-cluster bootstrap percentiles. This is a descriptive paired replay of already-collected branches, not a new experiment: the four allocations are recomputed from the same frozen k=0 failure set, so no additional model calls were made. Path-dependent cascades (feeding one arm's output into the next) cannot be reconstructed from branch-parallel logs and are left to future work.*

## R1.6 Repairer coverage across all four models (descriptive)

| Model | Arms available | Condition coverage | F3 repair rate (k=0 failures, confirmatory) |
|---|---|---|---|
| M1 | F3 only | C3/C4 | 29% (n=49) [18, 42] |
| M2 | resample/F1/F2/F3 | C1/C2/C3/C4 | 23% (n=253) [18, 28] |
| M3 | F3 only | C1/C2/C3/C4 | 12% (n=271) [9, 17] |
| M4 | resample/F1/F2/F3 | C1/C2/C3/C4 | 27% (n=121) [20, 36] |

*M1 and M3 were not run on the four-arm dose grid, so arm-level rankings are reported only for M2 and M4; their F3 coverage is shown here to document that targeted repair was exercised on all four repairers. Cells marked unavailable are not estimated.*

## R1.10 Quotation-length audit for successful repairs

| Group | n | median | IQR | 10th pct | mean |
|---|---|---|---|---|---|
| First-attempt correct (k=0 pass) | 713 | 88 | [46, 133] | 38 | 146 |
| Successful repair (final round) | 171 | 88 | [44, 133] | 22 | 124 |

Share of repaired quotations shorter than the first-attempt-correct lower quartile (46 characters): **27%**.

### Length change by initial error class (successful repairs only)

| Initial error class | n | median initial | median repaired | delta |
|---|---|---|---|---|
| fabricated_quotation | 86 | 135 | 116 | -19 |
| context_displacement | 39 | 58 | 48 | -10 |
| version_drift | 14 | 46 | 46 | +0 |
| misattribution | 13 | 22 | 22 | +0 |

*Characters are measured on the quotation strings recorded by the deterministic judge. The first-attempt-correct distribution is a reference, not an unbiased control: those items are easier by construction. No pedagogical minimum length is asserted; any minimum-length guardrail would be a configurable deployment parameter requiring task- and language-specific calibration, and instructional value remains a question for the prepared human A/B study.*
