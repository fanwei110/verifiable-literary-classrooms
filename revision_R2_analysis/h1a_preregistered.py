"""H1a 按预注册口径重算（D8；更正正文的报告口径）。

preregistration_v2.md 第 17 行：H1a = "k≤3 F3 repair raises C3 strict rate by ≥10pp over its own k=0"，
回退条件 <5pp。这是全部 C3 生成上的绝对提升（分母 = 全部 C3 生成）。
R1 正文报告的是条件修复率（分母 = k=0 失败者）26% [12, 62]。两者回答不同问题，
本脚本两者都算，区间用与 e1_analysis.py 相同的任务簇自助（种子 20260703），
先复现 26% [12, 62] 作为方法锚点。

输出 out/h1a_preregistered.md。
"""
from __future__ import annotations

import random
from collections import defaultdict
from pathlib import Path

import r2_common as C

OUT = Path(__file__).resolve().parent / "out"


def boot_pooled(pairs, n_boot=2000, seed=20260703):
    """与 journal_extension/e1_analysis.py::_boot_ci 逐行相同的任务簇自助（池化均值）。"""
    rng = random.Random(seed)
    by = defaultdict(list)
    for t, v in pairs:
        by[t].append(v)
    tasks = list(by)
    point = sum(v for _, v in pairs) / len(pairs)
    boots = []
    for _ in range(n_boot):
        s = []
        for _ in range(len(tasks)):
            s += by[rng.choice(tasks)]
        boots.append(sum(s) / len(s))
    boots.sort()
    return point, boots[int(0.025 * n_boot)], boots[int(0.975 * n_boot)]


def main() -> None:
    C.utf8_stdout()
    OUT.mkdir(exist_ok=True)
    rows = [r for r in C.load_primary() if r["condition"] == "C3"]
    n = len(rows)
    k0 = sum(int(r["k0_strict"]) for r in rows)
    fin = sum(int(r["final_strict"]) for r in rows)
    fails = [r for r in rows if not r["k0_strict"]]
    fixed = sum(int(r["final_strict"]) for r in fails)

    # 条件修复率（R1 正文口径）——方法锚点，须复现 26% [12, 62]
    cond = boot_pooled([(r["task_id"], int(r["final_strict"])) for r in fails])
    # 预注册口径：每条 C3 生成的 (final − k0)，即绝对提升
    absl = boot_pooled([(r["task_id"], int(r["final_strict"]) - int(r["k0_strict"])) for r in rows])
    # 每个模型分别报告（描述性）
    per_model = defaultdict(lambda: [0, 0, 0])
    for r in rows:
        pm = per_model[r["model"]]
        pm[0] += 1
        pm[1] += int(r["k0_strict"])
        pm[2] += int(r["final_strict"])

    md = ["# H1a under the preregistered definition", "",
          f"C3 generations (confirmatory, F3 arm): n = {n}; k=0 strict = {k0} ({100*k0/n:.2f}%); "
          f"final strict after k≤3 F3 rounds = {fin} ({100*fin/n:.2f}%).", "",
          "| Quantity | Definition | Estimate | Task-cluster 95% CI |", "|---|---|---|---|",
          f"| Preregistered H1a | absolute gain in C3 strict rate over its own k=0 (all C3 generations) | "
          f"+{100*absl[0]:.2f}pp ({fin - k0}/{n}) | [{100*absl[1]:.1f}, {100*absl[2]:.1f}]pp |",
          f"| Conditional repair rate (reported in R1) | repaired / k=0 failures | {100*cond[0]:.1f}% ({fixed}/{len(fails)}) | "
          f"[{100*cond[1]:.0f}, {100*cond[2]:.0f}]% |", "",
          "Preregistered threshold: ≥10pp; fallback if <5pp. The point estimate lies between the two.", "",
          "| Model | n | k=0 strict | final strict | gain (pp) |", "|---|---|---|---|---|"]
    for m in sorted(per_model):
        a, b, c = per_model[m]
        md.append(f"| {m} | {a} | {100*b/a:.1f}% | {100*c/a:.1f}% | +{100*(c-b)/a:.1f} |")
    (OUT / "h1a_preregistered.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
