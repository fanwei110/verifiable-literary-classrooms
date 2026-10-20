# LLM-judge reference-label audit (post hoc correction)

Rebuild check: the 60 items re-derived in memory from `runs/raw/formal/formal_corr.jsonl` with the original sampling rule match the public `foil_key.csv` on auto_strict, auto_error_class and kind for all 60 items, and the displayed quote, locator and speaker appear verbatim in every frozen prompt (180 prompts).

Items whose displayed record passes the same verifier although the whole response failed: **8**

| item | run | task | cond | evidence in response | original class | displayed-record verdict |
|---|---|---|---|---|---|---|
| SEV002 | M1_C3_TGU3_T3_B_r10 | TGU3_T3 | C3 | 2 | fabricated_quotation | correct |
| SEV003 | M1_C1_TGU4_T3_B_r10 | TGU4_T3 | C1 | 2 | context_displacement | correct |
| SEV006 | M2_C4_TGU3_T3_canonical_r10 | TGU3_T3 | C4 | 2 | version_drift | correct |
| SEV013 | M1_C1_TGU1_T3_A_r01 | TGU1_T3 | C1 | 2 | context_displacement | correct |
| SEV024 | M2_C4_TGU3_T3_canonical_r03 | TGU3_T3 | C4 | 2 | version_drift | correct |
| SEV025 | M3_C4_TGU3_T3_canonical_r03 | TGU3_T3 | C4 | 2 | context_displacement | correct |
| SEV046 | M2_C3_TGU3_T3_B_r07 | TGU3_T3 | C3 | 2 | version_drift | correct |
| SEV056 | M2_C1_TGU4_T3_B_r09 | TGU4_T3 | C1 | 2 | context_displacement | correct |

Primary labels: 20 correct, 40 error items; error classes {'fabricated_quotation': 11, 'correct': 20, 'misattribution': 12, 'version_drift': 9, 'context_displacement': 8}.

Sensitivity labels: window not imposed → 20 correct; + alias → 23 correct.

## original (response-level labels, as published)

| Judge | Evidence | Strict accuracy [Wilson 95%] | Error acceptance | Correct acceptance | Unsure | Acc. excl. unsure |
|---|---|---|---|---|---|---|
| gpt-5.6-sol (Codex subscription) | closed | 26.7% [17.1, 39.0] | 18.8% (9/48) | 33.3% | 56.7% | 61.5% |
| gpt-5.6-sol (Codex subscription) | rag_top3 | 46.7% [34.6, 59.1] | 37.5% (18/48) | 75.0% | 21.7% | 59.6% |
| gpt-5.6-sol (Codex subscription) | gold_reference | 58.3% [45.7, 69.9] | 37.5% (18/48) | 83.3% | 10.0% | 64.8% |
| deepseek-v4-pro | closed | 38.3% [27.1, 51.0] | 66.7% (32/48) | 100.0% | 8.3% | 41.8% |
| deepseek-v4-pro | rag_top3 | 46.7% [34.6, 59.1] | 60.4% (29/48) | 83.3% | 1.7% | 47.5% |
| deepseek-v4-pro | gold_reference | 61.7% [49.0, 72.9] | 43.8% (21/48) | 83.3% | 0.0% | 61.7% |

| Judge | Contrast | a only | b only | exact p | Holm p |
|---|---|---|---|---|---|
| gpt-5.6-sol (Codex subscription) | closed vs rag_top3 | 4 | 16 | 0.0118 | 0.0236 |
| gpt-5.6-sol (Codex subscription) | rag_top3 vs gold_reference | 2 | 9 | 0.0654 | 0.0654 |
| gpt-5.6-sol (Codex subscription) | closed vs gold_reference | 4 | 23 | 0.0003 | 0.0009 |
| deepseek-v4-pro | closed vs rag_top3 | 3 | 8 | 0.2266 | 0.2266 |
| deepseek-v4-pro | rag_top3 vs gold_reference | 1 | 10 | 0.0117 | 0.0234 |
| deepseek-v4-pro | closed vs gold_reference | 4 | 18 | 0.0043 | 0.0130 |

## primary: displayed-record labels

| Judge | Evidence | Strict accuracy [Wilson 95%] | Error acceptance | Correct acceptance | Unsure | Acc. excl. unsure |
|---|---|---|---|---|---|---|
| gpt-5.6-sol (Codex subscription) | closed | 28.3% [18.5, 40.8] | 12.5% (5/40) | 40.0% | 56.7% | 65.4% |
| gpt-5.6-sol (Codex subscription) | rag_top3 | 56.7% [44.1, 68.4] | 27.5% (11/40) | 80.0% | 21.7% | 72.3% |
| gpt-5.6-sol (Codex subscription) | gold_reference | 68.3% [55.8, 78.7] | 27.5% (11/40) | 85.0% | 10.0% | 75.9% |
| deepseek-v4-pro | closed | 48.3% [36.2, 60.7] | 62.5% (25/40) | 95.0% | 8.3% | 52.7% |
| deepseek-v4-pro | rag_top3 | 56.7% [44.1, 68.4] | 55.0% (22/40) | 85.0% | 1.7% | 57.6% |
| deepseek-v4-pro | gold_reference | 71.7% [59.2, 81.5] | 35.0% (14/40) | 85.0% | 0.0% | 71.7% |

| Judge | Contrast | a only | b only | exact p | Holm p |
|---|---|---|---|---|---|
| gpt-5.6-sol (Codex subscription) | closed vs rag_top3 | 1 | 18 | 0.0001 | 0.0002 |
| gpt-5.6-sol (Codex subscription) | rag_top3 vs gold_reference | 2 | 9 | 0.0654 | 0.0654 |
| gpt-5.6-sol (Codex subscription) | closed vs gold_reference | 1 | 25 | 0.0000 | 0.0000 |
| deepseek-v4-pro | closed vs rag_top3 | 3 | 8 | 0.2266 | 0.2266 |
| deepseek-v4-pro | rag_top3 vs gold_reference | 1 | 10 | 0.0117 | 0.0234 |
| deepseek-v4-pro | closed vs gold_reference | 4 | 18 | 0.0043 | 0.0130 |

## sensitivity: + window constraint not imposed

| Judge | Evidence | Strict accuracy [Wilson 95%] | Error acceptance | Correct acceptance | Unsure | Acc. excl. unsure |
|---|---|---|---|---|---|---|
| gpt-5.6-sol (Codex subscription) | closed | 28.3% [18.5, 40.8] | 12.5% (5/40) | 40.0% | 56.7% | 65.4% |
| gpt-5.6-sol (Codex subscription) | rag_top3 | 56.7% [44.1, 68.4] | 27.5% (11/40) | 80.0% | 21.7% | 72.3% |
| gpt-5.6-sol (Codex subscription) | gold_reference | 68.3% [55.8, 78.7] | 27.5% (11/40) | 85.0% | 10.0% | 75.9% |
| deepseek-v4-pro | closed | 48.3% [36.2, 60.7] | 62.5% (25/40) | 95.0% | 8.3% | 52.7% |
| deepseek-v4-pro | rag_top3 | 56.7% [44.1, 68.4] | 55.0% (22/40) | 85.0% | 1.7% | 57.6% |
| deepseek-v4-pro | gold_reference | 71.7% [59.2, 81.5] | 35.0% (14/40) | 85.0% | 0.0% | 71.7% |

| Judge | Contrast | a only | b only | exact p | Holm p |
|---|---|---|---|---|---|
| gpt-5.6-sol (Codex subscription) | closed vs rag_top3 | 1 | 18 | 0.0001 | 0.0002 |
| gpt-5.6-sol (Codex subscription) | rag_top3 vs gold_reference | 2 | 9 | 0.0654 | 0.0654 |
| gpt-5.6-sol (Codex subscription) | closed vs gold_reference | 1 | 25 | 0.0000 | 0.0000 |
| deepseek-v4-pro | closed vs rag_top3 | 3 | 8 | 0.2266 | 0.2266 |
| deepseek-v4-pro | rag_top3 vs gold_reference | 1 | 10 | 0.0117 | 0.0234 |
| deepseek-v4-pro | closed vs gold_reference | 4 | 18 | 0.0043 | 0.0130 |

## sensitivity: + window not imposed + Ulysses/Odysseus alias

| Judge | Evidence | Strict accuracy [Wilson 95%] | Error acceptance | Correct acceptance | Unsure | Acc. excl. unsure |
|---|---|---|---|---|---|---|
| gpt-5.6-sol (Codex subscription) | closed | 28.3% [18.5, 40.8] | 13.5% (5/37) | 34.8% | 56.7% | 65.4% |
| gpt-5.6-sol (Codex subscription) | rag_top3 | 61.7% [49.0, 72.9] | 21.6% (8/37) | 82.6% | 21.7% | 78.7% |
| gpt-5.6-sol (Codex subscription) | gold_reference | 73.3% [61.0, 82.9] | 21.6% (8/37) | 87.0% | 10.0% | 81.5% |
| deepseek-v4-pro | closed | 53.3% [40.9, 65.4] | 59.5% (22/37) | 95.7% | 8.3% | 58.2% |
| deepseek-v4-pro | rag_top3 | 61.7% [49.0, 72.9] | 51.4% (19/37) | 87.0% | 1.7% | 62.7% |
| deepseek-v4-pro | gold_reference | 76.7% [64.6, 85.6] | 29.7% (11/37) | 87.0% | 0.0% | 76.7% |

| Judge | Contrast | a only | b only | exact p | Holm p |
|---|---|---|---|---|---|
| gpt-5.6-sol (Codex subscription) | closed vs rag_top3 | 1 | 21 | 0.0000 | 0.0000 |
| gpt-5.6-sol (Codex subscription) | rag_top3 vs gold_reference | 2 | 9 | 0.0654 | 0.0654 |
| gpt-5.6-sol (Codex subscription) | closed vs gold_reference | 1 | 28 | 0.0000 | 0.0000 |
| deepseek-v4-pro | closed vs rag_top3 | 3 | 8 | 0.2266 | 0.2266 |
| deepseek-v4-pro | rag_top3 vs gold_reference | 1 | 10 | 0.0117 | 0.0234 |
| deepseek-v4-pro | closed vs gold_reference | 4 | 18 | 0.0043 | 0.0130 |

## Primary labels: gold-reference acceptance by error class

| Judge | Class | accepted / n |
|---|---|---|
| gpt-5.6-sol (Codex subscription) | fabricated_quotation | 0/11 |
| gpt-5.6-sol (Codex subscription) | misattribution | 5/12 |
| gpt-5.6-sol (Codex subscription) | version_drift | 0/9 |
| gpt-5.6-sol (Codex subscription) | context_displacement | 6/8 |
| deepseek-v4-pro | fabricated_quotation | 2/11 |
| deepseek-v4-pro | misattribution | 6/12 |
| deepseek-v4-pro | version_drift | 1/9 |
| deepseek-v4-pro | context_displacement | 5/8 |

## Primary labels: RAG top-3 strict accuracy by retrieval hit

| Judge | Hit definition | Hit | n | Strict accuracy |
|---|---|---|---|---|
| gpt-5.6-sol (Codex subscription) | task_gold_hit_at_3 | True | 30 | 73.3% (22/30) |
| gpt-5.6-sol (Codex subscription) | task_gold_hit_at_3 | False | 30 | 40.0% (12/30) |
| gpt-5.6-sol (Codex subscription) | claim_exact_hit_at_3 | True | 17 | 70.6% (12/17) |
| gpt-5.6-sol (Codex subscription) | claim_exact_hit_at_3 | False | 43 | 51.2% (22/43) |
| deepseek-v4-pro | task_gold_hit_at_3 | True | 30 | 66.7% (20/30) |
| deepseek-v4-pro | task_gold_hit_at_3 | False | 30 | 46.7% (14/30) |
| deepseek-v4-pro | claim_exact_hit_at_3 | True | 17 | 70.6% (12/17) |
| deepseek-v4-pro | claim_exact_hit_at_3 | False | 43 | 51.2% (22/43) |
