"""OpenRouter runner for pilot and formal generations.

The runner reads the API key from --key-file or OPENROUTER_API_KEY and never
writes it to logs. Formal runs should only be started after the corpus, tasks,
prompts, and judge are frozen in preregistration.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "harness"))
from judge import judge  # noqa: E402

CONFIG = yaml.safe_load((ROOT / "config" / "models.yaml").read_text(encoding="utf-8"))


def read_api_key(key_file: str | None) -> str:
    if key_file:
        text = Path(key_file).read_text(encoding="utf-8")
        key_prefix = "sk" + "-or-"
        match = re.search(re.escape(key_prefix) + r"[A-Za-z0-9_-]+", text)
        if not match:
            raise SystemExit("no OpenRouter key found in key file")
        return match.group(0)
    key = os.environ.get(CONFIG["api"]["key_env_var"], "")
    if not key:
        raise SystemExit("no API key; pass --key-file or set OPENROUTER_API_KEY")
    return key


def call_openrouter(model_slug: str, prompt: str, api_key: str) -> tuple[str, dict, float]:
    url = CONFIG["api"]["base_url"].rstrip("/") + "/chat/completions"
    body = {
        "model": model_slug,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": CONFIG["decoding"]["max_tokens"],
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    last_error = None
    backoffs = CONFIG["api"]["retry_backoff_seconds"]
    for attempt in range(CONFIG["api"]["max_retries"] + 1):
        try:
            t0 = time.perf_counter()
            response = requests.post(url, json=body, headers=headers, timeout=CONFIG["api"]["timeout_seconds"])
            elapsed = time.perf_counter() - t0
            if response.status_code in (429, 500, 502, 503, 504):
                last_error = f"HTTP {response.status_code}: {response.text[:200]}"
            else:
                response.raise_for_status()
                data = response.json()
                text = data["choices"][0]["message"].get("content") or ""
                meta = {
                    "provider": data.get("provider"),
                    "model_id": data.get("model"),
                    "usage": data.get("usage"),
                    "finish_reason": data["choices"][0].get("finish_reason"),
                }
                return text, meta, elapsed
        except (requests.RequestException, KeyError, ValueError) as exc:
            last_error = repr(exc)
        if attempt < CONFIG["api"]["max_retries"]:
            time.sleep(backoffs[min(attempt, len(backoffs) - 1)])
    raise RuntimeError(f"API failed after retries: {last_error}")


def prompt_path(condition: str, task_id: str, variant: str) -> Path:
    if condition == "C1":
        return ROOT / "prompts" / "C1_simulated" / f"{task_id}_{variant}.md"
    if condition == "C2":
        return ROOT / "prompts" / "C2_structured" / f"{task_id}.md"
    if condition == "C3":
        return ROOT / "prompts" / "C3_grounded" / f"{task_id}_{variant}.md"
    if condition == "C4":
        return ROOT / "prompts" / "C4_tgu" / f"{task_id}.md"
    raise ValueError(condition)


def build_jobs(
    models: list[str],
    conditions: list[str],
    tasks: list[str],
    reps: int,
    requested_variants: list[str],
) -> list[dict]:
    jobs = []
    for task_id in tasks:
        for condition in conditions:
            variants = requested_variants if condition in {"C1", "C3"} else ["canonical"]
            for variant in variants:
                rep_count = reps
                for model in models:
                    for rep in range(1, rep_count + 1):
                        jobs.append(
                            {
                                "task_id": task_id,
                                "condition": condition,
                                "variant": variant,
                                "model": model,
                                "rep": rep,
                                "run_id": f"{model}_{condition}_{task_id}_{variant}_r{rep:02d}",
                            }
                        )
    return jobs


def existing_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    ids = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            ids.add(json.loads(line)["run_id"])
        except (json.JSONDecodeError, KeyError):
            continue
    return ids


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--key-file")
    ap.add_argument("--models", default="M1,M2,M3")
    ap.add_argument("--conditions", default="C1,C2,C3,C4")
    ap.add_argument("--tasks", required=True, help="comma list or 'all'")
    ap.add_argument("--reps", type=int, default=1)
    ap.add_argument("--max-jobs", type=int, default=0)
    ap.add_argument("--variants", default="A", help="C1/C3 variants: A, B, or A,B")
    args = ap.parse_args()

    if args.tag == "formal" and not CONFIG.get("locked"):
        raise SystemExit("config/models.yaml is not locked; refusing formal run")

    api_key = read_api_key(args.key_file)
    models = args.models.split(",")
    conditions = args.conditions.split(",")
    if args.tasks == "all":
        tasks = sorted(path.stem for path in (ROOT / "tasks").glob("TGU*_T*.yaml"))
    else:
        tasks = args.tasks.split(",")
    variants = args.variants.split(",")
    for variant in variants:
        if variant not in {"A", "B"}:
            raise SystemExit("--variants must be A, B, or A,B")

    outdir = ROOT / "runs" / "raw" / args.tag
    outdir.mkdir(parents=True, exist_ok=True)
    completion_dir = outdir / "completions"
    completion_dir.mkdir(exist_ok=True)
    log_path = outdir / f"{args.tag}.jsonl"
    done = existing_ids(log_path)

    jobs = [
        job
        for job in build_jobs(models, conditions, tasks, args.reps, variants)
        if job["run_id"] not in done
    ]
    if args.max_jobs:
        jobs = jobs[: args.max_jobs]
    print(f"jobs={len(jobs)} already_done={len(done)} log={log_path}")

    with log_path.open("a", encoding="utf-8") as log:
        for index, job in enumerate(jobs, start=1):
            prompt = prompt_path(job["condition"], job["task_id"], job["variant"]).read_text(encoding="utf-8")
            slug = CONFIG["models"][job["model"]]["openrouter_slug"]
            try:
                completion, meta, api_s = call_openrouter(slug, prompt, api_key)
                comp_path = completion_dir / f"{job['run_id']}.txt"
                comp_path.write_text(completion, encoding="utf-8")
                verdict = judge(job["task_id"], completion, job["condition"])
                rec = {
                    "run_id": job["run_id"],
                    "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "model": job["model"],
                    "model_label": CONFIG["models"][job["model"]]["label"],
                    "model_slug": slug,
                    "condition": job["condition"],
                    "task_id": job["task_id"],
                    "variant": job["variant"],
                    "repetition": job["rep"],
                    "prompt": prompt,
                    "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                    "completion": completion,
                    "completion_path": str(comp_path.relative_to(ROOT)),
                    "api_response_meta": meta,
                    "judge": verdict,
                    "latency_s": {"api": round(api_s, 2)},
                }
                print(f"[{index}/{len(jobs)}] {job['run_id']} -> {verdict['bucket']} ({api_s:.1f}s)")
            except Exception as exc:  # noqa: BLE001
                rec = {
                    "run_id": job["run_id"],
                    "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "model": job["model"],
                    "condition": job["condition"],
                    "task_id": job["task_id"],
                    "variant": job["variant"],
                    "repetition": job["rep"],
                    "transport_error": repr(exc),
                    "judge": {"bucket": "transport_failure", "strict_correct": False, "defensible_correct": False},
                }
                print(f"[FAIL] {job['run_id']} -> {exc}")
            log.write(json.dumps(rec, ensure_ascii=False) + "\n")
            log.flush()


if __name__ == "__main__":
    main()
