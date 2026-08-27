"""基线：copy-first 两步提示（脚手架，非闭环）。
在 C3(oracle 窗口) 基础上，强制模型先逐字转写候选句，再产出结构化答案。
检验"简单提示脚手架能否替代验证-修复闭环"——若 copy-first ≈ C3 闭环，则闭环无净价值。
用法：python journal_extension/baselines/copy_first.py --tasks TGU3_T1,... --models M2 --reps 5 --workers 6
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "harness"))
sys.path.insert(0, str(ROOT / "journal_extension"))

import judge as judge_mod  # noqa: E402
from api_client import Client, EXT_MODELS  # noqa: E402
import apply_corrections  # noqa: E402
apply_corrections.patch(judge_mod)  # 基线同用已核验 gold 修正

PROMPT_DIR = ROOT / "prompts"

SCAFFOLD = (
    "\n\nBefore answering, silently perform these steps:\n"
    "1. Transcribe verbatim (character-for-character) up to three candidate sentences "
    "that appear in the excerpt above and fit the request.\n"
    "2. Choose the single best candidate and confirm it appears exactly in the excerpt.\n"
    "3. Output ONLY the final JSON object with the required schema — do not include your "
    "transcription steps in the output.\n"
    "Quote only text you can find verbatim in the excerpt."
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", required=True)
    ap.add_argument("--models", default="M2")
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--tag", default="copyfirst")
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
        base = (PROMPT_DIR / "C3_grounded" / f"{t}_A.md").read_text(encoding="utf-8")
        prompt = base.rstrip() + SCAFFOLD
        for m in models:
            for rep in range(1, args.reps + 1):
                rid = f"copyfirst_{m}_{t}_r{rep:02d}"
                if rid not in done:
                    jobs.append((rid, m, t, rep, prompt))

    print(f"copy-first jobs: {len(jobs)} (skipped {len(done)})")
    client = Client()
    lock = threading.Lock()

    def worker(job):
        rid, m, t, rep, prompt = job
        text, meta, latency = client.chat(m, [{"role": "user", "content": prompt}],
                                          tag=f"{args.tag}:{m}")
        verdict = judge_mod.judge(t, text, condition="C3")
        rec = {"run_id": rid, "baseline": "copy_first", "model": m,
               "model_slug": EXT_MODELS[m]["slug"], "task_id": t, "condition": "COPYFIRST",
               "repetition": rep,
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
