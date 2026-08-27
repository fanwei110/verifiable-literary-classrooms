"""中文验证-修复闭环（cross-language replication）。judge_zh + 中文信息封顶反馈。
臂：resample（盲重采样，best-of-k 派生）/ F3（类别+字段级定向反馈，绝不含正确值）。
用法：python journal_extension/repair_loop_zh.py --tag zh_e1 --models M2,M4 --conditions C1,C3 --reps 5 --k 3
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "journal_extension"))
sys.path.insert(0, str(ROOT / "harness_zh"))
from api_client import Client, EXT_MODELS  # noqa: E402
from judge_zh import judge_zh, load_task  # noqa: E402
from normalize_zh import normalize_zh  # noqa: E402
from spike_zh import build_prompt  # 复用带篇约束的中文 prompt  # noqa: E402

TASK_DIR = ROOT / "tasks_zh"

FB1 = ("你的上一个回答未通过对冻结原文语料的自动校验。请给出修正后的答案，"
       "仍为一个合法 JSON 对象，schema 不变，不要输出 JSON 以外的文字。")
ERR_ZH = {
    "fabricated_quotation": "所引文字在冻结语料中找不到",
    "misattribution": "作品或说话人归属与语料不符",
    "version_drift": "引文与语料版本用字略有出入",
    "context_displacement": "引文找到了，但出处/说话人/取材范围有误",
    "too_short_or_format": "引文过短或格式不符，不足以构成有效引用",
    "format_failure": "输出不是一个合法且字段完整的 JSON 对象",
}
FIELD_ZH = {
    "quote_found": "所引文字未在语料中找到",
    "claimed_work_ok": "作品归属校验未过",
    "locator_ok": "出处（篇名）校验未过",
    "speaker_ok": "说话人归属校验未过",
    "grounded_ok": "所引文字不在所给原文片段内",
}


def build_feedback_zh(verdict: dict) -> str:
    err = verdict.get("error_class_candidate") or "unknown"
    lines = [FB1, "", f"错误类别：{err}（{ERR_ZH.get(err, '校验未通过')}）。", "字段级校验旗标："]
    flags = []
    for md in (verdict.get("match_details") or []):
        for k, zh in FIELD_ZH.items():
            if md.get(k) is False:
                flags.append(zh)
    lines += (sorted(set(flags)) or ["（无更细字段信息）"])
    lines.append("请对照原文只改错的字段，不要改对的部分。")
    return "\n".join(lines)


def assert_no_leak_zh(feedback: str, task: dict) -> None:
    fb = normalize_zh(feedback)
    for ev in task["expected_evidence"]:
        q = normalize_zh(ev.get("quote", ""))
        if len(q) >= 5 and q[:8] in fb:
            raise RuntimeError(f"ZH FEEDBACK LEAK: {q[:8]} in feedback for {task['task_id']}")
        loc = normalize_zh(ev.get("locator", ""))
        if loc and loc in fb:
            raise RuntimeError(f"ZH FEEDBACK LEAK locator {loc}")


def run_group(client, task, cond, model, rep, arms, k_max, tag):
    prompt = build_prompt(task, cond)

    def call(msgs, ridx, arm):
        text, meta, lat = client.chat(model, msgs, tag=f"{tag}:{arm}")
        v = judge_zh(task["task_id"], text, condition=cond)
        return {"round": ridx, "completion": text, "judge": v, "usage": meta.get("usage")}

    r0 = call([{"role": "user", "content": prompt}], 0, "k0")
    k0 = bool(r0["judge"].get("strict_correct"))
    gid = f"{model}_{cond}_{task['task_id']}_r{rep:02d}"
    recs = []
    for arm in arms:
        rounds = [r0]
        if not k0:
            if arm == "resample":
                for k in range(1, k_max + 1):
                    rounds.append(call([{"role": "user", "content": prompt}], k, arm))
            else:  # F3
                msgs = [{"role": "user", "content": prompt}]
                for k in range(1, k_max + 1):
                    fb = build_feedback_zh(rounds[-1]["judge"])
                    assert_no_leak_zh(fb, task)
                    msgs = msgs + [{"role": "assistant", "content": rounds[-1]["completion"]},
                                   {"role": "user", "content": fb}]
                    rk = call(msgs, k, arm)
                    rounds.append(rk)
                    if rk["judge"].get("strict_correct"):
                        break
        recs.append({"group_id": gid, "task_id": task["task_id"], "work_id": task["work_id"],
                     "condition": cond, "model": model, "rep": rep, "arm": arm,
                     "k0_strict": k0, "final_strict": bool(rounds[-1]["judge"].get("strict_correct")),
                     "rounds": rounds,
                     "ts": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")})
    return recs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="zh_e1")
    ap.add_argument("--models", default="M2")
    ap.add_argument("--conditions", default="C1,C3")
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--arms", default="resample,F3")
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--workers", type=int, default=5)
    a = ap.parse_args()
    tasks = [load_task(p.stem) for p in sorted(TASK_DIR.glob("ZTGU*_T*.json"))]
    arms = a.arms.split(",")
    outdir = ROOT / "runs" / "raw" / f"ext_{a.tag}"
    outdir.mkdir(parents=True, exist_ok=True)
    log = outdir / f"{a.tag}.jsonl"
    done = set()
    if log.exists():
        done = {json.loads(l)["group_id"] for l in log.read_text(encoding="utf-8").splitlines() if l.strip()}
    jobs = [(t, c, m, rep) for t in tasks for c in a.conditions.split(",")
            for m in a.models.split(",") for rep in range(1, a.reps + 1)
            if f"{m}_{c}_{t['task_id']}_r{rep:02d}" not in done]
    print(f"zh repair jobs: {len(jobs)} (skip {len(done)})")
    client = Client()
    lock = threading.Lock()

    def worker(job):
        t, c, m, rep = job
        recs = run_group(client, t, c, m, rep, arms, a.k, a.tag)
        with lock:
            with log.open("a", encoding="utf-8") as f:
                for r in recs:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
        return 1

    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = [ex.submit(worker, j) for j in jobs]
        for i, fut in enumerate(as_completed(futs), 1):
            fut.result()
            if i % 20 == 0 or i == len(jobs):
                print(f"[{i}/{len(jobs)}] ${client.spent():.2f}")
    print(f"done ${client.spent():.2f}")


if __name__ == "__main__":
    main()
