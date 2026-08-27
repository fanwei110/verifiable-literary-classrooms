"""分析 R1.7 双模型三条件结果并生成可直接进入返修材料的表格。"""

from __future__ import annotations

import csv
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from scipy.stats import binomtest

from experiment_core import CONDITIONS, read_jsonl, validate_verdict


BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
PUBLIC_KEY = ROOT / "journal_extension" / "llm_judge_foil" / "foil_key.csv"
MANIFEST = BASE / "inputs" / "prompts_manifest.jsonl"
ANALYSIS = BASE / "analysis"
MODEL_FILES = {
    "gpt-5.6-sol (Codex subscription)": BASE / "raw" / "gpt_results.jsonl",
    "deepseek-v4-pro": BASE / "raw" / "deepseek_results.jsonl",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    """读取研究 CSV。"""
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    """写出 Excel 友好的 UTF-8 BOM CSV。"""
    if not rows:
        raise ValueError(f"拒绝写出空表：{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def wilson(
    successes: int, total: int, z: float = 1.959963984540054
) -> tuple[float, float]:
    """计算二项比例的 Wilson 95% 区间。"""
    if total <= 0:
        return math.nan, math.nan
    proportion = successes / total
    denominator = 1 + z * z / total
    center = (proportion + z * z / (2 * total)) / denominator
    half = (
        z
        * math.sqrt(proportion * (1 - proportion) / total + z * z / (4 * total * total))
        / denominator
    )
    return max(0.0, center - half), min(1.0, center + half)


def holm_adjust(p_values: Iterable[float]) -> list[float]:
    """对同一模型的三组配对比较实施 Holm 校正。"""
    values = list(p_values)
    order = sorted(range(len(values)), key=values.__getitem__)
    adjusted = [0.0] * len(values)
    running = 0.0
    count = len(values)
    for rank, index in enumerate(order):
        candidate = min(1.0, (count - rank) * values[index])
        running = max(running, candidate)
        adjusted[index] = running
    return adjusted


def load_scored() -> list[dict[str, Any]]:
    """合并两模型结果、真值与检索审计字段，并拒绝缺样本或重复。"""
    key_rows = {row["item_id"]: row for row in read_csv(PUBLIC_KEY)}
    manifest_rows = {
        (row["item_id"], row["condition"]): row for row in read_jsonl(MANIFEST)
    }
    scored: list[dict[str, Any]] = []
    for model_label, path in MODEL_FILES.items():
        results = [row for row in read_jsonl(path) if row.get("status") == "success"]
        pairs = {(row["item_id"], row["condition"]) for row in results}
        if len(results) != 180 or len(pairs) != 180:
            raise ValueError(
                f"{model_label} 必须恰有 180 条唯一成功结果，实际 {len(results)}/{len(pairs)}"
            )
        for row in results:
            response = validate_verdict(row["response"])
            truth = key_rows[row["item_id"]]
            is_correct = truth["auto_strict"].strip().lower() == "true"
            error_class = truth["auto_error_class"].strip() or "correct"
            expected = "accurate" if is_correct else "inaccurate"
            prompt_row = manifest_rows[(row["item_id"], row["condition"])]
            scored.append(
                {
                    "model": model_label,
                    "item_id": row["item_id"],
                    "condition": row["condition"],
                    "is_correct_control": is_correct,
                    "error_class": error_class,
                    "expected_verdict": expected,
                    "verdict": response["verdict"],
                    "confidence": response["confidence"],
                    "strict_classification_correct": response["verdict"] == expected,
                    "rationale": response["rationale"],
                    "cited_evidence_json": json.dumps(
                        response["cited_evidence"], ensure_ascii=False
                    ),
                    "prompt_sha256": row["prompt_sha256"],
                    "claim_exact_hit_at_3": prompt_row.get("claim_exact_hit_at_3", ""),
                    "task_gold_hit_at_3": prompt_row.get("task_gold_hit_at_3", ""),
                    "diagnostic_hit_at_3": prompt_row.get("diagnostic_hit_at_3", ""),
                }
            )
    if len(scored) != 360:
        raise ValueError(f"合并结果应为 360 条，实际 {len(scored)}")
    return scored


def group_rows(scored: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """生成总体、控制、错误总体及四错误类别的比例表。"""
    output: list[dict[str, Any]] = []
    groups = [
        ("all", lambda row: True),
        ("correct_controls", lambda row: row["is_correct_control"]),
        ("all_errors", lambda row: not row["is_correct_control"]),
        (
            "fabricated_quotation",
            lambda row: row["error_class"] == "fabricated_quotation",
        ),
        ("misattribution", lambda row: row["error_class"] == "misattribution"),
        ("version_drift", lambda row: row["error_class"] == "version_drift"),
        (
            "context_displacement",
            lambda row: row["error_class"] == "context_displacement",
        ),
    ]
    for model in MODEL_FILES:
        for condition in CONDITIONS:
            base_rows = [
                row
                for row in scored
                if row["model"] == model and row["condition"] == condition
            ]
            for group_name, predicate in groups:
                rows = [row for row in base_rows if predicate(row)]
                n = len(rows)
                verdicts = Counter(row["verdict"] for row in rows)
                successes = sum(
                    bool(row["strict_classification_correct"]) for row in rows
                )
                low, high = wilson(successes, n)
                non_unsure = n - verdicts["unsure"]
                if group_name == "correct_controls":
                    primary_metric = "correct_acceptance_rate"
                elif group_name == "all":
                    primary_metric = "strict_accuracy"
                else:
                    primary_metric = "error_detection_rate"
                output.append(
                    {
                        "model": model,
                        "condition": condition,
                        "group": group_name,
                        "n": n,
                        "primary_metric": primary_metric,
                        "primary_successes": successes,
                        "primary_rate": successes / n,
                        "wilson_95_low": low,
                        "wilson_95_high": high,
                        "accurate_rate": verdicts["accurate"] / n,
                        "inaccurate_rate": verdicts["inaccurate"] / n,
                        "unsure_rate": verdicts["unsure"] / n,
                        "strict_accuracy_excluding_unsure": (
                            successes / non_unsure if non_unsure else math.nan
                        ),
                    }
                )
    return output


def mcnemar_rows(scored: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """对相同 60 题的条件结果进行 exact McNemar 配对检验。"""
    comparisons = [
        ("closed", "rag_top3"),
        ("rag_top3", "gold_reference"),
        ("closed", "gold_reference"),
    ]
    output: list[dict[str, Any]] = []
    for model in MODEL_FILES:
        lookup = {
            (row["item_id"], row["condition"]): bool(
                row["strict_classification_correct"]
            )
            for row in scored
            if row["model"] == model
        }
        model_rows = []
        for first, second in comparisons:
            first_only = sum(
                lookup[(item_id, first)] and not lookup[(item_id, second)]
                for item_id in sorted({row["item_id"] for row in scored})
            )
            second_only = sum(
                not lookup[(item_id, first)] and lookup[(item_id, second)]
                for item_id in sorted({row["item_id"] for row in scored})
            )
            discordant = first_only + second_only
            p_value = (
                binomtest(min(first_only, second_only), discordant, 0.5).pvalue
                if discordant
                else 1.0
            )
            model_rows.append(
                {
                    "model": model,
                    "condition_a": first,
                    "condition_b": second,
                    "a_correct_b_wrong": first_only,
                    "a_wrong_b_correct": second_only,
                    "discordant_pairs": discordant,
                    "mcnemar_exact_p": p_value,
                }
            )
        adjusted = holm_adjust(row["mcnemar_exact_p"] for row in model_rows)
        for row, adjusted_p in zip(model_rows, adjusted):
            row["holm_adjusted_p"] = adjusted_p
            output.append(row)
    return output


def retrieval_rows(scored: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按三种命中定义报告 RAG 命中与未命中的判别表现。"""
    output: list[dict[str, Any]] = []
    rag = [row for row in scored if row["condition"] == "rag_top3"]
    for model in MODEL_FILES:
        model_rows = [row for row in rag if row["model"] == model]
        for flag in (
            "claim_exact_hit_at_3",
            "task_gold_hit_at_3",
            "diagnostic_hit_at_3",
        ):
            for hit in (True, False):
                rows = [row for row in model_rows if row[flag] is hit]
                n = len(rows)
                successes = sum(
                    bool(row["strict_classification_correct"]) for row in rows
                )
                low, high = wilson(successes, n)
                output.append(
                    {
                        "model": model,
                        "hit_definition": flag,
                        "hit": hit,
                        "n": n,
                        "strict_successes": successes,
                        "strict_accuracy": successes / n if n else math.nan,
                        "wilson_95_low": low,
                        "wilson_95_high": high,
                    }
                )
    return output


def fmt_rate(value: float) -> str:
    """以百分比呈现，保留一位小数。"""
    return f"{100 * value:.1f}%"


def fmt_rate_ci(row: dict[str, Any]) -> str:
    """把主比例及 Wilson 95% 区间压缩为表格单元。"""
    return (
        f"{fmt_rate(row['primary_rate'])} "
        f"[{fmt_rate(row['wilson_95_low'])}, {fmt_rate(row['wilson_95_high'])}]"
    )


def write_summary(
    metrics: list[dict[str, Any]],
    mcnemar: list[dict[str, Any]],
    retrieval: list[dict[str, Any]],
    scored: list[dict[str, Any]],
) -> None:
    """生成面向正文和回复函的无夸大结果摘要。"""
    lines = [
        "# R1.7 双模型开放式评判结果",
        "",
        "严格主指标把 `unsure` 计为未正确分类；模型输出为一次性冻结记录，不主张可逐字复现。",
        "",
        "## 总体严格准确率",
        "",
        "| 模型 | Closed | RAG top-3 | Gold reference |",
        "|---|---:|---:|---:|",
    ]
    for model in MODEL_FILES:
        rates = {}
        for condition in CONDITIONS:
            row = next(
                item
                for item in metrics
                if item["model"] == model
                and item["condition"] == condition
                and item["group"] == "all"
            )
            rates[condition] = fmt_rate_ci(row)
        lines.append(
            f"| {model} | {rates['closed']} | {rates['rag_top3']} | {rates['gold_reference']} |"
        )
    lines += ["", "## 排除 unsure 的敏感性分析", ""]
    lines += [
        "| 模型 | Closed | RAG top-3 | Gold reference |",
        "|---|---:|---:|---:|",
    ]
    for model in MODEL_FILES:
        rates = {}
        for condition in CONDITIONS:
            row = next(
                item
                for item in metrics
                if item["model"] == model
                and item["condition"] == condition
                and item["group"] == "all"
            )
            rates[condition] = fmt_rate(row["strict_accuracy_excluding_unsure"])
        lines.append(
            f"| {model} | {rates['closed']} | {rates['rag_top3']} | {rates['gold_reference']} |"
        )
    lines += ["", "## 错误接受率与正确接受率", ""]
    lines += [
        "| 模型 | 条件 | 错误接受率（错误题判 accurate） | 正确接受率 | Unsure（全部） |",
        "|---|---|---:|---:|---:|",
    ]
    for model in MODEL_FILES:
        for condition in CONDITIONS:
            errors = next(
                item
                for item in metrics
                if item["model"] == model
                and item["condition"] == condition
                and item["group"] == "all_errors"
            )
            controls = next(
                item
                for item in metrics
                if item["model"] == model
                and item["condition"] == condition
                and item["group"] == "correct_controls"
            )
            overall = next(
                item
                for item in metrics
                if item["model"] == model
                and item["condition"] == condition
                and item["group"] == "all"
            )
            lines.append(
                f"| {model} | {condition} | {fmt_rate(errors['accurate_rate'])} | "
                f"{fmt_rate(controls['accurate_rate'])} | {fmt_rate(overall['unsure_rate'])} |"
            )
    lines += ["", "## 配对比较", ""]
    for row in mcnemar:
        lines.append(
            f"- {row['model']}: {row['condition_a']} vs. {row['condition_b']}, "
            f"discordant={row['discordant_pairs']}, exact p={row['mcnemar_exact_p']:.4g}, "
            f"Holm-adjusted p={row['holm_adjusted_p']:.4g}."
        )
    lines += ["", "## RAG top-3 命中与未命中", ""]
    lines += [
        "| 模型 | 命中定义 | 命中 n / 严格准确率 | 未命中 n / 严格准确率 |",
        "|---|---|---:|---:|",
    ]
    for model in MODEL_FILES:
        for flag in (
            "claim_exact_hit_at_3",
            "task_gold_hit_at_3",
            "diagnostic_hit_at_3",
        ):
            hit = next(
                row
                for row in retrieval
                if row["model"] == model
                and row["hit_definition"] == flag
                and row["hit"] is True
            )
            miss = next(
                row
                for row in retrieval
                if row["model"] == model
                and row["hit_definition"] == flag
                and row["hit"] is False
            )
            lines.append(
                f"| {model} | {flag} | {hit['n']} / {fmt_rate(hit['strict_accuracy'])} | "
                f"{miss['n']} / {fmt_rate(miss['strict_accuracy'])} |"
            )
    lines += [
        "",
        "## 解释边界",
        "",
        "- 这些比较评估的是冻结的 60 题分层样本，不代表开放域文学事实核验的总体性能。",
        "- GPT 结果来自 Codex CLI/ChatGPT 订阅环境，不能表述为 OpenAI API 实验。",
        "- 确定性验证器的核心优势应表述为语料成员关系的确定性、可审计性与无需模型调用，而不是预设对任意 LLM 的绝对性能优势。",
        "",
        f"完整题项级结果共 {len(scored)} 条，见 `item_level_scored.csv`。",
    ]
    (ANALYSIS / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    """完成全部预注册统计并写出表格。"""
    ANALYSIS.mkdir(parents=True, exist_ok=True)
    scored = load_scored()
    metrics = group_rows(scored)
    mcnemar = mcnemar_rows(scored)
    retrieval = retrieval_rows(scored)
    write_csv(ANALYSIS / "item_level_scored.csv", scored)
    write_csv(ANALYSIS / "metrics.csv", metrics)
    write_csv(ANALYSIS / "mcnemar.csv", mcnemar)
    write_csv(ANALYSIS / "retrieval_mediation.csv", retrieval)
    write_summary(metrics, mcnemar, retrieval, scored)
    print("统计完成：360 条题项级结果")
    print(f"输出目录：{ANALYSIS}")


if __name__ == "__main__":
    main()
