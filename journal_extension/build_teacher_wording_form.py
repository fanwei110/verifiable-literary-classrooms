"""生成教师课堂措辞采集表（人研究材料包之一）。
从英文 tasks/ 与中文 tasks_zh/ 汇出 (作品×主题×任务型)，供教师写自己课堂上的自然引导措辞，
用于替换研究中的模拟人设提示（C1/C3），检验真实措辞下结论是否稳健。
用法：python journal_extension/build_teacher_wording_form.py
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "人研究材料包"
TYPE_HINT = {"T1": "检索：请学生给出一句确切原文引用",
             "T2": "归属：请学生说出某句出自谁/何处",
             "T3": "小课：围绕主题用两句引文做一段讲解"}


def en_rows():
    import yaml
    rows = []
    for p in sorted((ROOT / "tasks").glob("TGU*_T*.yaml")):
        t = yaml.safe_load(p.read_text(encoding="utf-8"))
        rows.append({"item_id": t["task_id"], "lang": "EN", "work": t.get("work_title"),
                     "theme": t.get("theme"), "task_type": t.get("task_type"),
                     "task_hint": TYPE_HINT.get(t.get("task_type"), "")})
    return rows


def zh_rows():
    rows = []
    for p in sorted((ROOT / "tasks_zh").glob("ZTGU*_T*.json")):
        t = json.loads(p.read_text(encoding="utf-8"))
        rows.append({"item_id": t["task_id"], "lang": "ZH", "work": t.get("work_title"),
                     "theme": t.get("theme"), "task_type": t.get("task_type"),
                     "task_hint": TYPE_HINT.get(t.get("task_type"), "")})
    return rows


def main():
    OUT.mkdir(exist_ok=True)
    rows = en_rows() + zh_rows()
    form = []
    for r in rows:
        form.append({
            "item_id": r["item_id"], "语言": r["lang"], "作品/Work": r["work"],
            "主题/Theme": r["theme"], "任务型": f"{r['task_type']}（{r['task_hint']}）",
            "教师自然措辞（你在课堂上会怎么说/怎么布置这个引用任务？请用你自己的话）": "",
            "备选措辞2（可选，体现措辞多样性）": "",
        })
    with (OUT / "teacher_wording_form.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(form[0].keys())); w.writeheader(); w.writerows(form)

    inst = ["# 教师课堂措辞采集表 — 说明", "",
            f"共 {len(form)} 项（英文 {len(en_rows())} + 中文 {len(zh_rows())}）。",
            "**目的**：研究中给模型的提示是我们模拟的教师人设。请你就每一项，写出**你自己在真实课堂上**会如何向学生布置/引导这个引用任务——用你自然的措辞，不必套用任何格式。",
            "**为什么**：用真实教师措辞替换模拟人设，检验研究结论（接地/验证的价值）在真实语言下是否稳健。",
            "**怎么填**：`teacher_wording_form.csv` 每行一项，填最后两列（第二列可留空）。中文项用中文，英文项用英文。",
            "**匿名**：不采集你的姓名等身份信息（除知情同意签署）。见 `ethics_and_consent.md`。",
            "**时长**：约 20-30 分钟。"]
    (OUT / "teacher_wording_README.md").write_text("\n".join(inst) + "\n", encoding="utf-8")
    print(f"教师措辞表：{len(form)} 项 -> {OUT/'teacher_wording_form.csv'} + README")


if __name__ == "__main__":
    main()
