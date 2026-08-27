# R1.7 双模型开放式引文评判实验

本目录实现 60 个冻结题项、三种证据条件和两个独立模型 judge 的同批对照。GPT 侧通过本机 ChatGPT 登录的 Codex CLI 订阅调用 `gpt-5.6-sol`；DeepSeek 侧通过官方 Chat Completions API 调用 `deepseek-v4-pro`。OpenRouter 不参与本实验。

## 固定设计

- `closed`：不提供外部证据。
- `rag_top3`：`all-MiniLM-L6-v2` 对六部冻结语料的全库 dense 检索；分段约 700 字符、重叠 150 字符、top-3。
- `gold_reference`：由隐藏题项—任务映射统一附加冻结任务 YAML 的 `source_window` 与规范元数据。
- 每个模型、题项和条件只运行一次；正式样本为 `60 × 3 × 2 = 360`。
- `unsure` 在严格主分析中计为未正确分类，同时报告排除 `unsure` 的敏感性分析。

## 可复现边界

提示、输入哈希、模型标识、CLI/API 配置和原始最终响应会冻结；模型采样输出本身不保证逐字复现。GPT 结果必须表述为 Codex CLI/ChatGPT subscription judge，不能写成 OpenAI API 实验。

GPT 隔离除 `--ephemeral`、`--ignore-user-config`、空白目录和 read-only sandbox 外，还显式设置 `skills.include_instructions=false` 与 `skills.bundled.enabled=false`。仅关闭 plugins feature 不足以移除 skills catalogue；该问题下产生的批次已整体归档。正式验收要求每条事件流既无工具事件，也无客户端 error/技能注入事件。

DeepSeek 请求固定 `thinking.enabled`、`reasoning_effort=high`、`max_tokens=65536` 和 JSON Output，不发送 thinking mode 不支持的采样参数。正式批曾依次以 2048、4096、8192 和 16384 上限做过预运行；四档均出现纯 reasoning 占满上限而未生成 JSON 的情况，因此均整体归档、不进入分析。官方当前模型页给出的最大输出为 384K；最终正式批从零统一使用 65536，以覆盖已观测到的 high-thinking 长尾。所有预运行费用仍计入 10 美元总账，且峰值保守账本达到 9.75 美元即停止派发。价格按 2026-08-23 官方 [Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/) 分项核算。

## 执行顺序

使用 `python` 依次运行：

1. `prepare_manifest.py`
2. `pytest -q tests`
3. `run_experiment.py --provider both --deepseek-key-file <KEY_FILE> --deepseek-budget-usd 10 --resume`
4. `validate_run.py`
5. `analyze_results.py`
6. `security_scan.py --deepseek-key-file <KEY_FILE>`

运行器不会记录密钥内容或密钥路径；DeepSeek 失败响应也会在写盘前脱敏。`raw/gpt_events/` 保存 Codex JSONL 事件，用于证明正式结果没有工具调用。
