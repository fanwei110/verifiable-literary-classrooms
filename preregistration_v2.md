# Preregistration v2 — Verifiable Classroom, Journal Extension (Verify-then-Repair)

**Registered:** 2026-07-03 (before confirmatory runs). Frozen 2,160-generation grid (`runs/raw/formal/`) is the reproduced baseline and is NOT rerun. All confirmatory generations are new, logged under `runs/raw/ext_*/`.
**Integrity commitments:** hypotheses fixed below before confirmatory data; null / reversed results reported as primary findings per the fallbacks; no reference fabricated (Crossref/arXiv verified); all feedback information-capped (F1–F3 never contain correct values, enforced in code by `assert_no_leak`).

## 1. Core claim
A deterministic, corpus-hash-anchored quotation verifier, placed *inside* the generation loop, repairs LLM classroom quotation errors; the repair rate decomposes by the epistemic type of the error, and the gain comes from *field-level directed* feedback rather than mere retries — establishing where the evidence layer of live literary teaching can be engineered-governed and where governance necessarily fails.

## 2. Design (confirmatory)
- **Tasks:** all 18 (6 TGU × 3 types). **Headline analyses use the 12 confirmatory tasks** (all except dev = TGU2 Macbeth, TGU4 Tale of Two Cities, which were used to develop repair templates); dev tasks reported separately.
- **Conditions:** C1–C4 (M1 only C3/C4 for cost). Variant A for C1/C3 (single persona variant; deviation from formal's A+B, disclosed).
- **Models:** M2=deepseek-chat (official API, workhorse, 10 reps), M3=Qwen3-235B (OpenRouter, 10 reps), M4=deepseek-reasoner (5 reps; reasoning-cost/latency limited, disclosed, reported separately as a reasoning-model probe), M1=Mistral-Large (C3/C4 only, 5 reps). Frozen-log slugs differ from these API slugs → logged as DEVIATION; M3 showed −18pp on a C3 drift slice → each model contributes its OWN fresh k=0 baseline (no cross-run mixing).
- **Repair:** k ≤ 3 rounds. **Primary feedback arm = F3** (field-level failure flags, no correct values). Feedback-dose comparison (E1b) runs the four arms {resample, F1 binary, F2 category, F3 field} within-subject on the same k=0 failures.
- **Judge:** unchanged `harness/judge.py` (deterministic). Repair feedback is derived from the judge verdict; the SAME verdict function is the outcome — this circularity is addressed by design (§5).

## 3. Hypotheses (each has a preregistered fallback; direction is the test, not the sign)
- **H1a** (primary contrast): k≤3 F3 repair raises C3 strict rate by ≥10pp over its own k=0. Fallback if <5pp: reframe to "the verifier localizes but cannot drive repair → classroom errors are knowledge- not feedback-constrained"; the per-class un-repairability map is still the headline; deployment value = interception (zero-cost, 100% precise), not repair.
- **H1b**: at equal call budget, F3 repair > best-of-k blind resample (best-of-k derived zero-cost from the resample arm and from frozen 10-rep cells; E0 shows blind resampling saturates C3 at ~50.9% by k=4). Fallback if resample ties F3: "verifier-as-selector" story (value is selection not guidance); deployment → reject-and-resample (lower latency).
- **H2a**: repair rate ordering **locator-only > context-displacement > fabrication** (within grounded conditions). Fallback: any reversal is reported as a stronger finding about the true nature of that error class.
- **H2b**: fabrication repair rate C3 ≫ C1 (with window present, fabrication is an attention/retrieval failure → repairable; without window, a knowledge gap → not). This is where power lives: C1 has 171 fabrication failures in the frozen grid; the extension C1 arm samples these. Fallback: no window-modulation → "fabrication is a global generation habit."
- **H2c** (refined by smoke): the repair gain requires *field-level* specificity — F3 > F2 ≈ F1. Smoke showed F3 35% vs F1=F2 10%. Fallback if F2≈F3: category-level suffices (simpler feedback design); if F1≈F3: gain is retry-driven → merges with H1b.
- **H3a**: minimal schema S1 ≥ full template S2 (explains frozen C4≤C3). S0=C3, S2=C4 anchored to frozen; new: S1. Fallback: any monotone/flat result has a deployment-positive writeup.
- **H3b**: window size inverted-U (±300 evidence-poor, ±2700 attention-diluted vs ±900). Fallback: flat = "grounding robust to window size, teachers need not tune."
- **H3c** (position): **dropped** — E0 shows the ±900 windows are symmetric by construction (19/22 target sentences mid-window), so observational position analysis is uninformative; controlled position manipulation is not run.
- **H4a–c** (Phase 2, Chinese corpus): grounding direction, error-migration, and repairability-stratification replicate cross-language. **All confirmatory contrasts are within-language**; cross-language comparison is descriptive only (instrument non-equivalence: the ASCII-only normalizer outputs empty string on Chinese → a new instrument; memorization saturation of famous poems; window/target ratio ~30× for quatrains vs ~2× for novels). Memorization covariate (closed-book completion hit-rate) recorded.

## 4. Multiple comparisons
Primary = H1a only (one contrast). All others secondary/exploratory. Benjamini-Hochberg FDR at 0.05 within the secondary family. GEE clustered by task (`analysis/inferential_analysis.fit_gee`), with wild cluster bootstrap for the 12-task confirmatory set (small clusters). Repair process = discrete-time survival + error-class transition matrix.

## 5. Governance of the coach-judge identity (design-level, written into the paper)
The judge is a deterministic corpus-membership test; `strict_correct` IS the operational definition of the outcome — categorically different from an LLM-judge self-preference loop. Residual threats and locks:
- **No answer leakage:** F1–F3 feedback contains only error-category and field names, never correct strings; enforced at runtime by `repair_loop.assert_no_leak`; the three feedback templates are frozen here and published. F4 oracle arm (gives answers) is quarantined — capability upper bound only, excluded from all main claims.
- **Held-out:** repair templates/k/prompt-engineering developed only on 6 dev tasks; the 12 confirmatory tasks are the headline. Chinese repair templates transfer zero-shot (domain-level held-out).
- **Anti-Goodhart audit panel** (`guardrail_panel.py`, audit-only, never fed back): per-round quote-length distribution, evidence-record count, strict/defensible divergence, quote concentration (collapse to famous high-frequency lines). Any deterioration reported as "repair bought accuracy at the cost of X."
- **Evaluation triangulation:** threshold sensitivity (0.72→0.65/0.80, locator tolerance) re-judged over the whole grid at zero call cost; ~150–200 repaired-vs-original pairs blind-rated by teachers (Phase 3); adversarial judge set 40→~80 with items designed to game repair.

## 6. Downgrade lines (resource)
- M4 reps=5, M1 C3/C4-only: disclosed asymmetry; if a model is delisted, record replacement, treat as new model.
- Teacher study (Phase 3): if <8 teachers recruited, downgrade phrasing study to "expanded robustness"; the severity-κ anchoring (≥3 raters, double-blind, preregistered arbitration; report honestly if human severity overturns the automated 53.6/46.4 split) is retained.
- Budget hard cap $100 total; ledger `journal_extension/cost_ledger.csv`; $85 triggers a batched pause.

## 7. Analysis scripts (deterministic, reproducible)
`journal_extension/e0_reanalysis.py` (baseline), `repair_loop.py` (generation), `smoke_analysis.py` / `analysis_ext/*` (repair rates, class matrix, survival, dose-response), reused `analysis/inferential_analysis.py` (`cluster_bootstrap`, `fit_gee`). Every headline number regenerable from the ext logs by one script.
