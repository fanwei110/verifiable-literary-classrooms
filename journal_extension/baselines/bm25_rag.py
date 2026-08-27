"""基线：BM25 检索式 RAG（替代 oracle 窗口）。
在冻结语料 clean_text 上分段 → BM25 检索 top-N 段作为"证据窗口" → 跑 grounded 提示。
检验"接地增益是否依赖完美 oracle 窗口"：若 C1 < BM25-RAG < C3(oracle)，说明检索质量可插值。
strict_correct 由语料成员判定（与窗口无关），是主指标；另记 gold 段召回名次。
用法：python journal_extension/baselines/bm25_rag.py --tasks TGU3_T1,... --models M2 --reps 5 --topn 3 --workers 6
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import re
import sys
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "harness"))
sys.path.insert(0, str(ROOT / "journal_extension"))

import judge as judge_mod  # noqa: E402
import yaml  # noqa: E402
from api_client import Client, EXT_MODELS  # noqa: E402
import apply_corrections  # noqa: E402
apply_corrections.patch(judge_mod)  # 基线同用已核验 gold 修正

TASK_DIR = ROOT / "tasks"
PROMPT_DIR = ROOT / "prompts"
CORPUS = json.loads((ROOT / "corpus" / "processed" / "corpus_index.json").read_text(encoding="utf-8"))
_TOK = re.compile(r"[a-z0-9]+")


def tok(s: str) -> list[str]:
    return _TOK.findall(s.lower())


def segment(text: str, seg_chars: int = 700, overlap: int = 150) -> list[str]:
    """按段落聚合到 ~seg_chars 的重叠片段。"""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    segs, cur = [], ""
    for p in paras:
        if len(cur) + len(p) > seg_chars and cur:
            segs.append(cur)
            cur = cur[-overlap:] + "\n\n" + p
        else:
            cur = (cur + "\n\n" + p) if cur else p
    if cur:
        segs.append(cur)
    return segs


class BM25:
    def __init__(self, docs: list[list[str]], k1=1.5, b=0.75):
        self.docs, self.k1, self.b = docs, k1, b
        self.N = len(docs)
        self.avgdl = sum(len(d) for d in docs) / max(self.N, 1)
        self.df = Counter()
        for d in docs:
            for t in set(d):
                self.df[t] += 1
        self.idf = {t: math.log(1 + (self.N - n + 0.5) / (n + 0.5)) for t, n in self.df.items()}
        self.tf = [Counter(d) for d in docs]

    def score(self, q: list[str], i: int) -> float:
        d, dl, s = self.tf[i], len(self.docs[i]), 0.0
        for t in q:
            if t not in d:
                continue
            f = d[t]
            s += self.idf.get(t, 0) * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
        return s

    def rank(self, q: list[str]) -> list[int]:
        qs = [(self.score(q, i), i) for i in range(self.N)]
        qs.sort(reverse=True)
        return [i for _, i in qs]


_bm25_cache: dict[str, tuple] = {}


def work_index(work_id: str):
    if work_id not in _bm25_cache:
        segs = segment(CORPUS[work_id]["clean_text"])
        _bm25_cache[work_id] = (segs, BM25([tok(s) for s in segs]))
    return _bm25_cache[work_id]


def build_prompt(task: dict, retrieved: list[str]) -> str:
    """复用 C3 指令头 + schema 尾，仅把 oracle 窗口替换为 BM25 检索窗口。
    注意：schema/输出格式说明位于 oracle 窗口**之后**，必须保留，否则模型不输出 JSON。"""
    c3 = (PROMPT_DIR / "C3_grounded" / f"{task['task_id']}_A.md").read_text(encoding="utf-8")
    head = c3.split("Frozen source excerpt(s):")[0].rstrip()
    marker = "Return only one valid JSON object"
    tail = c3[c3.index(marker):] if marker in c3 else ""
    body = "\n\n".join(f"[Retrieved excerpt {i+1}]\n{seg}" for i, seg in enumerate(retrieved))
    return (f"{head}\n\nFrozen source excerpt(s) (retrieved by BM25, may be imperfect):\n"
            f"{body}\n\n{tail}")


def _ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def gold_rank(task: dict, segs: list[str], ranking: list[int]) -> int:
    """gold 引文所在段在检索名次（1-based；-1 表示未命中任何段）。规范化空白后匹配。"""
    q = _ws(task["expected_evidence"][0].get("quote") or "")[:50]
    gold_segs = {i for i, s in enumerate(segs) if q and q in _ws(s)}
    for rank, i in enumerate(ranking, 1):
        if i in gold_segs:
            return rank
    return -1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", required=True)
    ap.add_argument("--models", default="M2")
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--topn", type=int, default=3)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--tag", default="bm25")
    args = ap.parse_args()

    tasks = args.tasks.split(",")
    models = args.models.split(",")
    outdir = ROOT / "runs" / "raw" / f"ext_{args.tag}"
    outdir.mkdir(parents=True, exist_ok=True)
    log_path = outdir / f"{args.tag}.jsonl"
    done = set()
    if log_path.exists():
        done = {json.loads(l)["run_id"] for l in log_path.read_text(encoding="utf-8").splitlines() if l.strip()}

    jobs = []
    for t in tasks:
        task = yaml.safe_load((TASK_DIR / f"{t}.yaml").read_text(encoding="utf-8"))
        segs, bm = work_index(task["work_id"])
        query = tok(task.get("theme", "") + " " + task.get("task_type_label", "") + " quotation")
        ranking = bm.rank(query)
        top = [segs[i] for i in ranking[:args.topn]]
        gr = gold_rank(task, segs, ranking)
        prompt = build_prompt(task, top)
        for m in models:
            for rep in range(1, args.reps + 1):
                rid = f"bm25_{m}_{t}_r{rep:02d}"
                if rid not in done:
                    jobs.append((rid, m, t, rep, task, prompt, gr))

    print(f"BM25-RAG jobs: {len(jobs)} (skipped {len(done)})")
    client = Client()
    lock = threading.Lock()

    def worker(job):
        rid, m, t, rep, task, prompt, gr = job
        text, meta, latency = client.chat(m, [{"role": "user", "content": prompt}],
                                          tag=f"{args.tag}:{m}")
        # condition=None → 不做 grounded-vs-oracle 检查，strict_correct = 语料正确性（与 C1 口径可比）
        verdict = judge_mod.judge(t, text, condition=None)
        # 模型是否从检索窗口取引文（在 prompt 中出现）
        used_retrieved = False
        for md in (verdict.get("match_details") or []):
            q = _ws(str(md.get("quote", "")))
            if len(q) >= 15 and q in _ws(prompt):
                used_retrieved = True
                break
        rec = {"run_id": rid, "baseline": "bm25_rag", "model": m,
               "model_slug": EXT_MODELS[m]["slug"], "task_id": t, "condition": "BM25",
               "repetition": rep, "topn": args.topn, "gold_seg_rank": gr,
               "timestamp_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
               "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
               "completion": text, "judge": verdict,
               "strict_correct": bool(verdict.get("strict_correct")),
               "used_retrieved_quote": used_retrieved,
               "usage": meta.get("usage"), "latency_s": round(latency, 2)}
        with lock:
            with log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return rid

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(worker, j) for j in jobs]
        for i, fut in enumerate(as_completed(futs), 1):
            fut.result()
            if i % 20 == 0 or i == len(jobs):
                print(f"[{i}/{len(jobs)}] spent=${client.spent():.2f}")
    print(f"done. ledger total = ${client.spent():.2f}")


if __name__ == "__main__":
    main()
