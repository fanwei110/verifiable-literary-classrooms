# GPT 前沿摸底包（给 Codex 执行）

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
