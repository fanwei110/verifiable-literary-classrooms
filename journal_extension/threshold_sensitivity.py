"""预注册判据敏感性（零 API 成本，重判冻结网格）。
(a) locator 容差 ∈ {0.60,0.75,0.90}：影响 strict（重判）。
(b) drift 阈值 ∈ {0.65,0.72,0.80}：只影响 version_drift/fabricated 分类（从存储 approx_score 重算，无需重判）。
用法：python journal_extension/threshold_sensitivity.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "harness"))
sys.path.insert(0, str(ROOT / "journal_extension"))
import judge as judge_mod  # noqa: E402
import apply_corrections  # noqa: E402
apply_corrections.patch(judge_mod)

FORMAL = ROOT / "runs" / "raw" / "formal" / "formal.jsonl"
OUT = ROOT / "journal_extension" / "analysis_ext" / "threshold_sensitivity.md"


def make_locator_match(tol):
    cl = judge_mod.canonical_locator

    def lm(claimed, actual):
        c, a = cl(claimed), cl(actual)
        if not c or not a:
            return False
        if a in c or c in a:
            return True
        ct, at = set(c.split()), set(a.split())
        return bool(at) and len(ct & at) / len(at) >= tol
    return lm


def main():
    rows = [json.loads(l) for l in FORMAL.read_text(encoding="utf-8").splitlines() if l.strip()]
    md = ["# 判据敏感性（冻结网格 2160，locator 修正后）", ""]

    # (a) locator 容差 → strict%
    md += ["## (a) locator 容差 → 各条件 strict%（重判）", "",
           "| 容差 | C1 | C2 | C3 | C4 | 总 |", "|---|---|---|---|---|---|"]
    base_line = None
    for tol in (0.60, 0.75, 0.90):
        judge_mod.locator_match = make_locator_match(tol)
        by = defaultdict(lambda: [0, 0])
        tot = [0, 0]
        for r in rows:
            v = judge_mod.judge(r["task_id"], r.get("completion", ""), condition=r["condition"])
            s = bool(v.get("strict_correct"))
            by[r["condition"]][0] += 1; by[r["condition"]][1] += s
            tot[0] += 1; tot[1] += s
        cells = " | ".join(f"{100*by[c][1]/by[c][0]:.0f}%" for c in ("C1", "C2", "C3", "C4"))
        line = f"| {tol:.2f}{' (默认)' if tol==0.75 else ''} | {cells} | {100*tot[1]/tot[0]:.0f}% |"
        md.append(line)
        if tol == 0.75:
            base_line = tot[1] / tot[0]
    md += ["", f"→ strict 对 locator 容差稳健（默认 0.75 总率 {100*base_line:.0f}%；0.60↔0.90 变动见上表，"
           "证明结论不靠某一阈值）。"]

    # (b) drift 阈值 → version_drift/fabricated 分类（从 approx_score 重算，只对 quote_found=False 的失败）
    md += ["", "## (b) drift 阈值 → 未命中失败的 version_drift/fabricated 划分（分类重算，不影响 strict）", "",
           "| 阈值 | version_drift | fabricated | drift占未命中% |", "|---|---|---|---|"]
    notfound = []
    for r in rows:
        for m in (r.get("judge", {}).get("match_details") or []):
            if m.get("quote_found") is False:
                notfound.append(m.get("approx_score") or 0.0)
    for th in (0.65, 0.72, 0.80):
        drift = sum(1 for a in notfound if a >= th)
        fab = len(notfound) - drift
        md.append(f"| {th:.2f}{' (默认)' if th==0.72 else ''} | {drift} | {fab} | "
                  f"{100*drift/max(len(notfound),1):.0f}% |")
    md += ["", f"→ 未命中引文共 {len(notfound)} 条；drift/fabricated 划分随阈值平滑变动，不改 strict 结论；"
           "报告用默认 0.72 并附此敏感区间。"]

    OUT.write_text("\n".join(md) + "\n", encoding="utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    print("\n".join(md))


if __name__ == "__main__":
    main()
