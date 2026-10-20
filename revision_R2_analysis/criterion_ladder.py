"""判据阶梯与评分规则敏感性（回应 R4.1–R4.3、R4.5；post hoc，非预注册）。

问题：strict 的 locator/speaker/窗口三项对照的是任务策展证据（task-anchored），
grounding 效应是否部分来自这种锚定？做法：在同一批已观察的 k=0 输出上，逐级放宽判据，
并对主口径逐项打开四个预先写定的敏感性开关（规则见 r2_common.VariantJudge）。

输出 out/criterion_ladder.md 与 out/criterion_ladder.csv。
用法：python revision_R2_analysis/criterion_ladder.py
"""
from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

import r2_common as C

OUT = Path(__file__).resolve().parent / "out"

SPECS = [
    ("L0", "Corpus membership only", dict(level="L0")),
    ("L1", "Membership + author and work", dict(level="L1")),
    ("L2", "L1 + speaker + window (no locator)", dict(level="L2")),
    ("strict", "Primary criterion (preregistered implementation)", dict(level="strict")),
    ("S-alias", "strict + translation alias (Ulysses/Odysseus)", dict(level="strict", alias=True)),
    ("S-ordered", "strict + ordered-numeral locator rule", dict(level="strict", ordered=True)),
    ("S-ellipsis", "strict + ellipsis-aware fragment matching", dict(level="strict", ellipsis=True)),
    ("S-nfkd", "strict + diacritic folding (NFKD) and U+2026 as separator", dict(level="strict", nfkd=True)),
    ("S-all", "strict + all four sensitivity rules", dict(level="strict", alias=True, ordered=True, ellipsis=True, nfkd=True)),
]


def main() -> None:
    C.utf8_stdout()
    rows = C.load_primary()
    C.check_anchor(rows)
    base = {r["run_id"]: int(r["k0_strict"]) for r in rows}
    OUT.mkdir(exist_ok=True)
    table = []
    per_task = {}
    for key, label, kw in SPECS:
        vj = C.VariantJudge(**kw)
        out = {r["run_id"]: int(vj.k0(r)) for r in rows}
        rate = defaultdict(lambda: [0, 0])
        for r in rows:
            rate[r["condition"]][0] += out[r["run_id"]]
            rate[r["condition"]][1] += 1
        p, lo, hi, d = C.grounding_effect(rows, out)
        per_task[key] = d
        up = sum(1 for k in out if out[k] and not base[k])
        down = sum(1 for k in out if base[k] and not out[k])
        g_up = sum(1 for r in rows if out[r["run_id"]] and not base[r["run_id"]] and r["condition"] in C.GROUNDED)
        row = {"key": key, "label": label, "effect_pp": round(p, 1), "ci_lo": round(lo, 1), "ci_hi": round(hi, 1),
               "pos_tasks": sum(1 for v in d.values() if v > 0), "flips_fail_to_pass": up,
               "flips_pass_to_fail": down, "flips_up_grounded": g_up, "flips_up_ungrounded": up - g_up}
        for c in ("C1", "C2", "C3", "C4"):
            k, n = rate[c]
            row[f"{c}_pct"] = round(100 * k / n, 1)
            row[f"{c}_n"] = n
        table.append(row)
        print(key, row["effect_pp"], [row["ci_lo"], row["ci_hi"]], "up", up, "down", down)

    with (OUT / "criterion_ladder.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(table[0]))
        w.writeheader()
        w.writerows(table)

    md = ["# Criterion ladder and scoring-rule sensitivity (post hoc)", "",
          f"Sample: {len(rows)} k=0 generations, 12 confirmatory task clusters (F3-arm records of ext_e1c_m1–m4; "
          "dev tasks TGU2/TGU4 excluded). Anchor check: VariantJudge with all switches off reproduces the frozen "
          "k0_strict for every record (0 mismatches).", "",
          "Effect = mean over the 12 tasks of (C3,C4 pass rate − C1,C2 pass rate); CI = task-cluster percentile "
          f"bootstrap, B={C.BOOT_N}, seed={C.BOOT_SEED}.", "",
          "| Level | Criterion | C1 | C2 | C3 | C4 | Grounding effect (pp) | 95% CI | Tasks > 0 | fail→pass (grounded / ungrounded) | pass→fail |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in table:
        md.append(f"| {r['key']} | {r['label']} | {r['C1_pct']}% | {r['C2_pct']}% | {r['C3_pct']}% | {r['C4_pct']}% | "
                  f"{r['effect_pp']:+.1f} | [{r['ci_lo']:.1f}, {r['ci_hi']:.1f}] | {r['pos_tasks']}/12 | "
                  f"{r['flips_fail_to_pass']} ({r['flips_up_grounded']} / {r['flips_up_ungrounded']}) | {r['flips_pass_to_fail']} |")
    md += ["", "## Per-task grounding difference (pp)", "",
           "| Task | " + " | ".join(k for k, _, _ in SPECS) + " |", "|---|" + "---|" * len(SPECS)]
    for t in sorted(per_task["strict"]):
        md.append(f"| {t} | " + " | ".join(f"{per_task[k][t]:+.1f}" for k, _, _ in SPECS) + " |")
    md += ["", "Note: these rescorings report how the same observed outputs fare under each rule. They are not "
           "re-runs of the repair loop under a different verifier, whose stopping and feedback would differ."]
    (OUT / "criterion_ladder.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("->", OUT / "criterion_ladder.md")


if __name__ == "__main__":
    main()
