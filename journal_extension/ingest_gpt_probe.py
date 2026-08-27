"""回收 GPT 摸底输出并判分（零 API 调用；探索层，标注 provenance deviation）。"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))
import judge as judge_mod  # noqa: E402

IN = Path(__file__).resolve().parent / "gpt_probe" / "gpt_probe_output.jsonl"
META = Path(__file__).resolve().parent / "gpt_probe" / "gpt_probe_input.jsonl"
OUTDIR = ROOT / "runs" / "raw" / "ext_gpt_probe"


def main() -> None:
    if not IN.exists():
        raise SystemExit(f"missing {IN} — 等用户经 Codex 跑完后放回")
    meta = {json.loads(l)["custom_id"]: json.loads(l)
            for l in META.read_text(encoding="utf-8").splitlines() if l.strip()}
    OUTDIR.mkdir(parents=True, exist_ok=True)
    out = OUTDIR / "gpt_probe.jsonl"
    stats = defaultdict(lambda: [0, 0])
    with out.open("w", encoding="utf-8") as f:
        for line in IN.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            m = meta[row["custom_id"]]
            verdict = judge_mod.judge(m["task_id"], row.get("completion") or "",
                                      condition=m["condition"])
            rec = {**m, "model": row.get("model", "gpt-unknown"),
                   "provenance": "user-run via Codex (interactive harness, not controlled API)",
                   "judge": verdict}
            del rec["prompt"]
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            s = stats[m["condition"]]
            s[0] += 1
            s[1] += 1 if verdict.get("strict_correct") else 0
    print(f"judged -> {out}")
    for cond, (n, ok) in sorted(stats.items()):
        print(f"  {cond}: {ok}/{n} strict ({100*ok/n:.0f}%)")


if __name__ == "__main__":
    main()
