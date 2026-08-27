"""反-Goodhart 护栏面板（审计-only，绝不回传入环）。
检测"修复以内容塌缩换正确率"：逐轮引文长度、证据条数、strict/defensible 背离、引文集中度。
用法：python journal_extension/guardrail_panel.py ext_e1a_m2 [ext_e1a_m3 ...]
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parent / "analysis_ext" / "guardrail_report.md"


def extract_quotes(completion: str) -> list[str]:
    try:
        obj = json.loads(re.search(r"\{.*\}", completion, re.S).group(0))
        return [str(e.get("quote", "")) for e in obj.get("evidence", []) if e.get("quote")]
    except Exception:
        return []


def main(tags: list[str]) -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # 防 GBK 控制台无法输出 emoji/中文
    except Exception:
        pass
    logs = []
    for tag in tags:
        core = tag[4:] if tag.startswith("ext_") else tag
        p = ROOT / "runs" / "raw" / f"ext_{core}" / f"{core}.jsonl"
        if not p.exists():
            p = ROOT / "runs" / "raw" / tag / f"{tag}.jsonl"
        if p.exists():
            logs += [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    # 只看有修复轮（k0 失败且做了修复）的记录
    repaired = [r for r in logs if len(r.get("rounds", [])) > 1]
    md = ["# 反-Goodhart 护栏面板（审计-only）", "",
          f"来源 {tags}；含修复轮记录 {len(repaired)}", ""]

    # 逐轮引文长度 & 证据条数
    per_round = defaultdict(lambda: {"qlen": [], "ncount": []})
    conc = Counter()  # 修复后最终引文（判成功者）
    for r in repaired:
        for rd in r["rounds"]:
            quotes = extract_quotes(rd["completion"])
            k = rd["round"]
            if quotes:
                per_round[k]["qlen"].append(sum(len(q) for q in quotes) / len(quotes))
            per_round[k]["ncount"].append(len(quotes))
        if r.get("final_strict"):
            for q in extract_quotes(r["rounds"][-1]["completion"]):
                conc[q.strip()[:50]] += 1

    md += ["## 逐轮引文平均长度 / 证据条数（塌缩检测）",
           "| 轮 k | n | 平均引文字符数 | 平均证据条数 |", "|---|---|---|---|"]
    base_qlen = None
    for k in sorted(per_round):
        d = per_round[k]
        ql = sum(d["qlen"]) / len(d["qlen"]) if d["qlen"] else 0
        nc = sum(d["ncount"]) / len(d["ncount"]) if d["ncount"] else 0
        if k == 0:
            base_qlen = ql
        md.append(f"| {k} | {len(d['ncount'])} | {ql:.0f} | {nc:.2f} |")
    if base_qlen and per_round:
        last_k = max(per_round)
        last_ql = (sum(per_round[last_k]["qlen"]) / len(per_round[last_k]["qlen"])
                   if per_round[last_k]["qlen"] else base_qlen)
        pct = 100 * (last_ql - base_qlen) / base_qlen
        verdict = "⚠️ 引文显著变短，修复以缩短换分" if pct < -15 else "✓ 无显著塌缩"
        md += ["", f"引文长度 k0→k{last_k}: {pct:+.0f}% → **{verdict}**"]

    # strict/defensible 背离
    div = sum(1 for r in repaired if r.get("final_strict")
              and not r["rounds"][-1]["judge"].get("defensible_correct"))
    md += ["", f"## strict 但非 defensible（背离）：{div}（修复后严格通过却非可辩护——异常应为 0，>0 需查）"]

    # 引文集中度：修复成功后是否收敛到少数高频名句
    md += ["", "## 修复后引文集中度 top-5（是否塌缩到易验证名句）",
           "| 引文前缀 | 出现次数 |", "|---|---|"]
    for q, n in conc.most_common(5):
        md.append(f"| {q}... | {n} |")
    md += ["", f"（去重引文 {len(conc)} 条；若 top-1 占比过高＝塌缩迹象）"]

    OUT.write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md[:20]))
    print("... full ->", OUT)


if __name__ == "__main__":
    main(sys.argv[1:] or ["ext_smoke"])
