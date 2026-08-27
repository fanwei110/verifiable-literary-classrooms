"""构建严重度盲评包（人研究材料包之一）。
从修正后冻结网格分层抽样：正确控制项 + 4 类错误，盲态呈现模型输出（不透露正确答案/自动判定），
供 ≥3 位教师独立评"引文是否准确 + 严重度 1-4 + 是否误导学生"。
产出：盲评表 CSV（发给评委）+ 隐藏答案键 CSV（评后比对）+ 协议 md。
用法：python journal_extension/build_severity_package.py
"""
from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "人研究材料包"
CORR = ROOT / "runs" / "raw" / "formal" / "formal_corr.jsonl"
TASK_DIR = ROOT / "tasks"

# 确定性抽样（可复现，不用随机种子——按 run_id 排序取模）
PER_ERROR_CLASS = 12
N_CONTROLS = 12


def auto_tier(j: dict) -> str:
    """自动严重度分层（修正后）：locator-only 位移 + 版本漂移 = minor；捏造/误归属/接地违背 = serious。"""
    ec = j.get("error_class_candidate")
    if ec == "version_drift":
        return "minor"
    if ec == "context_displacement":
        md = (j.get("match_details") or [{}])[0]
        # 仅 locator 错、其余对 → minor；含 speaker/grounded 错 → serious
        only_loc = (md.get("locator_ok") is False and md.get("speaker_ok") is not False
                    and md.get("grounded_ok") is not False and md.get("quote_found"))
        return "minor" if only_loc else "serious"
    if ec in ("fabricated_quotation", "misattribution"):
        return "serious"
    return "serious"


def claimed_fields(completion: str) -> dict:
    try:
        obj = json.loads(re.search(r"\{.*\}", completion, re.S).group(0))
        ev = (obj.get("evidence") or [{}])[0]
        return {k: str(ev.get(k, "")) for k in ("quote", "author", "work", "locator", "speaker_or_narrator")}
    except Exception:
        return {}


def task_ctx(task_id: str) -> str:
    try:
        import yaml
        t = yaml.safe_load((TASK_DIR / f"{task_id}.yaml").read_text(encoding="utf-8"))
        return f"{t.get('work_title')}｜主题：{t.get('theme')}｜任务：给出确切原文引用并注明出处"
    except Exception:
        return task_id


def main():
    OUT.mkdir(exist_ok=True)
    rows = [json.loads(l) for l in CORR.read_text(encoding="utf-8").splitlines() if l.strip()]
    by_class = defaultdict(list)
    controls = []
    for r in rows:
        j = r.get("judge", {})
        cf = claimed_fields(r.get("completion", ""))
        if not cf.get("quote"):
            continue
        item = {"run_id": r["run_id"], "task_id": r["task_id"], "condition": r["condition"],
                **cf, "strict": r.get("strict_correct"), "error_class": j.get("error_class_candidate")}
        if r.get("strict_correct"):
            controls.append(item)
        elif j.get("error_class_candidate"):
            by_class[j["error_class_candidate"]].append(item)

    def pick(items, n):
        items = sorted(items, key=lambda x: x["run_id"])
        step = max(1, len(items) // n)
        return items[::step][:n]

    sample = []
    for ec in ("fabricated_quotation", "misattribution", "version_drift", "context_displacement"):
        sample += [("err", it) for it in pick(by_class.get(ec, []), PER_ERROR_CLASS)]
    sample += [("ctrl", it) for it in pick(controls, N_CONTROLS)]
    # 打乱呈现顺序（确定性：按 run_id 哈希位排序）
    sample.sort(key=lambda x: x[1]["run_id"][::-1])

    form_rows, key_rows = [], []
    for i, (kind, it) in enumerate(sample, 1):
        iid = f"SEV{i:03d}"
        form_rows.append({
            "item_id": iid,
            "任务语境": task_ctx(it["task_id"]),
            "模型给出的引文": it["quote"],
            "模型标注的作者": it["author"], "模型标注的作品": it["work"],
            "模型标注的出处": it["locator"], "模型标注的说话人": it["speaker_or_narrator"],
            "R_引文准确?(是/否/不确定)": "", "R_严重度(1微小-4严重)": "",
            "R_会误导学生?(是/否)": "", "R_备注": "",
        })
        key_rows.append({"item_id": iid, "kind": kind, "run_id": it["run_id"],
                         "task_id": it["task_id"], "condition": it["condition"],
                         "auto_strict": it["strict"], "auto_error_class": it["error_class"],
                         "auto_severity_tier": "correct" if kind == "ctrl" else auto_tier(
                             {"error_class_candidate": it["error_class"], "match_details": []})})

    with (OUT / "severity_rating_form.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(form_rows[0].keys())); w.writeheader(); w.writerows(form_rows)
    with (OUT / "severity_key_HIDDEN.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(key_rows[0].keys())); w.writeheader(); w.writerows(key_rows)
    print(f"severity 盲评包：{len(form_rows)} 项（{PER_ERROR_CLASS}×4类错误 + {N_CONTROLS}控制）")
    print(f"  -> {OUT/'severity_rating_form.csv'}（发评委）")
    print(f"  -> {OUT/'severity_key_HIDDEN.csv'}（评后比对，勿给评委）")


if __name__ == "__main__":
    main()
