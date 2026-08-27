# 废弃预检批次：DeepSeek `max_tokens=2048`

- 该批次在 2026-08-23 正式派发开始后被人工中止。
- 原因：4 个长证据题的 `completion_tokens=2048` 且 `reasoning_tokens=2048`，模型没有留下最终 JSON。
- 中止时共有 15 次调用：11 条成功、4 条无最终 JSON。
- 这 11 条成功结果不进入正式分析，因为后续统一把 `max_tokens` 提高到 4096；混用两种上限会破坏同批配置一致性。
- 所有 15 次调用的费用继续保留在 `deepseek_attempts.jsonl` 总账中，并计入 5 美元硬上限。
- 废弃成功结果保存在 `deepseek_results_aborted_max_tokens_2048.jsonl`，仅供审计。
