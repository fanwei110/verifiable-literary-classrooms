# -*- coding: utf-8 -*-
"""汇总 §4/§5 补表补图所需数字（全部零 API，只读现成日志）：
- F5 best-of-k：在**修正后** 2160 网格（formal_corr.jsonl）上按 cell 10 次结果的
  hypergeometric 口径（不放回抽 k，取 best）算各条件 k=1..10 曲线（主稿 §4.3 口径）。
- T6 recall@k：BM25/dense 检索日志 gold_seg_rank → recall@{1,3,5,10}。
- T5 中文：zh_e1.jsonl 按作品×条件×模型 的 k0/final strict（仅 C1/C3，描述性）。
- T8 四臂×条件：ext_e1b_{m2,m4} 各臂在 k0 失败组内修复率（confirmatory）。
输出打印到 stdout，供手工排入正文（逐格与冻结正文口径核对）。
"""
from __future__ import annotations
import json, math, collections
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEV = {"TGU2", "TGU4"}


def load(p):
    p = Path(p)
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] if p.exists() else []


def bok_hyper(N, S, k):
    """N 次结果里 S 个成功，不放回抽 k，best（至少一个成功）的概率。"""
    if k >= N:
        return 1.0 if S > 0 else 0.0
    return 1.0 - math.comb(N - S, k) / math.comb(N, k)


# ---------- F5: best-of-k on corrected grid ----------
def f5():
    rows = load(ROOT / "runs/raw/formal/formal_corr.jsonl")
    # cell = (model_label, task_id, condition) → reps 的 strict 列表
    cells = collections.defaultdict(list)
    for r in rows:
        cells[(r.get("model_label") or r.get("model"), r["task_id"], r["condition"])].append(int(bool(r["strict_correct"])))
    by_cond = collections.defaultdict(list)
    for (m, t, c), reps in cells.items():
        by_cond[c].append((len(reps), sum(reps)))
    print("=== F5 best-of-k（修正后 2160 网格, hypergeometric, 各 cell 平均）===")
    print("cond | " + " | ".join(f"k={k}" for k in range(1, 11)))
    out = {}
    for c in ["C1", "C2", "C3", "C4"]:
        cs = by_cond.get(c, [])
        row = []
        for k in range(1, 11):
            elig = [(N, S) for (N, S) in cs if N >= 1]
            vals = [bok_hyper(N, S, min(k, N)) for (N, S) in elig]
            row.append(sum(vals) / len(vals) if vals else float("nan"))
        out[c] = row
        print(f"{c}  | " + " | ".join(f"{100*x:.0f}" for x in row))
    return out


# ---------- T6: retrieval recall@k ----------
def recall_at_k(rows, ks=(1, 3, 5, 10)):
    ranks = [r.get("gold_seg_rank") for r in rows if r.get("gold_seg_rank") is not None]
    n = len(ranks)
    return n, {k: (sum(1 for gr in ranks if gr < k) / n if n else float("nan")) for k in ks}


def t6():
    print("\n=== T6 检索 recall@k（gold 段落被检回的比例）===")
    for name, path in [("BM25", "runs/raw/ext_bm25/bm25.jsonl"), ("dense", "runs/raw/ext_dense/dense.jsonl")]:
        rows = load(ROOT / path)
        n, rc = recall_at_k(rows)
        print(f"{name} (n={n}): " + " ".join(f"r@{k}={100*v:.0f}%" for k, v in rc.items()))


# ---------- T5: Chinese grid ----------
def t5():
    rows = load(ROOT / "runs/raw/ext_zh_e1/zh_e1.jsonl")
    print("\n=== T5 中文 C1/C3 网格（描述性；每格 k0/final strict, n）===")
    agg = collections.defaultdict(lambda: [0, 0, 0, 0])  # (work,cond,model) -> [n, k0_sum, final_sum, _]
    for r in rows:
        key = (r["work_id"], r["condition"], r["model"])
        a = agg[key]; a[0] += 1; a[1] += int(bool(r["k0_strict"])); a[2] += int(bool(r["final_strict"]))
    for (w, c, m), (n, k0, fin, _) in sorted(agg.items()):
        print(f"{w:10} {c} {m}: n={n}  k0={100*k0/n:.0f}%  final={100*fin/n:.0f}%")


# ---------- T8: four-arm dose by condition ----------
def t8():
    print("\n=== T8 四臂×条件 修复率（k0 失败组内, confirmatory）===")
    for tag, path in [("M2 chat", "runs/raw/ext_e1b_m2"), ("M4 reasoner", "runs/raw/ext_e1b_m4")]:
        files = list((ROOT / path).glob("*.jsonl"))
        rows = []
        for f in files:
            rows += load(f)
        # 仅 confirmatory、k0 失败
        rows = [r for r in rows if r["task_id"].split("_")[0] not in DEV and not r.get("k0_strict")]
        by = collections.defaultdict(lambda: [0, 0])  # (arm,cond)->[n,fixed]
        for r in rows:
            arm = r.get("arm"); c = r.get("condition")
            if arm == "resample":
                # 盲重采样=best-of-k：三次独立重抽任一通过即算修复（非最后一轮）
                fixed = any(bool(rd.get("judge", {}).get("strict_correct")) for rd in r.get("rounds", [])[1:])
            else:
                # 定向反馈迭代式：以最后一轮为准
                fixed = bool(r.get("final_strict"))
            by[(arm, c)][0] += 1; by[(arm, c)][1] += int(fixed)
        arms = sorted({a for (a, _) in by})
        conds = ["C1", "C2", "C3", "C4"]
        print(f"-- {tag} --  " + "  ".join(f"{a}" for a in arms))
        for c in conds:
            cells = []
            for a in arms:
                n, fx = by.get((a, c), [0, 0])
                cells.append(f"{100*fx/n:.0f}%(n={n})" if n else "—")
            print(f"  {c}: " + "  ".join(cells))
        # 池化各臂
        pool = collections.defaultdict(lambda: [0, 0])
        for (a, c), (n, fx) in by.items():
            pool[a][0] += n; pool[a][1] += fx
        print("  池化: " + "  ".join(f"{a}={100*pool[a][1]/pool[a][0]:.0f}%(n={pool[a][0]})" for a in arms if pool[a][0]))


if __name__ == "__main__":
    f5(); t6(); t5(); t8()
