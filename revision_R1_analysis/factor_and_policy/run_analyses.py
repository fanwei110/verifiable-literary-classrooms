# -*- coding: utf-8 -*-
"""R1.4 / R1.5 / R1.6 / R1.10 的零 API 派生分析（只读既有冻结日志）。

R1.4  因子异质性：任务型 T1-T3 的接地提升、TGU x C1-C4 矩阵、反馈臂 x 任务型。
      dev(TGU2/TGU4) 与 confirmatory(12 tasks) 严格分开；F4 oracle 不入池。
R1.5  等预算策略混合：固定追加预算 B=3，报告 (resample j, F3 k), j+k=3 的四种
      预先列明分配，paired replay（同一 k=0 失败态、同一 group）。
R1.6  repairer 跨模型覆盖：把修复结果从 M2/M4 扩展到 M1/M3（描述性，标注不可用格）。
R1.10 长度审计：成功修复引文 vs 首轮即正确引文的长度分布、按错误类别分解、短尾比例。

用法：python revision_R1/new_analysis/factor_and_policy/run_analyses.py
输出：同目录 CSV + results.md
"""
from __future__ import annotations

import json
import math
import random
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
DEV = {"TGU2", "TGU4"}
E1C = ["e1c_m1", "e1c_m2", "e1c_m3", "e1c_m4"]
E1B = ["e1b_m2", "e1b_m4"]


def load(tag: str) -> list[dict]:
    p = ROOT / "runs" / "raw" / f"ext_{tag}" / f"{tag}.jsonl"
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def conf(r) -> bool:
    return r["task_id"].split("_")[0] not in DEV


def ttype(r) -> str:
    return r["task_id"].split("_")[1]  # T1 / T2 / T3


def tgu(r) -> str:
    return r["task_id"].split("_")[0]


def wilson(k: int, n: int, z: float = 1.96):
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - h) / d, (c + h) / d)


def cluster_boot(items, B=2000, seed=20260823):
    """任务聚类自助 CI（items: [(task_id, y)]）。"""
    by = defaultdict(list)
    for t, y in items:
        by[t].append(y)
    tasks = list(by)
    if len(tasks) < 2:
        return (float("nan"), float("nan"))
    rng = random.Random(seed)
    means = []
    for _ in range(B):
        pool = []
        for _ in range(len(tasks)):
            pool += by[tasks[rng.randrange(len(tasks))]]
        if pool:
            means.append(sum(pool) / len(pool))
    means.sort()
    return (means[int(0.025 * len(means))], means[int(0.975 * len(means))])


# ---------------------------------------------------------------- R1.4
def r14(md: list[str]):
    rows = [r for tag in E1C for r in load(tag) if r.get("arm") == "F3"]
    md += ["## R1.4 Factor heterogeneity (descriptive; reviewer-requested exploratory)", ""]

    # (a) grounding lift by task type, confirmatory
    md += ["### (a) Grounding lift by task type (confirmatory 12 tasks, k=0)", "",
           "| Task type | n (ungrounded) | rate (C1/C2) | n (grounded) | rate (C3/C4) | lift (pp) | 95% CI (task-cluster) |",
           "|---|---|---|---|---|---|---|"]
    csv_a = ["task_type,n_ungrounded,rate_ungrounded,n_grounded,rate_grounded,lift_pp,ci_low,ci_high"]
    for tt in ["T1", "T2", "T3"]:
        sub = [r for r in rows if conf(r) and ttype(r) == tt]
        ug = [r for r in sub if r["condition"] in ("C1", "C2")]
        gr = [r for r in sub if r["condition"] in ("C3", "C4")]
        if not ug or not gr:
            continue
        ru = sum(int(r["k0_strict"]) for r in ug) / len(ug)
        rg = sum(int(r["k0_strict"]) for r in gr) / len(gr)
        # 任务聚类自助：逐任务配对差
        by_task = defaultdict(lambda: {"u": [], "g": []})
        for r in sub:
            by_task[r["task_id"]]["g" if r["condition"] in ("C3", "C4") else "u"].append(int(r["k0_strict"]))
        diffs = [(t, (sum(d["g"]) / len(d["g"]) - sum(d["u"]) / len(d["u"])))
                 for t, d in by_task.items() if d["g"] and d["u"]]
        lo, hi = cluster_boot(diffs)
        md.append(f"| {tt} | {len(ug)} | {100*ru:.0f}% | {len(gr)} | {100*rg:.0f}% "
                  f"| +{100*(rg-ru):.0f} | [{100*lo:.0f}, {100*hi:.0f}] |")
        csv_a.append(f"{tt},{len(ug)},{ru:.4f},{len(gr)},{rg:.4f},{100*(rg-ru):.2f},{100*lo:.2f},{100*hi:.2f}")
    (OUT / "r14_by_task_type.csv").write_text("\n".join(csv_a) + "\n", encoding="utf-8")

    # (b) TGU x condition matrix, confirmatory vs dev separated
    for label, keep in [("confirmatory", True), ("development", False)]:
        md += ["", f"### (b) TGU x condition strict rate — {label} set (k=0)", "",
               "| TGU | C1 | C2 | C3 | C4 |", "|---|---|---|---|---|"]
        sub = [r for r in rows if conf(r) == keep]
        for g in sorted({tgu(r) for r in sub}):
            cells = []
            for c in ["C1", "C2", "C3", "C4"]:
                s = [r for r in sub if tgu(r) == g and r["condition"] == c]
                cells.append(f"{100*sum(int(r['k0_strict']) for r in s)/len(s):.0f}% (n={len(s)})" if s else "—")
            md.append(f"| {g} | " + " | ".join(cells) + " |")

    # (c) repair by feedback arm x task type — F1..F3 from e1b, F3 from e1c; F4 excluded
    md += ["", "### (c) Repair rate by feedback arm and task type "
           "(k=0 failures, confirmatory; F4 oracle arm excluded by design)", "",
           "| Arm | T1 | T2 | T3 | pooled |", "|---|---|---|---|---|"]
    e1b = [r for tag in E1B for r in load(tag)]
    e1b = [r for r in e1b if conf(r) and not r.get("k0_strict")]
    csv_c = ["arm,task_type,n,fixed,rate"]
    for arm in ["resample", "F1", "F2", "F3"]:
        cells = []
        tot_n = tot_f = 0
        for tt in ["T1", "T2", "T3"]:
            s = [r for r in e1b if r.get("arm") == arm and ttype(r) == tt]
            if not s:
                cells.append("—")
                continue
            f = sum(int(fixed_flag(r)) for r in s)
            tot_n += len(s)
            tot_f += f
            cells.append(f"{100*f/len(s):.0f}% (n={len(s)})")
            csv_c.append(f"{arm},{tt},{len(s)},{f},{f/len(s):.4f}")
        pooled = f"{100*tot_f/tot_n:.0f}% (n={tot_n})" if tot_n else "—"
        md.append(f"| {arm} | " + " | ".join(cells) + f" | {pooled} |")
    (OUT / "r14_arm_by_task_type.csv").write_text("\n".join(csv_c) + "\n", encoding="utf-8")
    md += ["", "*Note: F4 (oracle feedback) is physically isolated as a capability ceiling and is "
           "excluded from all repair pools. Cells are descriptive; no inferential test is applied "
           "to the four-way factorial because 12 task clusters cannot support it.*", ""]


def fixed_flag(r) -> bool:
    """resample 臂按 best-of-k（任一轮通过）；反馈臂按迭代终态。"""
    if r.get("arm") == "resample":
        return any(bool(rd.get("judge", {}).get("strict_correct")) for rd in r.get("rounds", [])[1:])
    return bool(r.get("final_strict"))


# ---------------------------------------------------------------- R1.5
def r15(md: list[str]):
    md += ["## R1.5 Equal-budget policy mixing (paired replay, B = 3 additional calls)", "",
           "Each group branches from the *same* k=0 failure state, so resample and F3 outcomes are "
           "paired within group. We fix the total additional-call budget at B = 3 and report all four "
           "pre-specified allocations; no allocation is selected post hoc.", "",
           "| Allocation | M2 (chat) | M4 (reasoner) |", "|---|---|---|"]
    csv = ["allocation,model,n,success,rate,ci_low,ci_high"]
    data = {}
    for tag in E1B:
        model = "M2" if tag.endswith("m2") else "M4"
        rows = [r for r in load(tag) if conf(r) and not r.get("k0_strict")]
        by_group = defaultdict(dict)
        for r in rows:
            by_group[r["group_id"]][r.get("arm")] = r
        data[model] = by_group

    for j in [3, 2, 1, 0]:
        k = 3 - j
        label = f"resample x{j} + F3 x{k}"
        cells = []
        for model in ["M2", "M4"]:
            items, succ = [], 0
            for gid, arms in data[model].items():
                if "resample" not in arms or "F3" not in arms:
                    continue
                ok = False
                if j > 0:
                    rr = arms["resample"].get("rounds", [])[1: j + 1]
                    ok |= any(bool(x.get("judge", {}).get("strict_correct")) for x in rr)
                if k > 0:
                    fr = arms["F3"].get("rounds", [])[1: k + 1]
                    ok |= any(bool(x.get("judge", {}).get("strict_correct")) for x in fr)
                items.append((arms["resample"]["task_id"], int(ok)))
                succ += int(ok)
            n = len(items)
            lo, hi = cluster_boot(items)
            cells.append(f"{100*succ/n:.1f}% (n={n}) [{100*lo:.0f}, {100*hi:.0f}]" if n else "—")
            if n:
                csv.append(f"{label},{model},{n},{succ},{succ/n:.4f},{lo:.4f},{hi:.4f}")
        md.append(f"| {label} | " + " | ".join(cells) + " |")
    (OUT / "r15_policy_mixing.csv").write_text("\n".join(csv) + "\n", encoding="utf-8")
    md += ["", "*Intervals are task-cluster bootstrap percentiles. This is a descriptive paired replay "
           "of already-collected branches, not a new experiment: the four allocations are recomputed "
           "from the same frozen k=0 failure set, so no additional model calls were made. "
           "Path-dependent cascades (feeding one arm's output into the next) cannot be reconstructed "
           "from branch-parallel logs and are left to future work.*", ""]


# ---------------------------------------------------------------- R1.6
def r16(md: list[str]):
    md += ["## R1.6 Repairer coverage across all four models (descriptive)", "",
           "| Model | Arms available | Condition coverage | F3 repair rate (k=0 failures, confirmatory) |",
           "|---|---|---|---|"]
    csv = ["model,arm,n,fixed,rate,ci_low,ci_high"]
    e1b_models = {"M2", "M4"}
    for tag, model in [("e1c_m1", "M1"), ("e1c_m2", "M2"), ("e1c_m3", "M3"), ("e1c_m4", "M4")]:
        rows = [r for r in load(tag) if r.get("arm") == "F3" and conf(r) and not r.get("k0_strict")]
        if not rows:
            md.append(f"| {model} | — | — | unavailable |")
            continue
        conds = sorted({r["condition"] for r in rows})
        n = len(rows)
        f = sum(int(bool(r.get("final_strict"))) for r in rows)
        lo, hi = wilson(f, n)
        arms = "resample/F1/F2/F3" if model in e1b_models else "F3 only"
        md.append(f"| {model} | {arms} | {'/'.join(conds)} | {100*f/n:.0f}% (n={n}) "
                  f"[{100*lo:.0f}, {100*hi:.0f}] |")
        csv.append(f"{model},F3,{n},{f},{f/n:.4f},{lo:.4f},{hi:.4f}")
    (OUT / "r16_repairer_coverage.csv").write_text("\n".join(csv) + "\n", encoding="utf-8")
    md += ["", "*M1 and M3 were not run on the four-arm dose grid, so arm-level rankings are reported "
           "only for M2 and M4; their F3 coverage is shown here to document that targeted repair was "
           "exercised on all four repairers. Cells marked unavailable are not estimated.*", ""]


# ---------------------------------------------------------------- R1.10
def r110(md: list[str]):
    rows = [r for tag in E1C for r in load(tag) if r.get("arm") == "F3" and conf(r)]
    ql = lambda rd: [len(str(m.get("quote", ""))) for m in (rd.get("judge", {}).get("match_details") or [])]

    first_ok, repaired = [], []
    by_class = defaultdict(lambda: {"init": [], "fin": []})
    for r in rows:
        rounds = r.get("rounds", [])
        if not rounds:
            continue
        if r.get("k0_strict"):
            first_ok += ql(rounds[0])
        elif r.get("final_strict"):
            init_len = ql(rounds[0])
            fin_len = ql(rounds[-1])
            repaired += fin_len
            ec = rounds[0].get("judge", {}).get("error_class_candidate") or "unknown"
            by_class[ec]["init"] += init_len
            by_class[ec]["fin"] += fin_len

    def stats(v):
        if not v:
            return None
        s = sorted(v)
        q = lambda p: s[min(len(s) - 1, int(p * len(s)))]
        return dict(n=len(s), median=q(0.5), q1=q(0.25), q3=q(0.75), p10=q(0.10), mean=sum(s) / len(s))

    a, b = stats(first_ok), stats(repaired)
    md += ["## R1.10 Quotation-length audit for successful repairs", "",
           "| Group | n | median | IQR | 10th pct | mean |", "|---|---|---|---|---|---|"]
    for name, s in [("First-attempt correct (k=0 pass)", a), ("Successful repair (final round)", b)]:
        if s:
            md.append(f"| {name} | {s['n']} | {s['median']} | [{s['q1']}, {s['q3']}] | {s['p10']} | {s['mean']:.0f} |")
    if a and b:
        share = sum(1 for x in repaired if x < a["q1"]) / len(repaired)
        md += ["", f"Share of repaired quotations shorter than the first-attempt-correct lower quartile "
               f"({a['q1']} characters): **{100*share:.0f}%**.", ""]
    md += ["### Length change by initial error class (successful repairs only)", "",
           "| Initial error class | n | median initial | median repaired | delta |", "|---|---|---|---|---|"]
    csv = ["error_class,n,median_initial,median_repaired,delta"]
    for ec, d in sorted(by_class.items(), key=lambda kv: -len(kv[1]["fin"])):
        si, sf = stats(d["init"]), stats(d["fin"])
        if not si or not sf:
            continue
        md.append(f"| {ec} | {sf['n']} | {si['median']} | {sf['median']} | {sf['median']-si['median']:+d} |")
        csv.append(f"{ec},{sf['n']},{si['median']},{sf['median']},{sf['median']-si['median']}")
    (OUT / "r110_length_audit.csv").write_text("\n".join(csv) + "\n", encoding="utf-8")
    md += ["", "*Characters are measured on the quotation strings recorded by the deterministic judge. "
           "The first-attempt-correct distribution is a reference, not an unbiased control: those items "
           "are easier by construction. No pedagogical minimum length is asserted; any minimum-length "
           "guardrail would be a configurable deployment parameter requiring task- and language-specific "
           "calibration, and instructional value remains a question for the prepared human A/B study.*", ""]


def main():
    md = ["# R1.4 / R1.5 / R1.6 / R1.10 — derived analyses (zero additional model calls)", "",
          "All results are recomputed from frozen logs under `runs/raw/ext_e1b_*` and `runs/raw/ext_e1c_*`. "
          "Development TGUs (TGU2, TGU4) are excluded from every confirmatory cell and reported separately "
          "where relevant.", ""]
    r14(md)
    r15(md)
    r16(md)
    r110(md)
    (OUT / "results.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
