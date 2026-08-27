"""中文确定性裁判（镜像 harness/judge.py，用 normalize_zh）。
关键差异：
- 最短引文规则 MIN_ZH_LEN：规范化后 < N 字的"引文"不算有效引用（防短语子串假阳性，如"仁""學"）。
- locator 按篇匹配（论语按篇引用）；篇核（去"第X"）子串匹配以容"論語·學而""學而篇"等写法。
- version_drift 用字符级 SequenceMatcher（阈值待校准，暂 0.72）。
"""
from __future__ import annotations

import json
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from normalize_zh import normalize_zh  # noqa: E402

CORPUS_PATH = ROOT / "corpus_zh" / "processed" / "corpus_index_zh.json"
TASK_DIR = ROOT / "tasks_zh"
MIN_ZH_LEN = 5          # 最短有效引文（规范化后字数）
DRIFT_THRESHOLD = 0.72  # version_drift 阈值（字符级）

_corpus_cache = None
_zh_num = "零一二三四五六七八九十百"


def load_corpus():
    global _corpus_cache
    if _corpus_cache is None:
        _corpus_cache = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    return _corpus_cache


def load_task(task_id: str) -> dict:
    return json.loads((TASK_DIR / f"{task_id}.json").read_text(encoding="utf-8"))


def extract_json_object(text: str):
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None, "no JSON object found"
    for cand in (m.group(0), text[text.find("{"):text.rfind("}") + 1]):
        try:
            return json.loads(cand), None
        except Exception as e:
            err = str(e)
    return None, err


def _pian_core(loc_norm: str) -> str:
    """去掉'第一/第二…'得到篇核（学而第一→学而）。"""
    return re.sub(r"第[" + _zh_num + r"]+", "", loc_norm)


def locator_match(claimed: str, expected: str) -> bool:
    c, e = normalize_zh(claimed), normalize_zh(expected)
    if not c or not e:
        return False
    if e in c or c in e:
        return True
    core = _pian_core(e)
    return bool(core) and core in c


def find_in_corpus(quote_norm: str, work: dict):
    for seg in work["segments"]:
        if quote_norm in normalize_zh(seg["text"]):
            return seg
    if quote_norm in normalize_zh(work["clean_text"]):
        return {"locator": "篇级匹配", "text": work["clean_text"]}
    return None


def approx_expected(quote_norm: str, expected: list):
    best, best_ev = 0.0, None
    for ev in expected:
        s = SequenceMatcher(None, quote_norm, normalize_zh(ev["quote"])).ratio()
        if s > best:
            best, best_ev = s, ev
    return best, best_ev


def evidence_result(record: dict, task: dict, corpus: dict, condition):
    work = corpus[task["work_id"]]
    quote = str(record.get("quote", ""))
    qn = normalize_zh(quote)
    too_short = len(qn) < MIN_ZH_LEN
    found = None if too_short else find_in_corpus(qn, work)
    approx, approx_ev = approx_expected(qn, task["expected_evidence"])

    author_ok = normalize_zh(str(record.get("work", ""))) in normalize_zh(task["work_title"]) or \
        normalize_zh(task["work_title"]) in normalize_zh(str(record.get("work", "")))
    locator_ok = speaker_ok = False
    grounded_ok = True
    matched = None
    if found is not None:
        for ev in task["expected_evidence"]:
            en = normalize_zh(ev["quote"])
            if en and (en in qn or qn in en):
                matched = ev
                break
        matched = matched or approx_ev
        if matched is not None:
            locator_ok = locator_match(str(record.get("locator", "")), matched["locator"])
            spk_claimed = normalize_zh(str(record.get("speaker_or_narrator", "")))
            spk_exp = normalize_zh(matched["speaker_or_narrator"])
            speaker_ok = bool(spk_exp) and (spk_exp in spk_claimed or spk_claimed in spk_exp)
            if condition in {"C3", "C4"}:
                grounded_ok = qn in normalize_zh(matched.get("source_window", ""))

    strict = bool(found and author_ok and locator_ok and speaker_ok and grounded_ok)
    error = None
    if not strict:
        if too_short:
            error = "too_short_or_format"
        elif found is None:
            error = "version_drift" if approx >= DRIFT_THRESHOLD else "fabricated_quotation"
        elif not author_ok:
            error = "misattribution"
        elif not (locator_ok and speaker_ok and grounded_ok):
            error = "context_displacement"
        else:
            error = "fabricated_quotation"
    return {
        "quote": quote, "quote_found": found is not None, "too_short": too_short,
        "actual_locator": found["locator"] if found else None,
        "claimed_work_ok": author_ok, "locator_ok": locator_ok, "speaker_ok": speaker_ok,
        "grounded_ok": grounded_ok, "approx_score": round(approx, 3),
        "strict": strict, "error_class_candidate": error,
    }


def judge_zh(task_id: str, completion_text: str, condition=None) -> dict:
    task = load_task(task_id)
    corpus = load_corpus()
    obj, perr = extract_json_object(completion_text)
    if obj is None or not isinstance(obj.get("evidence"), list) or \
            len(obj["evidence"]) < task.get("required_evidence_count", 1):
        return {"task_id": task_id, "condition": condition, "strict_correct": False,
                "bucket": "format_failure", "error_class_candidate": "format_failure",
                "parse_error": perr or "missing/too few evidence", "match_details": []}
    n = task.get("required_evidence_count", 1)
    details = [evidence_result(r, task, corpus, condition)
               for r in obj["evidence"][:n] if isinstance(r, dict)]
    if len(details) < n:
        return {"task_id": task_id, "condition": condition, "strict_correct": False,
                "bucket": "format_failure", "error_class_candidate": "format_failure",
                "match_details": details}
    strict = all(d["strict"] for d in details)
    err = None if strict else next((d["error_class_candidate"] for d in details if d["error_class_candidate"]), "fabricated_quotation")
    return {"task_id": task_id, "condition": condition, "strict_correct": strict,
            "bucket": "strict_correct" if strict else "wrong",
            "error_class_candidate": err, "match_details": details}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("task_id")
    ap.add_argument("completion")
    ap.add_argument("--condition", default=None)
    a = ap.parse_args()
    print(json.dumps(judge_zh(a.task_id, a.completion, a.condition), ensure_ascii=False, indent=1))
