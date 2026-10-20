# Computational cost–utility of in-loop verification (frozen logs only)

## M2 (deepseek-chat), k=0 failure pool n = 71

| Arm | Accounting | Success within k≤3 | Mean first-success round | Extra calls / item | Extra input tok / item | Extra output tok / item | Reasoning tok / item | Extra latency (s) / item | Extra tokens / success | Extra latency (s) / success |
|---|---|---|---|---|---|---|---|---|---|---|
| resample | as executed | 21.1% (15/71) | 1.40 | 3.00 | 1233 | 1080 | 0 | 13.7 | 10944 | 64.9 |
| resample | stop-at-first replay | 21.1% (15/71) | 1.40 | 2.66 | 1055 | 962 | 0 | 12.2 | 9543 | 58.0 |
| F1 | as executed | 8.5% (6/71) | 1.33 | 2.86 | 3447 | 999 | 0 | 11.5 | 52622 | 136.2 |
| F2 | as executed | 9.9% (7/71) | 2.14 | 2.92 | 3678 | 1016 | 0 | 11.0 | 47607 | 111.1 |
| F3 | as executed | 12.7% (9/71) | 1.44 | 2.80 | 3860 | 997 | 0 | 9.7 | 38316 | 76.8 |

## M4 (deepseek-reasoner), k=0 failure pool n = 78

| Arm | Accounting | Success within k≤3 | Mean first-success round | Extra calls / item | Extra input tok / item | Extra output tok / item | Reasoning tok / item | Extra latency (s) / item | Extra tokens / success | Extra latency (s) / success |
|---|---|---|---|---|---|---|---|---|---|---|
| resample | as executed | 15.4% (12/78) | 1.58 | 3.00 | 1319 | 2892 | 1843 | 33.5 | 27372 | 217.6 |
| resample | stop-at-first replay | 15.4% (12/78) | 1.58 | 2.78 | 1147 | 2656 | 1681 | 30.9 | 24722 | 200.8 |
| F1 | as executed | 12.8% (10/78) | 1.60 | 2.82 | 3438 | 3191 | 2265 | 33.9 | 51711 | 264.4 |
| F2 | as executed | 21.8% (17/78) | 1.65 | 2.71 | 3365 | 3253 | 2358 | 33.7 | 30365 | 154.7 |
| F3 | as executed | 19.2% (15/78) | 1.53 | 2.72 | 3789 | 3279 | 2384 | 34.0 | 36756 | 176.8 |

## Single k=0 generation cost by condition (primary sample, all four models pooled)

| Condition | n | Input tok (mean) | Output tok (mean) | Latency s (median) |
|---|---|---|---|---|
| C1 | 300 | 167 | 427 | 6.9 |
| C2 | 299 | 211 | 415 | 6.4 |
| C3 | 360 | 790 | 416 | 6.4 |
| C4 | 360 | 859 | 402 | 6.1 |

## Deterministic verifier runtime (no model call)

Machine: Intel64 Family 6 Model 186 Stepping 2, GenuineIntel, Python 3.12.4. Cold start (load frozen corpus index once): 25 ms. Per-generation judgement over 1319 k=0 outputs: median 12.50 ms, 95th percentile 25.45 ms, total 16.11 s.

Notes: latency is client-side wall-clock time and includes network and queueing. Tokens are not converted to a common currency across providers. No F4 records exist in the released logs, so F4 is not reported.
