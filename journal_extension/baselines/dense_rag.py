"""基线：dense 检索式 RAG（回应"BM25 过弱/strawman"）。
本地 sentence-transformers(all-MiniLM-L6-v2) 段落嵌入 + NumPy 余弦检索，替代 oracle 窗口。
复用 bm25_rag 的分段/prompt/判分(condition=None 语料正确性)/gold-rank/used-retrieved，只换排序器。
两层分析口径与 BM25 一致，便于成阶梯对比。零 API 检索成本（仅生成走 API）。
用法：python journal_extension/baselines/dense_rag.py --tasks TGU3_T1,... --models M2 --reps 5 --topn 3 --workers 6
"""
from __future__ import annotations

import os
# 必须在 import sentence_transformers 之前设，避开 TF/Keras 冲突 + 用 HF 国内镜像
os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("USE_TORCH", "1")
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

import argparse
import datetime as dt
import hashlib
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "harness"))
sys.path.insert(0, str(ROOT / "journal_extension"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import judge as judge_mod  # noqa: E402
import yaml  # noqa: E402
from api_client import Client, EXT_MODELS  # noqa: E402
# 复用 bm25_rag 的辅助（import 时会 apply_corrections.patch(judge_mod)）
from bm25_rag import CORPUS, TASK_DIR, segment, build_prompt, gold_rank, _ws  # noqa: E402
from sentence_transformers import SentenceTransformer  # noqa: E402

_MODEL = None
_emb_cache: dict[str, tuple] = {}


def model():
    global _MODEL
    if _MODEL is None:
        _MODEL = SentenceTransformer("all-MiniLM-L6-v2")
    return _MODEL


def work_index(work_id: str):
    """段落列表 + 归一化嵌入矩阵（缓存）。"""
    if work_id not in _emb_cache:
        segs = segment(CORPUS[work_id]["clean_text"])
        emb = model().encode(segs, batch_size=64, show_progress_bar=False,
                             normalize_embeddings=True)
        _emb_cache[work_id] = (segs, np.asarray(emb, dtype=np.float32))
    return _emb_cache[work_id]


def rank(query: str, emb: np.ndarray) -> list[int]:
    q = model().encode([query], normalize_embeddings=True)[0].astype(np.float32)
    sims = emb @ q  # 已归一化 → 点积=余弦
    return list(np.argsort(-sims))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", required=True)
    ap.add_argument("--models", default="M2")
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--topn", type=int, default=3)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--tag", default="dense")
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
        segs, emb = work_index(task["work_id"])
        # 与 BM25 同源的查询语义（主题为主），dense 用自然语言串
        query = f"{task.get('theme','')}. {task.get('task_type_label','')} quotation from {task.get('work_title','')}"
        ranking = rank(query, emb)
        top = [segs[i] for i in ranking[:args.topn]]
        gr = gold_rank(task, segs, ranking)
        prompt = build_prompt(task, top)
        for m in models:
            for rep in range(1, args.reps + 1):
                rid = f"dense_{m}_{t}_r{rep:02d}"
                if rid not in done:
                    jobs.append((rid, m, t, rep, prompt, gr))

    print(f"dense-RAG jobs: {len(jobs)} (skipped {len(done)})")
    client = Client()
    lock = threading.Lock()

    def worker(job):
        rid, m, t, rep, prompt, gr = job
        text, meta, latency = client.chat(m, [{"role": "user", "content": prompt}], tag=f"{args.tag}:{m}")
        verdict = judge_mod.judge(t, text, condition=None)
        used = False
        for md in (verdict.get("match_details") or []):
            q = _ws(str(md.get("quote", "")))
            if len(q) >= 15 and q in _ws(prompt):
                used = True
                break
        rec = {"run_id": rid, "baseline": "dense_rag", "model": m,
               "task_id": t, "condition": "DENSE", "repetition": rep, "topn": args.topn,
               "gold_seg_rank": gr, "used_retrieved_quote": used,
               "timestamp_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
               "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
               "completion": text, "judge": verdict,
               "strict_correct": bool(verdict.get("strict_correct")),
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
