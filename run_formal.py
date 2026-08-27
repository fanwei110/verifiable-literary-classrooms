"""Formal generation runner.

Grid:
  18 tasks x 4 conditions x 3 models x 10 repetitions = 2160 generations

Condition repetition structure:
  C1/C3: variants A and B, 5 repetitions each.
  C2/C4: canonical prompt, 10 repetitions.

The script is resume-safe. Successful records in formal.jsonl are skipped on
rerun. API failures are written to formal_failures.jsonl and retried on the
next run because they are not counted as completed records.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from runner import CONFIG, call_openrouter, prompt_path, read_api_key  # noqa: E402
sys.path.insert(0, str(ROOT / "harness"))
from judge import judge  # noqa: E402

MODELS = ("M1", "M2", "M3")
CONDITIONS = ("C1", "C2", "C3", "C4")
OUTDIR = ROOT / "runs" / "raw" / "formal"
LOG_PATH = OUTDIR / "formal.jsonl"
FAIL_PATH = OUTDIR / "formal_failures.jsonl"
STATUS_PATH = OUTDIR / "status.txt"
COMPLETIONS_DIR = OUTDIR / "completions"
LOCK_PATH = OUTDIR / "formal.lock"


def load_task_ids() -> list[str]:
    return sorted(path.stem for path in (ROOT / "tasks").glob("TGU*_T*.yaml"))


def prompt_count(folder: str) -> int:
    return len(list((ROOT / "prompts" / folder).glob("*.md")))


def preflight() -> None:
    errors: list[str] = []
    if not CONFIG.get("locked"):
        errors.append("config/models.yaml locked is not true")
    validation_report = ROOT / "harness" / "validation_report.md"
    if not validation_report.exists() or "40/40" not in validation_report.read_text(encoding="utf-8"):
        errors.append("harness/validation_report.md does not show 40/40")
    task_ids = load_task_ids()
    if len(task_ids) != 18:
        errors.append(f"expected 18 tasks, found {len(task_ids)}")
    counts = {
        "C1_simulated": prompt_count("C1_simulated"),
        "C2_structured": prompt_count("C2_structured"),
        "C3_grounded": prompt_count("C3_grounded"),
        "C4_tgu": prompt_count("C4_tgu"),
    }
    expected = {"C1_simulated": 36, "C2_structured": 18, "C3_grounded": 36, "C4_tgu": 18}
    if counts != expected:
        errors.append(f"prompt counts mismatch: {counts} expected {expected}")
    for model in MODELS:
        if model not in CONFIG["models"]:
            errors.append(f"missing model config: {model}")
    if errors:
        raise SystemExit("Formal preflight failed:\n- " + "\n- ".join(errors))


def build_jobs() -> list[dict]:
    jobs = []
    for task_id in load_task_ids():
        for condition in CONDITIONS:
            if condition in {"C1", "C3"}:
                slots = [("A", rep) for rep in range(1, 6)] + [("B", rep) for rep in range(6, 11)]
            else:
                slots = [("canonical", rep) for rep in range(1, 11)]
            for variant, rep in slots:
                for model in MODELS:
                    jobs.append(
                        {
                            "run_id": f"{model}_{condition}_{task_id}_{variant}_r{rep:02d}",
                            "model": model,
                            "condition": condition,
                            "task_id": task_id,
                            "variant": variant,
                            "repetition": rep,
                        }
                    )
    if len(jobs) != 2160:
        raise SystemExit(f"internal grid error: expected 2160 jobs, got {len(jobs)}")
    ids = [job["run_id"] for job in jobs]
    if len(ids) != len(set(ids)):
        raise SystemExit("internal grid error: duplicate run_id")
    return jobs


def done_ids() -> set[str]:
    ids = set()
    if not LOG_PATH.exists():
        return ids
    for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            ids.add(json.loads(line)["run_id"])
        except (json.JSONDecodeError, KeyError):
            continue
    return ids


def existing_bucket_counts() -> Counter:
    counts: Counter = Counter()
    if not LOG_PATH.exists():
        return counts
    for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            counts[row.get("judge", {}).get("bucket", "missing_bucket")] += 1
        except json.JSONDecodeError:
            counts["bad_json_line"] += 1
    return counts


def run_api_job(job: dict, api_key: str) -> tuple[str, dict, str, dict | None, float | None, str | None]:
    prompt = prompt_path(job["condition"], job["task_id"], job["variant"]).read_text(encoding="utf-8")
    slug = CONFIG["models"][job["model"]]["openrouter_slug"]
    try:
        completion, meta, api_s = call_openrouter(slug, prompt, api_key)
        return prompt, job, completion, meta, api_s, None
    except Exception as exc:  # noqa: BLE001
        return prompt, job, "", None, None, repr(exc)


def write_status(start_time: float, completed_this_run: int, failed_this_run: int, total_done: int, total_jobs: int, buckets: Counter) -> None:
    elapsed = max(time.time() - start_time, 1)
    rate = completed_this_run / elapsed * 3600
    remaining = max(total_jobs - total_done, 0)
    eta_hours = remaining / rate if rate > 0 else 0
    line = (
        f"{datetime.now().isoformat(timespec='seconds')}\n"
        f"completed_total={total_done}/{total_jobs}\n"
        f"completed_this_run={completed_this_run}\n"
        f"api_failures_this_run={failed_this_run}\n"
        f"rate_per_hour={rate:.1f}\n"
        f"eta_hours={eta_hours:.2f}\n"
        f"buckets={dict(buckets)}\n"
    )
    STATUS_PATH.write_text(line, encoding="utf-8")
    print(line.strip())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--key-file", required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--max-jobs", type=int, default=0, help="debug only; limits missing jobs")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    preflight()
    jobs = build_jobs()
    done = done_ids()
    missing = [job for job in jobs if job["run_id"] not in done]
    if args.max_jobs:
        missing = missing[: args.max_jobs]

    print(f"formal_grid=2160 already_done={len(done)} to_run={len(missing)} workers={args.workers}")
    if args.dry_run:
        by_model = Counter(job["model"] for job in jobs)
        by_condition = Counter(job["condition"] for job in jobs)
        by_task = Counter(job["task_id"] for job in jobs)
        print(f"by_model={dict(by_model)}")
        print(f"by_condition={dict(by_condition)}")
        print(f"task_count={len(by_task)} per_task_unique={sorted(set(by_task.values()))}")
        return
    if not missing:
        print("nothing to run")
        return

    OUTDIR.mkdir(parents=True, exist_ok=True)
    try:
        lock_fd = os.open(str(LOCK_PATH), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(lock_fd, str(os.getpid()).encode("utf-8"))
        os.close(lock_fd)
    except FileExistsError:
        raise SystemExit(f"formal runner lock exists: {LOCK_PATH}; another formal run may still be active")

    api_key = read_api_key(args.key_file)
    COMPLETIONS_DIR.mkdir(parents=True, exist_ok=True)

    try:
        start = time.time()
        completed_this_run = 0
        failed_this_run = 0
        buckets = existing_bucket_counts()

        with LOG_PATH.open("a", encoding="utf-8") as log, FAIL_PATH.open("a", encoding="utf-8") as fail_log:
            with ThreadPoolExecutor(max_workers=args.workers) as executor:
                futures = [executor.submit(run_api_job, job, api_key) for job in missing]
                for future in as_completed(futures):
                    prompt, job, completion, meta, api_s, error = future.result()
                    if error is not None:
                        failed_this_run += 1
                        fail_log.write(
                            json.dumps(
                                {
                                    "run_id": job["run_id"],
                                    "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                                    "model": job["model"],
                                    "condition": job["condition"],
                                    "task_id": job["task_id"],
                                    "variant": job["variant"],
                                    "repetition": job["repetition"],
                                    "transport_error": error,
                                },
                                ensure_ascii=False,
                            )
                            + "\n"
                        )
                        fail_log.flush()
                    else:
                        completion_path = COMPLETIONS_DIR / f"{job['run_id']}.txt"
                        completion_path.write_text(completion, encoding="utf-8")
                        verdict = judge(job["task_id"], completion, job["condition"])
                        record = {
                            "run_id": job["run_id"],
                            "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                            "model": job["model"],
                            "model_label": CONFIG["models"][job["model"]]["label"],
                            "model_slug": CONFIG["models"][job["model"]]["openrouter_slug"],
                            "condition": job["condition"],
                            "task_id": job["task_id"],
                            "variant": job["variant"],
                            "repetition": job["repetition"],
                            "prompt": prompt,
                            "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                            "completion": completion,
                            "completion_path": str(completion_path.relative_to(ROOT)),
                            "api_response_meta": meta,
                            "judge": verdict,
                            "latency_s": {"api": round(float(api_s), 2)},
                        }
                        log.write(json.dumps(record, ensure_ascii=False) + "\n")
                        log.flush()
                        completed_this_run += 1
                        buckets[verdict.get("bucket", "missing_bucket")] += 1

                    total_done = len(done) + completed_this_run
                    if (completed_this_run + failed_this_run) % 25 == 0 or total_done == len(jobs):
                        write_status(start, completed_this_run, failed_this_run, total_done, len(jobs), buckets)

        write_status(start, completed_this_run, failed_this_run, len(done) + completed_this_run, len(jobs), buckets)
    finally:
        try:
            LOCK_PATH.unlink()
        except FileNotFoundError:
            pass


if __name__ == "__main__":
    main()
