# R1.7 双模型开放式评判结果

严格主指标把 `unsure` 计为未正确分类；模型输出为一次性冻结记录，不主张可逐字复现。

## 总体严格准确率

| 模型 | Closed | RAG top-3 | Gold reference |
|---|---:|---:|---:|
| gpt-5.6-sol (Codex subscription) | 26.7% [17.1%, 39.0%] | 46.7% [34.6%, 59.1%] | 58.3% [45.7%, 69.9%] |
| deepseek-v4-pro | 38.3% [27.1%, 51.0%] | 46.7% [34.6%, 59.1%] | 61.7% [49.0%, 72.9%] |

## 排除 unsure 的敏感性分析

| 模型 | Closed | RAG top-3 | Gold reference |
|---|---:|---:|---:|
| gpt-5.6-sol (Codex subscription) | 61.5% | 59.6% | 64.8% |
| deepseek-v4-pro | 41.8% | 47.5% | 61.7% |

## 错误接受率与正确接受率

| 模型 | 条件 | 错误接受率（错误题判 accurate） | 正确接受率 | Unsure（全部） |
|---|---|---:|---:|---:|
| gpt-5.6-sol (Codex subscription) | closed | 18.8% | 33.3% | 56.7% |
| gpt-5.6-sol (Codex subscription) | rag_top3 | 37.5% | 75.0% | 21.7% |
| gpt-5.6-sol (Codex subscription) | gold_reference | 37.5% | 83.3% | 10.0% |
| deepseek-v4-pro | closed | 66.7% | 100.0% | 8.3% |
| deepseek-v4-pro | rag_top3 | 60.4% | 83.3% | 1.7% |
| deepseek-v4-pro | gold_reference | 43.8% | 83.3% | 0.0% |

## 配对比较

- gpt-5.6-sol (Codex subscription): closed vs. rag_top3, discordant=20, exact p=0.01182, Holm-adjusted p=0.02364.
- gpt-5.6-sol (Codex subscription): rag_top3 vs. gold_reference, discordant=11, exact p=0.06543, Holm-adjusted p=0.06543.
- gpt-5.6-sol (Codex subscription): closed vs. gold_reference, discordant=27, exact p=0.0003107, Holm-adjusted p=0.0009322.
- deepseek-v4-pro: closed vs. rag_top3, discordant=11, exact p=0.2266, Holm-adjusted p=0.2266.
- deepseek-v4-pro: rag_top3 vs. gold_reference, discordant=11, exact p=0.01172, Holm-adjusted p=0.02344.
- deepseek-v4-pro: closed vs. gold_reference, discordant=22, exact p=0.004344, Holm-adjusted p=0.01303.

## RAG top-3 命中与未命中

| 模型 | 命中定义 | 命中 n / 严格准确率 | 未命中 n / 严格准确率 |
|---|---|---:|---:|
| gpt-5.6-sol (Codex subscription) | claim_exact_hit_at_3 | 17 / 41.2% | 43 / 48.8% |
| gpt-5.6-sol (Codex subscription) | task_gold_hit_at_3 | 30 / 53.3% | 30 / 40.0% |
| gpt-5.6-sol (Codex subscription) | diagnostic_hit_at_3 | 30 / 53.3% | 30 / 40.0% |
| deepseek-v4-pro | claim_exact_hit_at_3 | 17 / 41.2% | 43 / 48.8% |
| deepseek-v4-pro | task_gold_hit_at_3 | 30 / 46.7% | 30 / 46.7% |
| deepseek-v4-pro | diagnostic_hit_at_3 | 30 / 46.7% | 30 / 46.7% |

## 解释边界

- 这些比较评估的是冻结的 60 题分层样本，不代表开放域文学事实核验的总体性能。
- GPT 结果来自 Codex CLI/ChatGPT 订阅环境，不能表述为 OpenAI API 实验。
- 确定性验证器的核心优势应表述为语料成员关系的确定性、可审计性与无需模型调用，而不是预设对任意 LLM 的绝对性能优势。

完整题项级结果共 360 条，见 `item_level_scored.csv`。
