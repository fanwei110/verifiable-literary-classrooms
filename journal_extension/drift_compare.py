"""漂移对比：ext_drift 新跑 k=0 vs 冻结日志同 cell 率（M2/M3），M4 为新模型摸底。"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FROZEN = ROOT / "runs" / "raw" / "formal" / "formal.jsonl"
DRIFT = ROOT / "runs" / "raw" / "ext_drift" / "drift.jsonl"
OUT = Path(__file__).resolve().parent / "analysis_ext" / "e0" / "drift_report.md"


def main() -> None:
    frozen = defaultdict(lambda: [0, 0])  # (model, cond, task) -> [n, strict]
    for line in FROZEN.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        k = (r["model"], r["condition"], r["task_id"])
        frozen[k][0] += 1
        frozen[k][1] += 1 if r["judge"].get("strict_correct") else 0

    new = defaultdict(lambda: [0, 0])
    for line in DRIFT.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        k = (r["model"], r["condition"], r["task_id"])
        new[k][0] += 1
        new[k][1] += 1 if r["k0_strict"] else 0

    lines = ["# 漂移切片对比（新跑 k=0 vs 冻结率）", "",
             "| model | cond | 新跑 strict | 冻结同 cell strict | 差 |",
             "|---|---|---|---|---|"]
    agg = defaultdict(lambda: [0, 0, 0, 0])  # (model,cond) -> new_n, new_s, fro_n, fro_s
    for (m, c, t), (n, s) in sorted(new.items()):
        fn, fs = frozen.get((m, c, t), (0, 0))
        a = agg[(m, c)]
        a[0] += n; a[1] += s; a[2] += fn; a[3] += fs
    for (m, c), (n, s, fn, fs) in sorted(agg.items()):
        newr = s / n if n else 0
        fror = fs / fn if fn else float("nan")
        diff = f"{100*(newr - fror):+.0f}pp" if fn else "（新模型，无冻结基线）"
        fro_txt = f"{fs}/{fn} = {100*fror:.0f}%" if fn else "—"
        lines.append(f"| {m} | {c} | {s}/{n} = {100*newr:.0f}% | {fro_txt} | {diff} |")
    lines += ["", "判读：|差| ≤ 15pp（小样本容差）视为无严重漂移；超出则记 DEVIATION 并复核。",
              "M4 (deepseek-reasoner) 无冻结基线，此处为新模型摸底快照。"]
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
