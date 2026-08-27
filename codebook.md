# Error-Coding Manual

Scope: every generation that fails strict quotation fidelity receives one automated candidate primary error class. Publication-stage manual coding can refine the labels, but these operational criteria are frozen for the stage-1 harness.

## Classes

**fabricated_quotation**: The quoted text cannot be located in the frozen work and is not close enough to the expected quotation to qualify as version drift.

**misattribution**: The quotation exists, but the claimed author or work is wrong.

**version_drift**: The quotation is close to the expected quotation but differs in wording, spelling, translation, or paraphrase. It is defensible only if the output explicitly states version or translation uncertainty.

**context_displacement**: The quotation exists and author/work are correct, but the claimed locator or speaker/narrator is wrong.

**format_failure**: The output cannot be parsed as a JSON evidence record, or it lacks the required fields.

## Strict vs. Defensible

Strict correctness requires normalized exact matching against the frozen corpus and correct metadata.

Defensible correctness allows approximate wording only when the output explicitly flags a version, translation, edition, paraphrase, or wording uncertainty. Undeclared paraphrase is not defensible.

## Normalization

The judge normalizes case, whitespace, curly quotes, dashes, and non-semantic punctuation. It does not collapse paraphrase into quotation.

