"""非破坏性再判分：注入已核验的 gold-locator 修正，对已存 completion 重新判分（零 API 成本）。
不改动 tasks/*.yaml 与冻结日志——通过 monkeypatch load_task 注入修正。
用法：
  python journal_extension/rejudge.py --log runs/raw/ext_e1a_m2/e1a_m2.jsonl          # 修复轮日志
  python journal_extension/rejudge.py --log runs/raw/formal/formal.jsonl --flat        # 平铺生成日志
输出：同目录 *_corr.jsonl + 打印 before/after strict 汇总。
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "harness"))
import judge as judge_mod  # noqa: E402

CORR = json.loads((Path(__file__).resolve().parent / "locator_corrections.json").read_text(encoding="utf-8"))
_by_task: dict[str, list] = {}
for c in CORR["corrections"]:
    _by_task.setdefault(c["task_id"], []).append(c)

_orig_load = judge_mod.load_task

# 缓存语料加载（行为等价，仅加速大批量再判分）
_corpus_cache = {}
_orig_load_corpus = judge_mod.load_corpus


def cached_load_corpus():
    if "c" not in _corpus_cache:
        _corpus_cache["c"] = _orig_load_corpus()
    return _corpus_cache["c"]


judge_mod.load_corpus = cached_load_corpus

# 记忆化 normalize_text：裁判对每次调用都会规范化整篇 clean_text（数 MB）与全部分段，
# 缓存后重复串（同一语料对象）变 O(1)，大批量再判分从数分钟降到数秒。行为等价。
import functools  # noqa: E402
if not getattr(judge_mod.normalize_text, "_memoized", False):
    _mn = functools.lru_cache(maxsize=4096)(judge_mod.normalize_text)
    _mn._memoized = True
    judge_mod.normalize_text = _mn


def patched_load_task(task_id: str) -> dict:
    task = copy.deepcopy(_orig_load(task_id))
    for c in _by_task.get(task_id, []):
        for ev in task.get("expected_evidence", []):
            if str(ev.get("quote", "")).startswith(c["quote_prefix"]) and ev.get("locator") == c["old"]:
                ev["locator"] = c["new"]
    return task


def rejudge_record_repair(rec: dict) -> dict:
    rec = copy.deepcopy(rec)
    for rd in rec["rounds"]:
        rd["judge"] = judge_mod.judge(rec["task_id"], rd["completion"], condition=rec["condition"])
    rec["k0_strict"] = bool(rec["rounds"][0]["judge"].get("strict_correct"))
    rec["final_strict"] = bool(rec["rounds"][-1]["judge"].get("strict_correct"))
    return rec


def rejudge_record_flat(rec: dict) -> dict:
    rec = copy.deepcopy(rec)
    comp = rec.get("completion") or rec.get("completion_text") or ""
    cond = rec.get("condition")
    v = judge_mod.judge(rec.get("task_id"), comp, condition=cond)
    rec["judge"] = v
    rec["strict_correct"] = bool(v.get("strict_correct"))
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", required=True)
    ap.add_argument("--flat", action="store_true", help="平铺日志（单 completion，无 rounds）")
    args = ap.parse_args()
    judge_mod.load_task = patched_load_task  # 注入修正

    src = Path(args.log)
    rows = [json.loads(l) for l in src.read_text(encoding="utf-8").splitlines() if l.strip()]
    out = src.with_name(src.stem + "_corr.jsonl")

    before = after = n = 0
    corrected_rows = []
    for r in rows:
        if args.flat:
            b = bool(r.get("strict_correct", r.get("judge", {}).get("strict_correct")))
            nr = rejudge_record_flat(r)
            a = nr["strict_correct"]
        else:
            b = bool(r.get("k0_strict"))
            nr = rejudge_record_repair(r)
            a = nr["k0_strict"]
        before += int(b); after += int(a); n += 1
        corrected_rows.append(nr)
    out.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in corrected_rows) + "\n", encoding="utf-8")

    unit = "generations" if args.flat else "k0 groups"
    print(f"re-judged {n} {unit} from {src.name}")
    print(f"  strict% BEFORE = {100*before/n:.1f}%  ->  AFTER (locator-corrected) = {100*after/n:.1f}%  (+{100*(after-before)/n:.1f}pp)")
    print(f"  -> {out}")


if __name__ == "__main__":
    main()
