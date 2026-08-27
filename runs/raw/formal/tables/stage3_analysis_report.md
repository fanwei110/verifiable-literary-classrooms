# Stage 3 Formal Analysis Report

## Coverage

- Records: 2160
- Unique run IDs: 2160
- Buckets: {'wrong': 1217, 'strict_correct': 812, 'format_failure': 102, 'defensible_correct': 29}

## Strict Correctness by Condition

| condition | n | correct | rate | cluster bootstrap 95% CI |
|---|---:|---:|---:|---:|
| C1 | 540 | 167 | 0.309 | [0.139, 0.500] |
| C2 | 540 | 188 | 0.348 | [0.165, 0.546] |
| C3 | 540 | 233 | 0.431 | [0.233, 0.630] |
| C4 | 540 | 224 | 0.415 | [0.220, 0.615] |

## Strict-Correctness Contrasts

| contrast | delta | cluster bootstrap 95% CI |
|---|---:|---:|
| C4-C1 | 0.106 | [-0.004, 0.230] |
| C3-C1 | 0.122 | [0.015, 0.252] |
| C2-C1 | 0.039 | [0.000, 0.089] |
| C4-C2 | 0.067 | [-0.024, 0.159] |
| C4-C3 | -0.017 | [-0.076, 0.037] |

## GEE Logistic Model, Strict Correctness

| term | odds ratio | robust 95% CI | p |
|---|---:|---:|---:|
| grounding | 1.694 | [1.008, 2.846] | 0.0465 |
| structure | 1.192 | [0.980, 1.451] | 0.07854 |
| grounding:structure | 0.783 | [0.589, 1.041] | 0.09275 |

## Interpretation

Grounding improves strict quotation fidelity relative to the improvised baseline, but the full TGU template does not outperform grounded-only prompting in this run. The C4-C3 contrast is negative and should be reported as a real result, not repaired after the fact.

