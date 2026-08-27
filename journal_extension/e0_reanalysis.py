"""E0 零成本重分析（只读冻结日志，0 次 API 调用）。

产出（journal_extension/analysis_ext/e0/）：
1. best_of_k.csv / .md      —— 重采样基线：边际 best-of-k 与"失败后重试 k 次"两种口径，
                               经验超几何（有限池，主口径）与几何独立近似（部署口径）并报。
2. position_analysis.csv    —— 目标句在源窗口中的位置分布（观察性；窗口按 ±900 构造，
                               预期大部分居中，仅边界截断产生变异——若退化则受控操纵才有意义）。
3. failure_pool.csv         —— 错误类别 × 条件 × 模型 失败池盘点（修复实验样本量地图）。
4. failure_manifest.jsonl   —— 全部失败样本清单（修复实验直接消费）。
5. failure_manifest_dev.jsonl —— dev 任务（TGU2/TGU4）子集，smoke test 输入。
6. e0_summary.md            —— 汇总解读。
"""
from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "runs" / "raw" / "formal" / "formal.jsonl"
TASK_DIR = ROOT / "tasks"
OUT = Path(__file__).resolve().parent / "analysis_ext" / "e0"
OUT.mkdir(parents=True, exist_ok=True)

DEV_TGUS = {"TGU2", "TGU4"}  # dev 集：Macbeth + A Tale of Two Cities（预注册划分）
K_MAX = 4


def load_rows() -> list[dict]:
    rows = [json.loads(l) for l in LOG.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(rows) == 2160, f"frozen log expected 2160, got {len(rows)}"
    return rows


def comb(n: int, k: int) -> int:
    return math.comb(n, k) if 0 <= k <= n else 0


def best_of_k(rows: list[dict]) -> None:
    """按 cell（model×condition×task，各 10 重复）估计重采样基线。"""
    cells: dict[tuple, list[bool]] = defaultdict(list)
    for r in rows:
        cells[(r["model"], r["condition"], r["task_id"])].append(
            bool(r["judge"].get("strict_correct"))
        )
    for key, v in cells.items():
        assert len(v) == 10, f"cell {key} has {len(v)} reps"

    lines = ["k,scheme,condition,rate"]
    md = ["# E0 best-of-k 重采样基线（零调用，冻结日志推得）", ""]
    md.append("| 口径 | 条件 | k=1(基线) | k=2 | k=3 | k=4 |")
    md.append("|---|---|---|---|---|---|")

    for scheme in ("hypergeometric", "geometric"):
        cond_rates: dict[str, list[float]] = defaultdict(lambda: defaultdict(list))
        for (model, cond, task), outcomes in cells.items():
            s = sum(outcomes)  # 10 次中的成功数
            for k in range(1, K_MAX + 1):
                if scheme == "hypergeometric":
                    # 从该 cell 的 10 次真实结果中不放回抽 k 次，至少一次成功的概率
                    p_k = 1.0 - comb(10 - s, k) / comb(10, k)
                else:
                    # 独立重抽近似（部署口径）
                    p = s / 10.0
                    p_k = 1.0 - (1.0 - p) ** k
                cond_rates[cond][k].append(p_k)
        for cond in ("C1", "C2", "C3", "C4"):
            vals = [sum(cond_rates[cond][k]) / len(cond_rates[cond][k]) for k in range(1, K_MAX + 1)]
            for k, v in zip(range(1, K_MAX + 1), vals):
                lines.append(f"{k},{scheme},{cond},{v:.4f}")
            md.append(
                f"| {scheme} | {cond} | " + " | ".join(f"{v:.3f}" for v in vals) + " |"
            )

    (OUT / "best_of_k.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    md += [
        "",
        "口径说明：hypergeometric=从 cell 的 10 次真实结果不放回抽 k（有限样本、主口径）；",
        "geometric=独立重抽 1-(1-p)^k（部署口径）。k=1 即冻结基线率。",
        "**闭环修复的对照线**：修复预算 k 轮对应此处 k+1 次抽样的 best-of-(k+1) 曲线。",
    ]
    (OUT / "best_of_k.md").write_text("\n".join(md) + "\n", encoding="utf-8")


def position_analysis() -> list[str]:
    """目标句在 source_window 中的位置分数（0=窗口开头，1=结尾）。"""
    rows_out = ["task_id,evidence_idx,pos_fraction,window_len,found"]
    fractions = []
    for path in sorted(TASK_DIR.glob("TGU*_T*.yaml")):
        task = yaml.safe_load(path.read_text(encoding="utf-8"))
        for i, ev in enumerate(task.get("expected_evidence", [])):
            window = ev.get("source_window") or ""
            quote = (ev.get("quote") or "")[:60]
            idx = window.find(quote)
            if idx < 0 or len(window) <= len(quote):
                rows_out.append(f"{task['task_id']},{i},,{len(window)},0")
                continue
            frac = idx / max(1, len(window) - len(quote))
            fractions.append(frac)
            rows_out.append(f"{task['task_id']},{i},{frac:.3f},{len(window)},1")
    (OUT / "position_analysis.csv").write_text("\n".join(rows_out) + "\n", encoding="utf-8")
    notes = []
    if fractions:
        lo = sum(1 for f in fractions if f < 0.33)
        mid = sum(1 for f in fractions if 0.33 <= f <= 0.67)
        hi = sum(1 for f in fractions if f > 0.67)
        notes.append(
            f"句位分布：前 1/3 = {lo}，中 1/3 = {mid}，后 1/3 = {hi}（n={len(fractions)}）。"
        )
        if mid >= 0.7 * len(fractions):
            notes.append(
                "**结论：窗口按 ±900 对称构造，句位近乎退化于中部——观察性句位分析无信息量；"
                "若要句位效应必须受控操纵（按预注册默认砍，除非后续有强理由）。**"
            )
    return notes


def failure_pool(rows: list[dict]) -> list[str]:
    """错误类别 × 条件 × 模型的失败池盘点 + 修复清单落盘。"""
    pool = Counter()
    manifest, manifest_dev = [], []
    for r in rows:
        j = r["judge"]
        if j.get("strict_correct"):
            continue
        err = j.get("error_class_candidate") or "unknown"
        pool[(r["condition"], r["model"], err)] += 1
        item = {
            "run_id": r["run_id"],
            "task_id": r["task_id"],
            "condition": r["condition"],
            "model": r["model"],
            "variant": r.get("variant"),
            "repetition": r.get("repetition"),
            "error_class_k0": err,
            "bucket_k0": j.get("bucket"),
        }
        manifest.append(item)
        if r["task_id"].split("_")[0] in DEV_TGUS:
            manifest_dev.append(item)

    lines = ["condition,model,error_class,n"]
    for (cond, model, err), n in sorted(pool.items()):
        lines.append(f"{cond},{model},{err},{n}")
    (OUT / "failure_pool.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")

    with (OUT / "failure_manifest.jsonl").open("w", encoding="utf-8") as f:
        for it in manifest:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    with (OUT / "failure_manifest_dev.jsonl").open("w", encoding="utf-8") as f:
        for it in manifest_dev:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")

    # 关键格子的样本量提示
    notes = [f"失败总数 {len(manifest)}；dev(TGU2/TGU4) 失败 {len(manifest_dev)}。"]
    for cond in ("C1", "C2", "C3", "C4"):
        fab = sum(n for (c, _m, e), n in pool.items() if c == cond and e == "fabricated_quotation")
        loc = sum(n for (c, _m, e), n in pool.items() if c == cond and e == "context_displacement")
        notes.append(f"{cond}: fabrication 池={fab}，context_displacement 池={loc}。")
    return notes


def main() -> None:
    rows = load_rows()
    best_of_k(rows)
    pos_notes = position_analysis()
    pool_notes = failure_pool(rows)

    summary = ["# E0 汇总（零调用）", ""]
    summary += ["## 句位观察分析"] + [f"- {n}" for n in pos_notes] + [""]
    summary += ["## 失败池盘点"] + [f"- {n}" for n in pool_notes] + [""]
    summary += [
        "## best-of-k",
        "- 见 best_of_k.md；闭环修复必须战胜其中 hypergeometric 口径的对应曲线才有'定向反馈净价值'。",
    ]
    (OUT / "e0_summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
    print("E0 done ->", OUT)
    for n in pos_notes + pool_notes:
        print(" *", n)


if __name__ == "__main__":
    main()
