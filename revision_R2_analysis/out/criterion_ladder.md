# Criterion ladder and scoring-rule sensitivity (post hoc)

Sample: 1319 k=0 generations, 12 confirmatory task clusters (F3-arm records of ext_e1c_m1–m4; dev tasks TGU2/TGU4 excluded). Anchor check: VariantJudge with all switches off reproduces the frozen k0_strict for every record (0 mismatches).

Effect = mean over the 12 tasks of (C3,C4 pass rate − C1,C2 pass rate); CI = task-cluster percentile bootstrap, B=2000, seed=20260823.

| Level | Criterion | C1 | C2 | C3 | C4 | Grounding effect (pp) | 95% CI | Tasks > 0 | fail→pass (grounded / ungrounded) | pass→fail |
|---|---|---|---|---|---|---|---|---|---|---|
| L0 | Corpus membership only | 42.7% | 51.5% | 87.5% | 93.9% | +43.7 | [23.2, 64.2] | 11/12 | 310 (175 / 135) | 0 |
| L1 | Membership + author and work | 36.7% | 43.1% | 86.4% | 92.5% | +49.6 | [27.8, 69.2] | 10/12 | 258 (166 / 92) | 0 |
| L2 | L1 + speaker + window (no locator) | 25.3% | 28.1% | 65.3% | 69.4% | +40.7 | [18.4, 62.7] | 10/12 | 20 (7 / 13) | 0 |
| strict | Primary criterion (preregistered implementation) | 22.3% | 26.8% | 65.3% | 67.5% | +41.9 | [21.0, 62.9] | 10/12 | 0 (0 / 0) | 0 |
| S-alias | strict + translation alias (Ulysses/Odysseus) | 23.3% | 30.4% | 73.1% | 74.2% | +46.8 | [26.5, 66.4] | 10/12 | 66 (52 / 14) | 0 |
| S-ordered | strict + ordered-numeral locator rule | 21.3% | 24.7% | 65.0% | 66.1% | +42.6 | [21.6, 63.2] | 10/12 | 0 (0 / 0) | 15 |
| S-ellipsis | strict + ellipsis-aware fragment matching | 22.7% | 27.1% | 69.4% | 67.8% | +43.8 | [23.1, 64.4] | 11/12 | 18 (16 / 2) | 0 |
| S-nfkd | strict + diacritic folding (NFKD) and U+2026 as separator | 22.3% | 26.8% | 65.3% | 67.5% | +41.9 | [21.0, 62.9] | 10/12 | 0 (0 / 0) | 0 |
| S-all | strict + all four sensitivity rules | 22.3% | 28.8% | 76.9% | 73.1% | +49.5 | [30.3, 68.6] | 10/12 | 83 (68 / 15) | 15 |

## Per-task grounding difference (pp)

| Task | L0 | L1 | L2 | strict | S-alias | S-ordered | S-ellipsis | S-nfkd | S-all |
|---|---|---|---|---|---|---|---|---|---|
| TGU1_T1 | +22.7 | +23.0 | +23.0 | +23.0 | +23.0 | +23.0 | +21.0 | +23.0 | +21.0 |
| TGU1_T2 | +1.0 | -0.7 | -0.7 | -0.7 | -0.7 | -7.3 | +4.3 | -0.7 | -2.3 |
| TGU1_T3 | +17.3 | +17.3 | -24.0 | -10.0 | -10.0 | +0.0 | -12.0 | -10.0 | +0.0 |
| TGU3_T1 | +16.0 | +16.0 | +22.0 | +24.0 | +24.0 | +24.0 | +24.0 | +24.0 | +24.0 |
| TGU3_T2 | +22.0 | +68.0 | +88.3 | +85.3 | +85.3 | +88.0 | +85.3 | +85.3 | +88.0 |
| TGU3_T3 | -13.0 | -13.0 | +26.0 | +27.3 | +27.3 | +29.3 | +42.3 | +27.3 | +44.3 |
| TGU5_T1 | +91.3 | +91.3 | +89.7 | +89.7 | +89.7 | +89.7 | +89.7 | +89.7 | +89.7 |
| TGU5_T2 | +72.7 | +72.7 | +72.7 | +72.7 | +72.7 | +72.7 | +72.7 | +72.7 | +72.7 |
| TGU5_T3 | +80.7 | +80.7 | +86.7 | +86.7 | +86.7 | +86.7 | +88.3 | +86.7 | +88.3 |
| TGU6_T1 | +96.3 | +94.7 | +89.7 | +89.7 | +89.7 | +89.7 | +89.7 | +89.7 | +89.7 |
| TGU6_T2 | +32.3 | +63.7 | +1.7 | +1.7 | +60.3 | +1.7 | +1.7 | +1.7 | +60.3 |
| TGU6_T3 | +85.0 | +81.7 | +13.3 | +13.3 | +13.3 | +13.3 | +18.3 | +13.3 | +18.3 |

Note: these rescorings report how the same observed outputs fare under each rule. They are not re-runs of the repair loop under a different verifier, whose stopping and feedback would differ.
