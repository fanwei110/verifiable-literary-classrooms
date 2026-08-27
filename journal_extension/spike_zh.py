"""中文赛道 spike：《論語·學而》单 TGU 端到端，探明难度与裁判行为。
C1(无窗) / C3(有窗) × M2 × reps，用 judge_zh 判分。零外部依赖（语料已冻结）。
用法：python journal_extension/spike_zh.py --models M2 --reps 5 --conditions C1,C3
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "journal_extension"))
sys.path.insert(0, str(ROOT / "harness_zh"))
from api_client import Client  # noqa: E402
from judge_zh import judge_zh, load_task, load_corpus  # noqa: E402

TASK_DIR = ROOT / "tasks_zh"


def book_of(work_id: str) -> str:
    """从冻结语料取该作品覆盖的篇名（约束任务只在覆盖范围内取引，避免跨篇假捏造）。"""
    books = load_corpus().get(work_id, {}).get("books", [])
    return "、".join(b["book_title"] for b in books) if books else ""

SCHEMA = ('{"answer": "面向课堂的讲解", "evidence": [{"quote": "逐字原文", "work": "作品名", '
          '"speaker_or_narrator": "说话人", "locator": "篇名", "use_in_answer": "一句说明"}], '
          '"limits": "任何不确定或版本说明"}')


def build_prompt(task: dict, condition: str) -> str:
    n = task.get("required_evidence_count", 1)
    cnt = "一句" if n == 1 else f"{n}句"
    book = book_of(task["work_id"])
    scope = f"《{task['work_title']}·{book}》篇" if book else f"《{task['work_title']}》"
    head = (f"你是一位古典文学课教师。课堂上，请就“{task['theme']}”这一主题，"
            f"从{scope}中给出确切的原文引用（{cnt}），并注明出处（篇名）与说话人。"
            f"只可引用{scope}范围内的原文，不要引用该篇之外的内容。")
    win = ""
    if condition in ("C3", "C4"):
        wins = "\n".join(ev["source_window"] for ev in task["expected_evidence"])
        win = f"\n\n冻结原文片段（请只从其中引用）：\n{wins}"
    tail = (f"\n\n仅返回一个合法 JSON 对象，schema：\n{SCHEMA}\n"
            f"evidence 数组须恰好含 {n} 条。不要使用 Markdown 代码块，不要输出 JSON 以外的任何文字。")
    return head + win + tail


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="M2")
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--conditions", default="C1,C3")
    ap.add_argument("--tag", default="zh_spike")
    args = ap.parse_args()

    tasks = sorted(p.stem for p in TASK_DIR.glob("ZTGU*_T*.json"))
    outdir = ROOT / "runs" / "raw" / f"ext_{args.tag}"
    outdir.mkdir(parents=True, exist_ok=True)
    log = outdir / f"{args.tag}.jsonl"
    client = Client()
    results = []
    with log.open("w", encoding="utf-8") as f:
        for tid in tasks:
            task = load_task(tid)
            for cond in args.conditions.split(","):
                prompt = build_prompt(task, cond)
                for m in args.models.split(","):
                    for rep in range(1, args.reps + 1):
                        text, meta, lat = client.chat(m, [{"role": "user", "content": prompt}],
                                                      tag=f"{args.tag}:{m}:{cond}")
                        v = judge_zh(tid, text, condition=cond)
                        rec = {"task_id": tid, "condition": cond, "model": m, "rep": rep,
                               "strict": bool(v.get("strict_correct")),
                               "error_class": v.get("error_class_candidate"),
                               "completion": text, "judge": v,
                               "ts": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
                        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                        results.append(rec)
    # 汇总
    from collections import defaultdict
    agg = defaultdict(lambda: [0, 0])
    for r in results:
        agg[(r["model"], r["condition"])][0] += 1
        agg[(r["model"], r["condition"])][1] += int(r["strict"])
    print(f"zh spike: {len(results)} generations, spent ${client.spent():.2f}")
    for (m, c), (n, s) in sorted(agg.items()):
        print(f"  {m} {c}: {s}/{n} strict = {100*s/n:.0f}%")
    from collections import Counter
    ec = Counter(r["error_class"] for r in results if not r["strict"])
    print("  错误类别（失败）:", dict(ec))
    print("  日志 ->", log)


if __name__ == "__main__":
    main()
