# LLM-judge Foil — 跑法说明（交 Codex 跑 GPT，可选再跑 Claude）

## 目的
让一个 LLM 当"裁判"闭卷核对 60 条文学引文准不准，我们再比它与确定性裁判(语料成员事实)
的差距——预期 LLM 会放过不少编造引文，证明确定性验证不可替代（支持论文 F1）。

## 输入
`prompts.jsonl`：每行一个 JSON，含 `item_id` 与 `prompt`。

## 请这样跑（每个 prompt 独立、无上下文、默认温度或 temperature=0 均可）
对每一行，把 `prompt` 原样发给模型，收集它的回复。**逐条独立**，不要把多条拼在一起。
- 主跑：**GPT**（如 gpt-5 / gpt-4o，你 Codex 里可用的）。
- 可选再跑：**Claude**（多一个 LLM 对照更稳）。

## 输出（发回给我）
`outputs_gpt.jsonl`（如再跑 Claude 则加 `outputs_claude.jsonl`），每行：
```
{"item_id": "SEV001", "model": "gpt-5", "response": "<模型原始回复文本>"}
```
`response` 放模型吐出的**原始文本**即可（里面应是那个 JSON；解析我来做）。

## 注意
- 模型只能用**自身知识**判断（提示里已声明"no tools/no search"）——这正是对照点。
- 别把 `foil_key.csv`（真值）喂给模型；那是我评后比对用的。
- 跑完把 `outputs_*.jsonl` 发我或放回 `journal_extension/llm_judge_foil/`。
