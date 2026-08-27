"""构建 LLM-judge foil 包（反面对照，支持 F1）。
让 LLM(GPT/Claude) 闭卷核对每条引文准不准，再与确定性裁判的真值比——展示 LLM-judge
会放过编造引文(自我偏好/无语料成员检验)，证明"为什么需要确定性验证"。
复用严重度 60 项英文集(已分层+带真值)。产出：
  llm_judge_foil/prompts.jsonl  —— 每行一个 item_id + prompt（交 Codex 跑 GPT/Claude）
  llm_judge_foil/README_forCodex.md —— 跑法说明
  llm_judge_foil/foil_key.csv   —— item_id → 确定性真值（我评后比对，勿交模型）
用法：python journal_extension/build_llm_judge_foil.py
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "人研究材料包"
OUT = ROOT / "journal_extension" / "llm_judge_foil"

PROMPT_TMPL = (
    "You are acting as an automated verifier of literary quotations, using ONLY your own "
    "knowledge — no external tools, no web search, no lookup.\n\n"
    "Claimed quotation: \"{quote}\"\n"
    "Attributed to: author = {author}; work = {work}; locator = {locator}; "
    "speaker/narrator = {speaker}.\n\n"
    "Question: Is this an accurate, verbatim quotation that is correctly attributed to that "
    "work and speaker?\n"
    "Respond with ONLY a JSON object and nothing else:\n"
    "{{\"verdict\": \"accurate\" | \"inaccurate\" | \"unsure\", \"confidence\": <0.0-1.0>, "
    "\"reason\": \"<one short sentence>\"}}"
)


def clean(s: str) -> str:
    """剔除孤立代理字符（mojibake 残留），保证 prompts.jsonl 是合法 UTF-8。"""
    return str(s).encode("utf-8", "replace").decode("utf-8")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    form = {r["item_id"]: r for r in csv.DictReader(
        (PKG / "severity_rating_form.csv").open(encoding="utf-8-sig"))}
    key = {r["item_id"]: r for r in csv.DictReader(
        (PKG / "severity_key_HIDDEN.csv").open(encoding="utf-8-sig"))}

    prompts, foil_key = [], []
    for iid, r in form.items():
        prompt = clean(PROMPT_TMPL.format(
            quote=r["模型给出的引文"], author=r["模型标注的作者"], work=r["模型标注的作品"],
            locator=r["模型标注的出处"], speaker=r["模型标注的说话人"]))
        prompts.append({"item_id": iid, "prompt": prompt})
        k = key[iid]
        foil_key.append({"item_id": iid, "auto_strict": k["auto_strict"],
                         "auto_error_class": k["auto_error_class"], "kind": k["kind"]})

    with (OUT / "prompts.jsonl").open("w", encoding="utf-8") as f:
        for p in prompts:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    with (OUT / "foil_key.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["item_id", "auto_strict", "auto_error_class", "kind"])
        w.writeheader(); w.writerows(foil_key)

    readme = f"""# LLM-judge Foil — 跑法说明（交 Codex 跑 GPT，可选再跑 Claude）

## 目的
让一个 LLM 当"裁判"闭卷核对 {len(prompts)} 条文学引文准不准，我们再比它与确定性裁判(语料成员事实)
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
{{"item_id": "SEV001", "model": "gpt-5", "response": "<模型原始回复文本>"}}
```
`response` 放模型吐出的**原始文本**即可（里面应是那个 JSON；解析我来做）。

## 注意
- 模型只能用**自身知识**判断（提示里已声明"no tools/no search"）——这正是对照点。
- 别把 `foil_key.csv`（真值）喂给模型；那是我评后比对用的。
- 跑完把 `outputs_*.jsonl` 发我或放回 `journal_extension/llm_judge_foil/`。
"""
    (OUT / "README_forCodex.md").write_text(readme, encoding="utf-8")
    print(f"foil 包：{len(prompts)} 条 prompt -> {OUT}")
    print(f"  prompts.jsonl / README_forCodex.md / foil_key.csv（真值，勿交模型）")


if __name__ == "__main__":
    main()
