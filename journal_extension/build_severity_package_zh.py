"""构建中文严重度盲评包（供古典文学老师评定，锚定 judge_zh）。
从中文运行日志（zh_e1 + zh_spike*）抽 k0 完成：分层错误类别 + 正确控制项，盲态呈现。
产出 人研究材料包/severity_zh_rating_form.csv（发）+ severity_zh_key_HIDDEN.csv（藏）。
"""
from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "人研究材料包"
LOGS = ["zh_e1", "zh_spike", "zh_spike2", "zh_spike4"]
WORK = {"analects": "《論語·學而》", "shishuo": "《世說新語·政事》"}


def claimed(completion):
    try:
        obj = json.loads(re.search(r"\{.*\}", completion, re.S).group(0))
        ev = (obj.get("evidence") or [{}])[0]
        return {k: str(ev.get(k, "")) for k in ("quote", "work", "speaker_or_narrator", "locator")}
    except Exception:
        return {}


def load():
    recs = []
    seen = set()
    for tag in LOGS:
        p = ROOT / "runs" / "raw" / f"ext_{tag}" / f"{tag}.jsonl"
        if not p.exists():
            continue
        for l in p.read_text(encoding="utf-8").splitlines():
            if not l.strip():
                continue
            r = json.loads(l)
            comp = r["rounds"][0]["completion"] if "rounds" in r else r.get("completion", "")
            judge = r["rounds"][0]["judge"] if "rounds" in r else r.get("judge", {})
            strict = r.get("k0_strict", r.get("strict"))
            wid = r.get("work_id") or ("analects" if r["task_id"].startswith("ZTGU1") else "shishuo")
            cf = claimed(comp)
            if not cf.get("quote"):
                continue
            key = (cf["quote"][:20], wid)
            if key in seen:
                continue
            seen.add(key)
            recs.append({"task_id": r["task_id"], "work_id": wid, "strict": bool(strict),
                         "error_class": judge.get("error_class_candidate"), **cf})
    return recs


def main():
    OUT.mkdir(exist_ok=True)
    recs = load()
    controls = [r for r in recs if r["strict"]]
    by_cls = defaultdict(list)
    for r in recs:
        if not r["strict"] and r["error_class"]:
            by_cls[r["error_class"]].append(r)

    def pick(items, n):
        items = sorted(items, key=lambda x: x["quote"])
        step = max(1, len(items) // n)
        return items[::step][:n]

    sample = []
    for ec, items in sorted(by_cls.items(), key=lambda kv: -len(kv[1])):
        sample += [("err", r) for r in pick(items, 10)]
    sample += [("ctrl", r) for r in pick(controls, 10)]
    sample.sort(key=lambda x: x[1]["quote"][::-1])

    form, key = [], []
    for i, (kind, r) in enumerate(sample, 1):
        iid = f"SEVZH{i:03d}"
        form.append({"item_id": iid, "作品": WORK.get(r["work_id"], r["work_id"]),
                     "模型给出的引文": r["quote"], "模型标注的说话人": r["speaker_or_narrator"],
                     "模型标注的出处": r["locator"],
                     "R_引文准确?(是/否/不确定)": "", "R_严重度(1微小-4严重)": "",
                     "R_会误导学生?(是/否)": "", "R_备注": ""})
        key.append({"item_id": iid, "kind": kind, "task_id": r["task_id"],
                    "work_id": r["work_id"], "auto_strict": r["strict"],
                    "auto_error_class": r["error_class"] or "correct"})
    with (OUT / "severity_zh_rating_form.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(form[0].keys())); w.writeheader(); w.writerows(form)
    with (OUT / "severity_zh_key_HIDDEN.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(key[0].keys())); w.writeheader(); w.writerows(key)
    from collections import Counter
    print(f"中文严重度盲评包：{len(form)} 项")
    print("  错误类别:", dict(Counter(k["auto_error_class"] for k in key)))
    print(f"  -> {OUT/'severity_zh_rating_form.csv'}（发古典文学评委）")


if __name__ == "__main__":
    main()
