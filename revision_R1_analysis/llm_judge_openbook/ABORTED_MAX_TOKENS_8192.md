# DeepSeek 8192 上限批次归档说明

- 状态：整批作废，不进入正式分析。
- 已生成且随后归档的可解析结果：110 条。
- 触发停止的题项：`SEV045 / rag_top3`。
- 失败表现：`completion_tokens=8192`、`reasoning_tokens=8192`，模型在达到输出上限前没有形成最终 JSON。
- 对照证据：同批成功项的完成 token 中位数为 1201、P90 为 3639、P95 为 5240、P99 为 6952；`SEV021/gold_reference` 和 `SEV044/rag_top3` 分别使用 7889 和 7568 completion tokens 后成功，说明 8192 位于 high-thinking 长尾的危险边缘。
- 处置：不对单题做选择性重采样；将整批正式配置统一提高到 `max_tokens=16384`，从 0/180 重跑。thinking mode、`reasoning_effort=high`、提示、模型和其他请求字段不变。
- 成本：本批以及更早的 2048/4096 预运行尝试继续保留在 `raw/deepseek_attempts.jsonl`，全部计入 10 美元硬预算。
- 归档文件：`raw/deepseek_results_aborted_max_tokens_8192.jsonl`。

