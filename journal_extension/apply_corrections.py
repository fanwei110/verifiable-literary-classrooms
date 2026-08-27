"""共享的非破坏性裁判修正层：注入已核验 gold-locator 修正 + 缓存/记忆化加速。
被 rejudge.py 与 repair_loop.py（--corrected）共用，保证生成、再判分、分析三处一致。
不改动 tasks/*.yaml 与冻结日志。修正清单见 locator_corrections.json（含 provenance）。
"""
from __future__ import annotations

import copy
import functools
import json
from pathlib import Path

CORR = json.loads((Path(__file__).resolve().parent / "locator_corrections.json").read_text(encoding="utf-8"))
_by_task: dict[str, list] = {}
for _c in CORR["corrections"]:
    _by_task.setdefault(_c["task_id"], []).append(_c)


def patch(judge_mod) -> None:
    """对传入的 judge 模块施加：gold 修正 + load_corpus 缓存 + normalize_text 记忆化。幂等。"""
    if getattr(judge_mod, "_corrections_applied", False):
        return

    orig_load_task = judge_mod.load_task

    def patched_load_task(task_id: str) -> dict:
        task = copy.deepcopy(orig_load_task(task_id))
        for c in _by_task.get(task_id, []):
            for ev in task.get("expected_evidence", []):
                if str(ev.get("quote", "")).startswith(c["quote_prefix"]) and ev.get("locator") == c["old"]:
                    ev["locator"] = c["new"]
        return task

    judge_mod.load_task = patched_load_task

    _cache: dict = {}
    orig_load_corpus = judge_mod.load_corpus

    def cached_load_corpus():
        if "c" not in _cache:
            _cache["c"] = orig_load_corpus()
        return _cache["c"]

    judge_mod.load_corpus = cached_load_corpus

    if not getattr(judge_mod.normalize_text, "_memoized", False):
        mn = functools.lru_cache(maxsize=8192)(judge_mod.normalize_text)
        mn._memoized = True
        judge_mod.normalize_text = mn

    judge_mod._corrections_applied = True


def n_corrections() -> int:
    return len(CORR["corrections"])
