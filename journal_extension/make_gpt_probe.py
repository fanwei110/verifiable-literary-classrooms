"""生成 GPT 前沿摸底输入包（用户经 Codex/OpenAI 跑，探索层、不入验证性网格）。

产出 journal_extension/gpt_probe/：
  gpt_probe_input.jsonl —— 24 条 prompt（与漂移切片同网格：6 任务 × C1/C3 × 2 重复）
  README_forCodex.md    —— 给 Codex 的执行说明
  （回收后用 ingest_gpt_probe.py 判分）
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from repair_loop import prompt_path  # noqa: E402

OUT = Path(__file__).resolve().parent / "gpt_probe"
OUT.mkdir(exist_ok=True)

TASKS = ["TGU1_T1", "TGU3_T2", "TGU5_T3", "TGU6_T1", "TGU2_T2", "TGU4_T3"]
CONDITIONS = ["C1", "C3"]
REPS = 2

rows = []
for t in TASKS:
    for c in CONDITIONS:
        variant = "A" if c in ("C1", "C3") else "canonical"
        prompt = prompt_path(c, t, variant).read_text(encoding="utf-8")
        for rep in range(1, REPS + 1):
            rows.append({
                "custom_id": f"GPT_{c}_{t}_{variant}_r{rep:02d}",
                "task_id": t, "condition": c, "variant": variant, "rep": rep,
                "prompt": prompt,
            })

with (OUT / "gpt_probe_input.jsonl").open("w", encoding="utf-8") as f:
    for r in rows:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")

readme = """# GPT 前沿摸底包（给 Codex 执行）

任务：对 `gpt_probe_input.jsonl` 的每一行，把 `prompt` 字段原文发给 GPT 模型
（单轮、默认解码、max_tokens≈2048、**不加任何 system prompt / 追加说明**），
把模型输出原样收集。

输出格式：`gpt_probe_output.jsonl`，每行一个 JSON 对象：
    {"custom_id": "<对应输入行的 custom_id>", "model": "<确切模型名>", "completion": "<模型输出原文>"}

要求：
1. 每行独立新会话（不得共享上下文）；同一行只跑一次，不重试挑答案。
2. 记录确切模型版本号（如 gpt-5.x-...），写进每行的 model 字段。
3. 输出放回本目录，文件名 gpt_probe_output.jsonl。

共 24 条。完成后交回，由 ingest_gpt_probe.py 判分（探索层结果，标注 provenance
deviation：经交互式 harness 生成，非受控 API——只进论文附录/探索性分析）。
"""
(OUT / "README_forCodex.md").write_text(readme, encoding="utf-8")
print(f"wrote {len(rows)} prompts -> {OUT}")
