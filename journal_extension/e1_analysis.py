"""E1a 主线分析：可修性矩阵（headline）+ k=0 基线 + 存活曲线 + H2b + 任务聚类自助。
用法：python journal_extension/e1_analysis.py ext_e1a_m2 [ext_e1a_m3 ...]
输出 analysis_ext/e1_report.md + e1_repair_matrix.csv
"""
from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTDIR = Path(__file__).resolve().parent / "analysis_ext"
DEV = {"TGU2", "TGU4"}  # held-out 开发任务

# 复用冻结版的聚类自助（若可用）；否则内置简版
try:
    sys.path.insert(0, str(ROOT))
    from analysis.inferential_analysis import cluster_bootstrap  # type: ignore
    HAVE_CB = True
except Exception:
    HAVE_CB = False


def _boot_ci(pairs, n_boot=2000):
    """按任务聚类自助修复提升的 95%CI。pairs=[(task, fixed01)]。内置简版。"""
    import random
    rng = random.Random(20260703)
    by_task = defaultdict(list)
    for t, v in pairs:
        by_task[t].append(v)
    tasks = list(by_task)
    if not tasks:
        return (0.0, 0.0, 0.0)
    point = sum(v for _, v in pairs) / len(pairs)
    boots = []
    for _ in range(n_boot):
        samp = []
        for _ in range(len(tasks)):
            samp += by_task[rng.choice(tasks)]
        boots.append(sum(samp) / len(samp))
    boots.sort()
    return point, boots[int(0.025 * n_boot)], boots[int(0.975 * n_boot)]


def resolve_log(tag):
    """约定：目录 ext_{tag}，文件 {tag}.jsonl。兼容传入带/不带 ext_ 前缀。"""
    core = tag[4:] if tag.startswith("ext_") else tag
    cands = [ROOT / "runs" / "raw" / f"ext_{core}" / f"{core}.jsonl",
             ROOT / "runs" / "raw" / tag / f"{tag}.jsonl"]
    for p in cands:
        if p.exists():
            return p
    return cands[0]


def load(tags):
    rows = []
    for tag in tags:
        p = resolve_log(tag)
        if not p.exists():
            print("MISSING", p)
            continue
        rows += [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    return rows


def task_group(gid):
    # group_id = {m}_{c}_{t}_{variant}_r{rep}; t 形如 TGU3_T1
    parts = gid.split("_")
    return parts[2] if len(parts) > 2 else "?"


def main(tags):
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # 防中文 Windows GBK 控制台崩溃
    except Exception:
        pass
    rows = load(tags)
    # 每 group 每 arm 一条；E1a 只有 F3
    f3 = [r for r in rows if r["arm"] == "F3"]
    # group 去重取 k0（k0 对所有 arm 相同）
    groups = {}
    for r in rows:
        groups.setdefault(r["group_id"], r)

    md = [f"# E1a 主线分析（{tags}）", "",
          f"F3 记录 {len(f3)}；去重 group {len(groups)}", ""]

    # ---- k=0 基线 by model×condition（confirmatory 12 任务）----
    md += ["## k=0 基线 strict%（confirmatory 12 任务；dev 另列）", "",
           "| 模型 | 条件 | conf n | conf strict% | dev strict% |", "|---|---|---|---|---|"]
    base = defaultdict(lambda: defaultdict(lambda: [0, 0]))  # [conf, dev] each [n,s]
    kc = defaultdict(lambda: {"conf": [0, 0], "dev": [0, 0]})
    for g in groups.values():
        m, c = g["model"], g["condition"]
        split = "dev" if g["task_id"].split("_")[0] in DEV else "conf"
        kc[(m, c)][split][0] += 1
        kc[(m, c)][split][1] += 1 if g["k0_strict"] else 0
    for (m, c) in sorted(kc):
        d = kc[(m, c)]
        cn, cs = d["conf"]; dn, ds = d["dev"]
        md.append(f"| {m} | {c} | {cn} | {100*cs/cn:.0f}% | {100*ds/dn:.0f}% |" if cn and dn
                  else f"| {m} | {c} | {cn} | {(100*cs/cn if cn else 0):.0f}% | {(100*ds/dn if dn else 0):.0f}% |")
    md.append("")

    # ---- 可修性矩阵（headline）：F3 修复率 × 初始错误类别 × 条件（confirmatory 池化模型）----
    md += ["## 可修性矩阵（headline）：F3 修复率 × 初始错误类别 × 条件",
           "（仅 confirmatory 12 任务；k0 失败组为分母）", "",
           "| 初始错误类别 | 条件 | 修复/n | 修复率 | 95%CI(任务聚类) |", "|---|---|---|---|---|"]
    matrix = defaultdict(lambda: defaultdict(list))  # cls -> cond -> [(task, fixed01)]
    csv_rows = []
    for r in f3:
        if r["k0_strict"]:
            continue
        if r["task_id"].split("_")[0] in DEV:
            continue
        cls = (r["rounds"][0]["judge"].get("error_class_candidate") or "unknown")
        cond = r["condition"]
        matrix[cls][cond].append((r["task_id"], 1 if r["final_strict"] else 0))
    for cls in sorted(matrix):
        for cond in sorted(matrix[cls]):
            pairs = matrix[cls][cond]
            n = len(pairs)
            s = sum(v for _, v in pairs)
            pt, lo, hi = _boot_ci(pairs)
            md.append(f"| {cls} | {cond} | {s}/{n} | {100*s/n:.0f}% | [{100*lo:.0f}, {100*hi:.0f}] |")
            csv_rows.append({"error_class": cls, "condition": cond, "n": n,
                             "fixed": s, "repair_rate": round(s / n, 3),
                             "ci_lo": round(lo, 3), "ci_hi": round(hi, 3)})
    md.append("")

    # ---- H2a 类别排序（池化条件，confirmatory）----
    md += ["## H2a 错误类别修复率排序（池化 grounded 条件 C2/C3/C4）", ""]
    cls_agg = defaultdict(lambda: [0, 0])
    for r in f3:
        if r["k0_strict"] or r["condition"] == "C1":
            continue
        if r["task_id"].split("_")[0] in DEV:
            continue
        cls = (r["rounds"][0]["judge"].get("error_class_candidate") or "unknown")
        cls_agg[cls][0] += 1
        cls_agg[cls][1] += 1 if r["final_strict"] else 0
    order = sorted(cls_agg.items(), key=lambda kv: kv[1][1] / max(kv[1][0], 1), reverse=True)
    for cls, (n, s) in order:
        md.append(f"- {cls}: {s}/{n} = {100*s/max(n,1):.0f}%")
    md.append("")

    # ---- H2b fabrication C1 vs C3 ----
    md += ["## H2b 捏造类修复率：C1(无窗) vs C3(有窗)", ""]
    for cond in ("C1", "C3"):
        sub = [r for r in f3 if not r["k0_strict"]
               and r["condition"] == cond
               and (r["rounds"][0]["judge"].get("error_class_candidate") == "fabricated_quotation")
               and r["task_id"].split("_")[0] not in DEV]
        if sub:
            s = sum(1 for r in sub if r["final_strict"])
            md.append(f"- {cond} fabrication: {s}/{len(sub)} = {100*s/len(sub):.0f}%")
    md.append("")

    # ---- 存活曲线（F3，k0 失败组，confirmatory）----
    md += ["## 存活曲线：F3 每轮累计修复率", "",
           "| 到第 k 轮 | 累计修复% |", "|---|---|"]
    fails = [r for r in f3 if not r["k0_strict"] and r["task_id"].split("_")[0] not in DEV]
    nf = len(fails)
    for k in (1, 2, 3):
        fixed = sum(1 for r in fails
                    if any(rd["judge"].get("strict_correct") for rd in r["rounds"][1:k + 1]))
        md.append(f"| {k} | {100*fixed/max(nf,1):.0f}% |")
    md.append("")

    # ---- H1a 主要对比：C3 修复提升 + 聚类自助 CI ----
    c3 = [r for r in f3 if not r["k0_strict"] and r["condition"] == "C3"
          and r["task_id"].split("_")[0] not in DEV]
    pairs = [(r["task_id"], 1 if r["final_strict"] else 0) for r in c3]
    pt, lo, hi = _boot_ci(pairs)
    md += ["## H1a 主要对比（primary）：C3 confirmatory F3 修复率（k0 失败组内）",
           f"- 修复率 = {100*pt:.0f}%  95%CI[{100*lo:.0f}, {100*hi:.0f}]（{len(pairs)} 组，任务聚类自助）",
           f"- 门槛：≥10pp 提升即 C3 最终率相对 k0 抬升 → {'见 k0 基线对照' }", ""]

    OUTDIR.mkdir(exist_ok=True)
    (OUTDIR / "e1_report.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    with (OUTDIR / "e1_repair_matrix.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["error_class", "condition", "n", "fixed",
                                          "repair_rate", "ci_lo", "ci_hi"])
        w.writeheader()
        w.writerows(csv_rows)
    print("\n".join(md))
    print("-> analysis_ext/e1_report.md + e1_repair_matrix.csv")


if __name__ == "__main__":
    main(sys.argv[1:] or ["ext_e1a_m2"])
