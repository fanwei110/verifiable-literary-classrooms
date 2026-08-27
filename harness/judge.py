"""JSON evidence judge for the verifiable-classroom benchmark."""

from __future__ import annotations

import json
import re
import string
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
TASK_DIR = ROOT / "tasks"
CORPUS_INDEX = ROOT / "corpus" / "processed" / "corpus_index.json"


def normalize_text(text: str) -> str:
    text = text or ""
    trans = {
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2014": "-",
        "\u2013": "-",
    }
    for src, dst in trans.items():
        text = text.replace(src, dst)
    keep = []
    for ch in text.lower():
        if ch in string.ascii_lowercase + string.digits:
            keep.append(ch)
        elif ch.isspace() or ch in string.punctuation:
            keep.append(" ")
    return re.sub(r"\s+", " ", "".join(keep)).strip()


def normalize_name(text: str) -> str:
    return normalize_text(text)


def load_task(task_id: str) -> dict[str, Any]:
    path = TASK_DIR / f"{task_id}.yaml"
    if not path.exists():
        raise FileNotFoundError(path)
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_corpus() -> dict[str, Any]:
    return json.loads(CORPUS_INDEX.read_text(encoding="utf-8"))


def extract_json_object(text: str) -> tuple[dict[str, Any] | None, str | None]:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S | re.I)
    candidates = []
    if fence:
        candidates.append(fence.group(1))
    brace_start = text.find("{")
    brace_end = text.rfind("}")
    if brace_start >= 0 and brace_end > brace_start:
        candidates.append(text[brace_start : brace_end + 1])
    candidates.append(text)
    for candidate in candidates:
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict):
                return obj, None
        except json.JSONDecodeError as exc:
            last = str(exc)
    return None, last if "last" in locals() else "no JSON object found"


def locator_match(claimed: str, actual: str) -> bool:
    c = canonical_locator(claimed)
    a = canonical_locator(actual)
    if not c or not a:
        return False
    if a in c or c in a:
        return True
    # Allow compact drama notations such as "Act III Scene I" vs "Act Iii, Scene I".
    c_tokens = set(c.split())
    a_tokens = set(a.split())
    return bool(a_tokens) and len(c_tokens & a_tokens) / len(a_tokens) >= 0.75


def roman_to_int(token: str) -> int | None:
    values = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}
    total = 0
    prev = 0
    if not token or any(ch not in values for ch in token.lower()):
        return None
    for ch in reversed(token.lower()):
        cur = values[ch]
        if cur < prev:
            total -= cur
        else:
            total += cur
            prev = cur
    return total


def canonical_locator(text: str) -> str:
    raw = normalize_text(text)
    out = []
    for token in raw.split():
        roman = roman_to_int(token)
        if roman is not None:
            out.append(str(roman))
        else:
            out.append(token)
    return " ".join(out)


def has_version_note(obj: dict[str, Any]) -> bool:
    text = " ".join(
        str(obj.get(k, "")) for k in ("limits", "answer")
    ).lower()
    return any(
        word in text
        for word in (
            "version",
            "translation",
            "edition",
            "wording",
            "paraphrase",
            "uncertain",
            "variant",
        )
    )


def find_in_segments(quote: str, work: dict[str, Any]) -> dict[str, Any] | None:
    nq = normalize_text(quote)
    if not nq:
        return None
    for segment in work["segments"]:
        if nq in normalize_text(segment["text"]):
            return segment
    if nq in normalize_text(work["clean_text"]):
        return {"locator": "Corpus-level match", "text": work["clean_text"]}
    return None


def approximate_expected(quote: str, expected: list[dict[str, Any]]) -> tuple[float, dict[str, Any] | None]:
    nq = normalize_text(quote)
    best_score = 0.0
    best = None
    for ev in expected:
        score = SequenceMatcher(None, nq, normalize_text(ev["quote"])).ratio()
        if score > best_score:
            best_score = score
            best = ev
    return best_score, best


def evidence_result(
    record: dict[str, Any],
    task: dict[str, Any],
    corpus: dict[str, Any],
    condition: str | None,
    version_note: bool,
) -> dict[str, Any]:
    work = corpus[task["work_id"]]
    quote = str(record.get("quote", ""))
    found_segment = find_in_segments(quote, work)
    expected = task["expected_evidence"]
    approx_score, approx_ev = approximate_expected(quote, expected)

    claimed_author = normalize_name(str(record.get("author", "")))
    claimed_work = normalize_name(str(record.get("work", "")))
    author_ok = claimed_author == normalize_name(task["author"])
    work_ok = claimed_work == normalize_name(task["work_title"])

    locator_ok = False
    speaker_ok = False
    grounded_ok = True
    matched_expected = None
    if found_segment is not None:
        for ev in expected:
            if normalize_text(ev["quote"]) in normalize_text(quote) or normalize_text(quote) in normalize_text(ev["quote"]):
                matched_expected = ev
                break
        if matched_expected is None:
            matched_expected = approx_ev
        if matched_expected is not None:
            locator_ok = locator_match(str(record.get("locator", "")), matched_expected["locator"])
            speaker_ok = normalize_name(matched_expected["speaker_or_narrator"]) in normalize_name(
                str(record.get("speaker_or_narrator", ""))
            )
            if condition in {"C3", "C4"}:
                grounded_ok = normalize_text(quote) in normalize_text(matched_expected["source_window"])

    strict = bool(found_segment and author_ok and work_ok and locator_ok and speaker_ok and grounded_ok)
    defensible = strict
    error = None
    if not strict:
        if found_segment is None:
            if approx_score >= 0.72:
                error = "version_drift"
                defensible = version_note and author_ok and work_ok
            else:
                error = "fabricated_quotation"
        elif not author_ok or not work_ok:
            error = "misattribution"
        elif not locator_ok or not speaker_ok or not grounded_ok:
            error = "context_displacement"
        else:
            error = "fabricated_quotation"

    return {
        "quote": quote,
        "quote_found": found_segment is not None,
        "actual_locator": found_segment["locator"] if found_segment else None,
        "claimed_author_ok": author_ok,
        "claimed_work_ok": work_ok,
        "locator_ok": locator_ok,
        "speaker_ok": speaker_ok,
        "grounded_ok": grounded_ok,
        "approx_score": round(approx_score, 3),
        "strict": strict,
        "defensible": defensible,
        "error_class_candidate": error,
    }


def judge(task_id: str, completion_text: str, condition: str | None = None) -> dict[str, Any]:
    task = load_task(task_id)
    corpus = load_corpus()
    obj, parse_error = extract_json_object(completion_text)
    if obj is None:
        return {
            "task_id": task_id,
            "condition": condition,
            "strict_correct": False,
            "defensible_correct": False,
            "bucket": "format_failure",
            "error_class_candidate": "format_failure",
            "parse_error": parse_error,
            "match_details": [],
        }
    evidence = obj.get("evidence")
    if not isinstance(evidence, list) or len(evidence) < task["required_evidence_count"]:
        return {
            "task_id": task_id,
            "condition": condition,
            "strict_correct": False,
            "defensible_correct": False,
            "bucket": "format_failure",
            "error_class_candidate": "format_failure",
            "parse_error": "missing or too few evidence records",
            "match_details": [],
        }
    version_note = has_version_note(obj)
    details = [
        evidence_result(record, task, corpus, condition, version_note)
        for record in evidence[: task["required_evidence_count"]]
        if isinstance(record, dict)
    ]
    if len(details) < task["required_evidence_count"]:
        return {
            "task_id": task_id,
            "condition": condition,
            "strict_correct": False,
            "defensible_correct": False,
            "bucket": "format_failure",
            "error_class_candidate": "format_failure",
            "parse_error": "evidence record is not an object",
            "match_details": details,
        }
    strict_correct = all(d["strict"] for d in details)
    defensible_correct = all(d["defensible"] for d in details)
    if strict_correct:
        bucket = "strict_correct"
        error = None
    elif defensible_correct:
        bucket = "defensible_correct"
        error = "version_drift"
    else:
        bucket = "wrong"
        error = next((d["error_class_candidate"] for d in details if d["error_class_candidate"]), "fabricated_quotation")
    return {
        "task_id": task_id,
        "condition": condition,
        "strict_correct": strict_correct,
        "defensible_correct": defensible_correct,
        "bucket": bucket,
        "error_class_candidate": error,
        "version_note": version_note,
        "match_details": details,
    }


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("task_id")
    ap.add_argument("completion_file", type=Path)
    ap.add_argument("--condition")
    args = ap.parse_args()
    print(json.dumps(judge(args.task_id, args.completion_file.read_text(encoding="utf-8"), args.condition), indent=2))
