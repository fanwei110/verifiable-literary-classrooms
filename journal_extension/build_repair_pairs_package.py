"""构建修复前后成对盲评包（人研究材料包之一）。
从修正后闭环日志抽取 (k0原始 vs 修复后最终) 引文对，A/B 盲态随机呈现，
供教师判"哪版更准确/更宜课堂 + 各自是否正确"。验证：修复是否真提升人类可见质量，
以及护栏症状（引文缩短 -24%）是否让修复在人眼中反而变差（Goodhart）。
用法：python journal_extension/build_repair_pairs_package.py
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "人研究材料包"
LOGS = ["e1c_m2", "e1c_m3", "e1c_m4"]
N_SUCCESS = 30   # 修复成功（自动判 strict）
N_FAIL = 15      # 修复后仍失败（检验人是否同意"没修好"）


def q(completion: str) -> dict:
    try:
        obj = json.loads(re.search(r"\{.*\}", completion, re.S).group(0))
        ev = (obj.get("evidence") or [{}])[0]
        return {k: str(ev.get(k, "")) for k in ("quote", "author", "work", "locator", "speaker_or_narrator")}
    except Exception:
        return {}


def qlen(completion):
    return len(q(completion).get("quote", ""))


def main():
    OUT.mkdir(exist_ok=True)
    import yaml
    pairs = []
    for tag in LOGS:
        p = ROOT / "runs" / "raw" / f"ext_{tag}" / f"{tag}.jsonl"
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if r["arm"] != "F3" or r["k0_strict"] or len(r["rounds"]) < 2:
                continue
            orig, final = r["rounds"][0]["completion"], r["rounds"][-1]["completion"]
            oq, fq = q(orig), q(final)
            if not oq.get("quote") or not fq.get("quote"):
                continue
            pairs.append({"run_id": r["run_id"], "task_id": r["task_id"], "condition": r["condition"],
                          "repaired_success": bool(r["final_strict"]),
                          "orig": oq, "final": fq,
                          "shortened": qlen(final) < qlen(orig) - 5})
    succ = sorted([x for x in pairs if x["repaired_success"]], key=lambda x: x["run_id"])
    fail = sorted([x for x in pairs if not x["repaired_success"]], key=lambda x: x["run_id"])

    def pick(items, n):
        step = max(1, len(items) // n); return items[::step][:n]
    sample = pick(succ, N_SUCCESS) + pick(fail, N_FAIL)
    sample.sort(key=lambda x: x["run_id"][::-1])  # 确定性打乱

    def ctx(tid):
        try:
            t = yaml.safe_load((ROOT / "tasks" / f"{tid}.yaml").read_text(encoding="utf-8"))
            return f"{t.get('work_title')}｜主题：{t.get('theme')}"
        except Exception:
            return tid

    form, key = [], []
    for i, x in enumerate(sample, 1):
        iid = f"PAIR{i:03d}"
        # A/B 随机（确定性：按 run_id 末位奇偶）——A 有时是原始有时是修复
        orig_is_A = (sum(map(ord, x["run_id"])) % 2 == 0)
        A, B = (x["orig"], x["final"]) if orig_is_A else (x["final"], x["orig"])
        def fmt(d):
            return f'“{d["quote"]}” — {d.get("author","")}《{d.get("work","")}》 {d.get("locator","")}｜{d.get("speaker_or_narrator","")}'
        form.append({"item_id": iid, "任务语境": ctx(x["task_id"]),
                     "版本A": fmt(A), "版本B": fmt(B),
                     "R_哪版更准确宜课堂(A/B/相当)": "", "R_A正确?(是/否)": "", "R_B正确?(是/否)": "", "R_备注": ""})
        key.append({"item_id": iid, "run_id": x["run_id"], "task_id": x["task_id"],
                    "orig_is_A": orig_is_A, "repaired_success": x["repaired_success"],
                    "repair_shortened_quote": x["shortened"]})

    with (OUT / "repair_pairs_form.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(form[0].keys())); w.writeheader(); w.writerows(form)
    with (OUT / "repair_pairs_key_HIDDEN.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(key[0].keys())); w.writeheader(); w.writerows(key)
    ns = sum(1 for k in key if k["repaired_success"])
    nsh = sum(1 for k in key if k["repair_shortened_quote"])
    print(f"成对盲评包：{len(form)} 对（修复成功 {ns} + 仍失败 {len(form)-ns}；其中修复缩短引文 {nsh} 对）")
    print(f"  -> {OUT/'repair_pairs_form.csv'}（发评委，A/B 盲）+ repair_pairs_key_HIDDEN.csv")


if __name__ == "__main__":
    main()
