# 废弃预检批次：DeepSeek `max_tokens=4096`

- 该批次在 2026-08-23 由运行器自动中止。
- 统一 4096 上限下，12 条正式题成功；随后两个在途长证据题分别出现 `completion_tokens=4096` 且 `reasoning_tokens=4096`，没有最终 JSON。
- 12 条成功结果不进入正式分析，以免正式批次混用两种输出上限。
- 调用费用继续留在 `deepseek_attempts.jsonl` 总账并计入 5 美元硬上限。
- 废弃成功结果保存在 `deepseek_results_aborted_max_tokens_4096.jsonl`。
- 下一批统一使用 8192；若再次出现同类耗尽，则停止抬升上限并审查 thinking/JSON Output 的根本兼容问题。
