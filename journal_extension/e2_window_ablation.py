"""E2 窗口大小消融（H3b）：接地是否只是 ±900 窗口的产物？
以目标引文为中心取 ±300 / ±900(控制) / ±2700 字窗，跑 C3 式接地，比较 strict。
若三档相近 → 接地对窗口大小稳健（不靠某一窗）。M2，grounded confirmatory 任务。
用法：python journal_extension/e2_window_ablation.py --reps 3
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "harness"))
sys.path.insert(0, str(ROOT / "journal_extension"))
import judge as judge_mod  # noqa: E402
import apply_corrections  # noqa: E402
apply_corrections.patch(judge_mod)
import yaml  # noqa: E402
from api_client import Client  # noqa: E402

CORPUS = json.loads((ROOT / "corpus" / "processed" / "corpus_index.json").read_text(encoding="utf-8"))
PROMPT_DIR = ROOT / "prompts"
DEV = {"TGU2", "TGU4"}


def window(work_id, quote, half):
    text = CORPUS[work_id]["clean_text"]
    i = text.find(quote)
    if i < 0:  # 规范化后再找一次（宽松）
        nq = re.sub(r"\s+", " ", quote)
        i = re.sub(r"\s+", " ", text).find(nq)
    if i < 0:
        return None
    s = max(0, i - half)
    return text[s:i + len(quote) + half]


def build_prompt(task_id, work_id, quote, half):
    c3 = (PROMPT_DIR / "C3_grounded" / f"{task_id}_A.md").read_text(encoding="utf-8")
    head = c3.split("Frozen source excerpt(s):")[0].rstrip()
    tail = c3[c3.index("Return only one valid JSON object"):] if "Return only one valid JSON object" in c3 else ""
    win = window(work_id, quote, half)
    if win is None:
        return None
    return f"{head}\n\nFrozen source excerpt(s):\n{win}\n\n{tail}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--model", default="M2")
    ap.add_argument("--tag", default="e2_window")
    a = ap.parse_args()
    tasks = [p.stem for p in sorted((ROOT / "tasks").glob("TGU*_T*.yaml"))
             if p.stem.split("_")[0] not in DEV]
    outdir = ROOT / "runs" / "raw" / f"ext_{a.tag}"
    outdir.mkdir(parents=True, exist_ok=True)
    log = outdir / f"{a.tag}.jsonl"
    client = Client()
    agg = defaultdict(lambda: [0, 0])
    with log.open("w", encoding="utf-8") as f:
        for tid in tasks:
            t = yaml.safe_load((ROOT / "tasks" / f"{tid}.yaml").read_text(encoding="utf-8"))
            q = t["expected_evidence"][0]["quote"]
            for half in (300, 900, 2700):
                prompt = build_prompt(tid, t["work_id"], q, half)
                if prompt is None:
                    continue
                for rep in range(1, a.reps + 1):
                    text, meta, lat = client.chat(a.model, [{"role": "user", "content": prompt}],
                                                  tag=f"{a.tag}:{half}")
                    v = judge_mod.judge(tid, text, condition="C3")
                    s = bool(v.get("strict_correct"))
                    agg[half][0] += 1; agg[half][1] += s
                    f.write(json.dumps({"task_id": tid, "half": half, "rep": rep,
                                        "strict": s, "error_class": v.get("error_class_candidate")},
                                       ensure_ascii=False) + "\n")
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    print(f"E2 窗口消融（{a.model}, grounded confirmatory, spent ${client.spent():.2f}）：")
    for half in (300, 900, 2700):
        n, s = agg[half]
        if n:
            print(f"  ±{half} 字窗: {s}/{n} strict = {100*s/n:.0f}%")
    print("→ 三档相近即接地对窗口大小稳健（非 ±900 的产物）。")


if __name__ == "__main__":
    main()
