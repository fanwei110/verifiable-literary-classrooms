# 基线阶梯（M2, confirmatory 12 任务, locator 修正后）

假设梯度：C1 无窗 ≲ BM25-RAG 检索窗 ≪ copy-first ≈ C3 oracle 窗 < C3 验证-修复闭环

## 语料正确性口径（quote+归属+定位+说话人；无 grounding 检查）
| 方法 | 正确/n | % |
|---|---|---|
| C1 无窗 (k0) | 23/120 | 19% |
| BM25-RAG 检索窗 | 16/60 | 27% |
| C3 oracle 窗 (k0) | 94/120 | 78% |

→ 词法检索(BM25)几乎不缩小 C1→C3 差距（检索 recall@3≈0%），oracle 窗口的接地增益不可由朴素检索廉价复制。

## Headline strict 口径（含 grounded-vs-oracle，仅对有窗条件）
| 方法 | strict/n | % |
|---|---|---|
| C3 oracle 窗 (k0) | 89/120 | 74% |
| copy-first (oracle 窗+脚手架) | 44/60 | 73% |
| C3 验证-修复闭环 (k≤3) | 93/120 | 78% |

→ copy-first 脚手架 ≈ C3 oracle（提示技巧不增益，增益来自窗口内容）;闭环在 oracle 之上继续回收残余。

BM25 检索质量：recall@1=0% recall@3=0%；模型采用检索引文比例 45%（其余回退到参数记忆≈C1）。
