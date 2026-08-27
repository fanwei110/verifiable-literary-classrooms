# GPT 技能元数据批次归档说明

- 状态：整批作废，不进入正式分析。
- 已生成且随后归档的可解析结果：143 条。
- 发现方式：Codex JSONL 事件流包含客户端提示 `Skill descriptions were shortened ...`。虽然这些记录没有任何工具调用，且已使用 `--ignore-user-config`、空白目录、ephemeral 会话和 read-only sandbox，但该提示证明技能目录摘要仍进入了模型上下文，不满足预定的“不得加载用户技能”隔离标准。
- 无效尝试：仅禁用 `plugins` 等 feature flags 后，smoke 仍出现同一提示。
- 有效修复：在 CLI 配置层显式加入 `skills.include_instructions=false` 与 `skills.bundled.enabled=false`。修复后的 smoke 事件流只有 `thread.started`、`turn.started`、最终 `agent_message` 和 `turn.completed`，不再包含技能提示或其他错误事件。
- 处置：143 条结果与其事件目录整体归档；GPT 正式批从 0/180 重跑。归档批不进入统计，也不用于选择正式响应。
- 归档文件：`raw/gpt_results_aborted_plugins_loaded.jsonl`；事件：`raw/gpt_events_aborted_plugins_loaded/`。

