# DeepSeek 16384 上限批次归档说明

- 状态：整批作废，不进入正式分析。
- 已生成且随后归档的可解析结果：47 条。
- 触发停止的题项：`SEV058 / gold_reference`。
- 失败表现：`completion_tokens=16384`、`reasoning_tokens=16384`，模型在达到输出上限前没有形成最终 JSON。
- 对照证据：同批成功项 `SEV021/gold_reference` 已使用 10376 completion tokens 后自然停止，说明 high-thinking 分布存在超过 16K 的长尾。
- 官方边界：DeepSeek 当前 Models & Pricing 页面标示 V4-Pro 最大输出为 384K；本实验不使用该最大值，而选择统一 `max_tokens=65536` 作为足以覆盖已观察长尾且受 10 美元硬账本约束的安全上限。
- 处置：不对单题做选择性重采样；最终正式批从 0/180 统一重跑。thinking mode、`reasoning_effort=high`、提示、模型和其他请求字段不变。
- 成本：本批以及更早的所有预运行尝试继续保留在 `raw/deepseek_attempts.jsonl`，全部计入 10 美元硬预算。
- 归档文件：`raw/deepseek_results_aborted_max_tokens_16384.jsonl`。

