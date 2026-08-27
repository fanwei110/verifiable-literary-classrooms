"""验证-修复闭环运行器（fresh 模式：新跑 k=0 → 判分 → 失败者按臂修复 ≤k 轮）。

臂（arm）：
  resample —— 同一 prompt 独立重抽 k 次（无反馈；A2 best-of-k 由分析阶段从中派生）
  F1 —— 仅告知"未通过验证"（二值反馈）
  F2 —— F1 + 错误类别名
  F3 —— F2 + 字段级失败旗标（哪个字段错了；**绝不含正确值**）
  F4 —— oracle：给出正确值（能力上界诊断；物理隔离，分析不入主结论）

信息封顶铁律：F1–F3 的反馈文本运行时经 assert_no_leak() 校验，
若包含期望引文/定位/说话人的任何片段立即抛异常终止。

输出：runs/raw/ext_{tag}/{tag}.jsonl，每 job 一行含全部轮次；按 run_id 断点续跑。
用法示例（smoke）：
  python journal_extension/repair_loop.py --tag smoke --tasks dev --conditions C1,C3 \
      --models M2,M4 --reps 3 --arms resample,F1,F2,F3 --k 2 --workers 3
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

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))          # for harness.judge
sys.path.insert(0, str(ROOT / "harness"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import judge as judge_mod  # harness/judge.py
from api_client import Client, EXT_MODELS  # noqa: E402

TASK_DIR = ROOT / "tasks"
PROMPT_DIR = ROOT / "prompts"
DEV_TGUS = {"TGU2", "TGU4"}
MAX_HISTORY_CHARS = 30_000

FEEDBACK_F1 = (
    "Your previous answer did not pass automated verification against the frozen "
    "source corpus. Please provide a corrected answer, as one valid JSON object "
    "with the same schema. Do not include text outside the JSON object."
)

ERROR_EXPLAIN = {  # 类别名 + 一句中性解释（不含任何正确值）
    "fabricated_quotation": "at least one quoted string could not be found in the frozen corpus",
    "misattribution": "the claimed author or work does not match the corpus for at least one quote",
    "version_drift": "a quote nearly matches the corpus but the wording differs from the frozen edition",
    "context_displacement": "a quote was found but its locator, speaker, or source-window use is wrong",
    "format_failure": "the output was not one valid JSON object with the required fields",
}

FIELD_HINTS = {  # 字段级旗标措辞（仍不含正确值）
    "quote_found": "the quoted string itself was not found in the corpus",
    "claimed_author_ok": "the author attribution failed verification",
    "claimed_work_ok": "the work attribution failed verification",
    "locator_ok": "the locator (act/scene/chapter/book) failed verification",
    "speaker_ok": "the speaker/narrator attribution failed verification",
    "grounded_ok": "the quote is not taken from the supplied source excerpt",
}


def load_task(task_id: str) -> dict:
    return yaml.safe_load((TASK_DIR / f"{task_id}.yaml").read_text(encoding="utf-8"))


def prompt_path(condition: str, task_id: str, variant: str) -> Path:
    sub = {"C1": "C1_simulated", "C2": "C2_structured",
           "C3": "C3_grounded", "C4": "C4_tgu"}[condition]
    name = f"{task_id}_{variant}.md" if condition in ("C1", "C3") else f"{task_id}.md"
    return PROMPT_DIR / sub / name


def build_feedback(tier: str, verdict: dict, task: dict) -> str:
    if tier == "F1":
        return FEEDBACK_F1
    err = verdict.get("error_class_candidate") or "unknown"
    lines = [FEEDBACK_F1, "",
             f"Error category: {err} ({ERROR_EXPLAIN.get(err, 'verification failed')})."]
    if tier == "F2":
        return "\n".join(lines)
    if tier == "F3":
        flags = []
        for i, md in enumerate(verdict.get("match_details") or []):
            failed = [FIELD_HINTS[k] for k in FIELD_HINTS
                      if md.get(k) is False]
            if failed:
                flags.append(f"Evidence record {i + 1}: " + "; ".join(failed) + ".")
        if not flags and verdict.get("parse_error"):
            flags.append(f"Parse problem: {verdict['parse_error']}.")
        lines += ["Field-level verification flags:"] + (flags or ["(no per-field detail available)"])
        lines.append("Re-check the failing fields against the source text and correct only what is wrong.")
        return "\n".join(lines)
    if tier == "F4":  # oracle —— 隔离臂
        lines.append("Reference (oracle) evidence for this task:")
        for ev in task.get("expected_evidence", []):
            lines.append(
                f'- quote: "{ev.get("quote")}" | locator: {ev.get("locator")} | '
                f"speaker_or_narrator: {ev.get('speaker_or_narrator')}"
            )
        return "\n".join(lines)
    raise ValueError(tier)


def assert_no_leak(feedback: str, task: dict) -> None:
    """信息封顶：F1–F3 反馈不得包含任何正确值片段。"""
    fb = " ".join(feedback.lower().split())
    for ev in task.get("expected_evidence", []):
        probes = []
        q = (ev.get("quote") or "").lower()
        if len(q) >= 15:
            probes.append(" ".join(q[:30].split()))
        loc = (ev.get("locator") or "").lower().strip()
        if loc:
            probes.append(loc)
        spk = (ev.get("speaker_or_narrator") or "").lower().strip()
        if spk and spk not in ("narrator",):  # 泛称不算泄漏
            probes.append(spk)
        for p in probes:
            if p and p in fb:
                raise RuntimeError(f"FEEDBACK LEAK DETECTED: {p!r} in feedback for {task['task_id']}")


def truncate_history(messages: list[dict]) -> tuple[list[dict], bool]:
    total = sum(len(m["content"]) for m in messages)
    if total <= MAX_HISTORY_CHARS or len(messages) <= 3:
        return messages, False
    # 保留原始 prompt（首条）+ 最近一轮 assistant + 最新 feedback
    kept = [messages[0]] + messages[-2:]
    return kept, True


def run_group(client: Client, group: dict, arms: list[str], k_max: int, tag: str) -> list[dict]:
    """受试内设计：每组（task×cond×model×rep）只生成一次 k=0；
    若失败，同一 k=0 完成文本分支到各臂分别修复——臂间配对可比。"""
    task = load_task(group["task_id"])
    prompt = prompt_path(group["condition"], group["task_id"], group["variant"]).read_text(encoding="utf-8")

    def one_call(messages: list[dict], round_idx: int, arm: str) -> dict:
        msgs, truncated = truncate_history(messages)
        text, meta, latency = client.chat(group["model"], msgs, tag=f"{tag}:{arm}:r{round_idx}")
        verdict = judge_mod.judge(group["task_id"], text, condition=group["condition"])
        return {"round": round_idx, "completion": text, "judge": verdict,
                "usage": meta.get("usage"), "latency_s": round(latency, 2),
                "history_truncated": truncated}

    r0 = one_call([{"role": "user", "content": prompt}], 0, "k0")
    k0_strict = bool(r0["judge"].get("strict_correct"))

    def base_record(arm: str, rounds: list[dict]) -> dict:
        return {
            "run_id": f"{group['group_id']}_{arm}",
            "group_id": group["group_id"],
            "timestamp_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "model": group["model"],
            "model_slug": EXT_MODELS[group["model"]]["slug"],
            "provider": EXT_MODELS[group["model"]]["provider"],
            "condition": group["condition"],
            "task_id": group["task_id"],
            "variant": group["variant"],
            "repetition": group["rep"],
            "arm": arm,
            "k_max": k_max,
            "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
            "rounds": rounds,
            "k0_strict": k0_strict,
            "final_strict": bool(rounds[-1]["judge"].get("strict_correct")),
        }

    records = []
    if k0_strict:
        # 成功组：每臂记同一 k=0（零额外调用，臂级端到端率可直接算）
        return [base_record(arm, [r0]) for arm in arms]

    for arm in arms:
        rounds = [r0]
        if arm == "resample":
            for k in range(1, k_max + 1):
                rounds.append(one_call([{"role": "user", "content": prompt}], k, arm))
                # 不早停：k 个独立样本全要（best-of-k 无偏派生）
        else:
            tier = arm  # F1/F2/F3/F4
            messages = [{"role": "user", "content": prompt}]
            for k in range(1, k_max + 1):
                fb = build_feedback(tier, rounds[-1]["judge"], task)
                if tier != "F4":
                    assert_no_leak(fb, task)
                messages = messages + [
                    {"role": "assistant", "content": rounds[-1]["completion"]},
                    {"role": "user", "content": fb},
                ]
                rk = one_call(messages, k, arm)
                rk["feedback_sent"] = fb
                rounds.append(rk)
                if rk["judge"].get("strict_correct"):
                    break
        records.append(base_record(arm, rounds))
    return records


def build_groups(tasks, conditions, models, reps) -> list[dict]:
    groups = []
    for t in tasks:
        for c in conditions:
            variant = "A" if c in ("C1", "C3") else "canonical"
            for m in models:
                for rep in range(1, reps + 1):
                    groups.append({
                        "task_id": t, "condition": c, "variant": variant,
                        "model": m, "rep": rep,
                        "group_id": f"{m}_{c}_{t}_{variant}_r{rep:02d}",
                    })
    return groups


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--tasks", required=True, help='"dev" 或 逗号分隔 task_id')
    ap.add_argument("--conditions", default="C1,C3")
    ap.add_argument("--models", default="M2,M4")
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--arms", default="resample,F1,F2,F3")
    ap.add_argument("--k", type=int, default=2)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--raw-judge", action="store_true",
                    help="停用已核验的 gold-locator 修正（默认施加，扩展版应始终用修正后 gold）")
    args = ap.parse_args()

    if not args.raw_judge:
        import apply_corrections
        apply_corrections.patch(judge_mod)          # 修正 judge_mod.judge 的评分与反馈
        globals()["load_task"] = judge_mod.load_task  # 本模块 run_group/F4 也用修正后 gold
        print(f"[corrections] applied {apply_corrections.n_corrections()} verified gold-locator corrections")

    if args.tasks == "dev":
        tasks = sorted(p.stem for p in TASK_DIR.glob("TGU*_T*.yaml")
                       if p.stem.split("_")[0] in DEV_TGUS)
    else:
        tasks = args.tasks.split(",")
    arms = args.arms.split(",")
    for a in arms:
        assert a in ("resample", "F1", "F2", "F3", "F4"), a
    if "F4" in arms:
        print("WARNING: F4 oracle arm requested — outputs quarantined from main analysis.")

    outdir = ROOT / "runs" / "raw" / f"ext_{args.tag}"
    outdir.mkdir(parents=True, exist_ok=True)
    log_path = outdir / f"{args.tag}.jsonl"
    done_groups = set()
    if log_path.exists():
        for line in log_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                done_groups.add(json.loads(line)["group_id"])

    groups = [g for g in build_groups(tasks, args.conditions.split(","),
                                      args.models.split(","), args.reps)
              if g["group_id"] not in done_groups]
    print(f"groups to run: {len(groups)} × arms {arms} (skipped {len(done_groups)} done)")
    client = Client()
    lock = threading.Lock()
    failures = []

    def worker(group):
        try:
            recs = run_group(client, group, arms, args.k, args.tag)
            with lock:
                with log_path.open("a", encoding="utf-8") as f:
                    for rec in recs:
                        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            return group["group_id"], True
        except Exception as e:
            with lock:
                failures.append({"group_id": group["group_id"], "error": str(e)})
            return group["group_id"], None

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(worker, g) for g in groups]
        for i, fut in enumerate(as_completed(futs), 1):
            gid, ok = fut.result()
            if i % 10 == 0 or i == len(groups):
                print(f"[{i}/{len(groups)}] spent=${client.spent():.2f}")

    if failures:
        (outdir / "failures.jsonl").write_text(
            "\n".join(json.dumps(x) for x in failures) + "\n", encoding="utf-8")
        print(f"{len(failures)} job failures logged")
    print(f"done. ledger total = ${client.spent():.2f}")


if __name__ == "__main__":
    main()
