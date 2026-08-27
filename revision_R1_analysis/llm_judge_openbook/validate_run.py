"""验收 R1.7 正式运行的完整性、隔离性与预算约束。"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from experiment_core import CONDITIONS, read_jsonl, validate_verdict


BASE = Path(__file__).resolve().parent
MANIFEST = BASE / "inputs" / "prompts_manifest.jsonl"
GPT_RESULTS = BASE / "raw" / "gpt_results.jsonl"
GPT_ATTEMPTS = BASE / "raw" / "gpt_attempts.jsonl"
DEEPSEEK_RESULTS = BASE / "raw" / "deepseek_results.jsonl"
DEEPSEEK_ATTEMPTS = [
    BASE / "raw" / "deepseek_attempts.jsonl",
    BASE / "smoke" / "deepseek_attempts.jsonl",
]
REPORT_JSON = BASE / "analysis" / "acceptance_report.json"
REPORT_MD = BASE / "analysis" / "acceptance_report.md"
TOOL_TYPES = {
    "command_execution",
    "file_change",
    "mcp_tool_call",
    "web_search",
    "image_generation",
    "computer_use",
    "collaboration_tool_call",
}


def require(condition: bool, message: str) -> None:
    """在验收条件未满足时立即失败，避免生成带病报告。"""
    if not condition:
        raise ValueError(message)


def load_event_log(relative_path: str) -> list[dict[str, Any]]:
    """读取单题 Codex JSONL 事件，保持对工具事件的原始审计。"""
    path = BASE / Path(relative_path)
    require(path.is_file(), f"缺少 GPT 事件日志：{relative_path}")
    return read_jsonl(path)


def condition_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    """统计三条件样本数，便于直接写入冻结清单。"""
    counts = Counter(str(row["condition"]) for row in rows)
    return {condition: counts[condition] for condition in CONDITIONS}


def audit_results() -> dict[str, Any]:
    """核对正式记录、请求配置、独立会话和累计成本。"""
    manifest = read_jsonl(MANIFEST)
    manifest_lookup = {
        (row["item_id"], row["condition"]): row["prompt_sha256"] for row in manifest
    }
    require(len(manifest) == 180, "冻结提示必须恰有 180 条")
    require(len(manifest_lookup) == 180, "冻结提示存在重复题项—条件键")

    gpt = read_jsonl(GPT_RESULTS)
    deepseek = read_jsonl(DEEPSEEK_RESULTS)
    for label, rows in (("GPT", gpt), ("DeepSeek", deepseek)):
        pairs = {(row["item_id"], row["condition"]) for row in rows}
        require(len(rows) == 180, f"{label} 正式结果不是 180 条")
        require(len(pairs) == 180, f"{label} 正式结果存在重复或遗漏")
        require(pairs == set(manifest_lookup), f"{label} 与冻结提示清单不一致")
        require(
            all(row.get("status") == "success" for row in rows), f"{label} 含非成功记录"
        )
        for row in rows:
            validate_verdict(row["response"])
            pair = (row["item_id"], row["condition"])
            require(
                row["prompt_sha256"] == manifest_lookup[pair],
                f"{label} 提示哈希不一致：{pair}",
            )
        require(
            condition_counts(rows) == {condition: 60 for condition in CONDITIONS},
            f"{label} 条件分布错误",
        )

    thread_ids: list[str] = []
    event_tool_calls = 0
    event_errors = 0
    for row in gpt:
        require(row["provider"] == "codex_cli_subscription", "GPT provider 标识错误")
        require(row["model_id"] == "gpt-5.6-sol", "GPT 模型发生漂移")
        require(
            row["codex_cli_version"] == "codex-cli 0.144.6", "Codex CLI 版本发生漂移"
        )
        require(row["subscription_cost_usd"] is None, "GPT 不得虚构 API 美元成本")
        require(row["tool_used"] is False, "GPT 结果标记发生工具调用")
        events = load_event_log(row["event_log"])
        started = [event for event in events if event.get("type") == "thread.started"]
        require(
            len(started) == 1 and started[0].get("thread_id"), "GPT 独立会话标识异常"
        )
        thread_ids.append(str(started[0]["thread_id"]))
        for event in events:
            item = event.get("item") if isinstance(event.get("item"), dict) else {}
            if item.get("type") in TOOL_TYPES:
                event_tool_calls += 1
            if item.get("type") == "error":
                event_errors += 1
    require(len(set(thread_ids)) == 180, "GPT 的 180 条记录并非 180 个独立会话")
    require(event_tool_calls == 0, "GPT 事件日志中发现工具调用")
    require(event_errors == 0, "GPT 正式事件日志含客户端错误或技能注入提示")
    gpt_usage = {
        key: sum(int(row.get("usage", {}).get(key, 0) or 0) for row in gpt)
        for key in (
            "input_tokens",
            "cached_input_tokens",
            "output_tokens",
            "reasoning_output_tokens",
        )
    }
    gpt_attempts = read_jsonl(GPT_ATTEMPTS)
    subscription_interruptions = sum(
        row.get("status") == "subscription_limit" for row in gpt_attempts
    )

    fingerprints: set[str] = set()
    for row in deepseek:
        require(row["provider"] == "deepseek_api", "DeepSeek provider 标识错误")
        require(row["model_id"] == "deepseek-v4-pro", "DeepSeek 请求模型发生漂移")
        require(row["returned_model"] == "deepseek-v4-pro", "DeepSeek 返回模型发生漂移")
        config = row["request_config"]
        require(config["max_tokens"] == 65536, "DeepSeek 正式批 max_tokens 不统一")
        require(
            config["reasoning_effort"] == "high", "DeepSeek reasoning_effort 不统一"
        )
        require(config["thinking"] == "enabled", "DeepSeek thinking 配置不统一")
        require(config["response_format"] == "json_object", "DeepSeek JSON 配置不统一")
        require(row["finish_reason"] == "stop", "DeepSeek 正式结果不是自然停止")
        fingerprints.add(str(row.get("system_fingerprint") or ""))

    tariff_cost = 0.0
    peak_cost = 0.0
    billed_attempts = 0
    for path in DEEPSEEK_ATTEMPTS:
        if not path.is_file():
            continue
        for row in read_jsonl(path):
            if row.get("cost_usd_tariff") is not None:
                tariff_cost += float(row["cost_usd_tariff"])
                billed_attempts += 1
            if row.get("cost_usd_peak") is not None:
                peak_cost += float(row["cost_usd_peak"])
    require(peak_cost <= 10.0, f"DeepSeek 峰值保守成本超预算：${peak_cost:.6f}")
    deepseek_usage = {
        "prompt_tokens": sum(
            int(row["usage"].get("prompt_tokens", 0) or 0) for row in deepseek
        ),
        "completion_tokens": sum(
            int(row["usage"].get("completion_tokens", 0) or 0) for row in deepseek
        ),
        "reasoning_tokens": sum(
            int(
                row["usage"]
                .get("completion_tokens_details", {})
                .get("reasoning_tokens", 0)
                or 0
            )
            for row in deepseek
        ),
    }

    return {
        "status": "pass",
        "formal_records": len(gpt) + len(deepseek),
        "manifest_records": len(manifest),
        "gpt": {
            "records": len(gpt),
            "condition_counts": condition_counts(gpt),
            "unique_thread_ids": len(set(thread_ids)),
            "tool_calls_in_events": event_tool_calls,
            "error_events": event_errors,
            "model_id": "gpt-5.6-sol",
            "codex_cli_version": "codex-cli 0.144.6",
            "subscription_cost_usd": None,
            "usage": gpt_usage,
            "subscription_limit_interruptions": subscription_interruptions,
        },
        "deepseek": {
            "records": len(deepseek),
            "condition_counts": condition_counts(deepseek),
            "model_id": "deepseek-v4-pro",
            "max_tokens": 65536,
            "system_fingerprints": sorted(fingerprints),
            "billed_attempts_including_smoke_and_aborted": billed_attempts,
            "cost_usd_tariff": tariff_cost,
            "cost_usd_peak_conservative": peak_cost,
            "budget_usd": 10.0,
            "formal_usage": deepseek_usage,
        },
    }


def write_report(report: dict[str, Any]) -> None:
    """同时写出机器可读 JSON 与便于审阅的 Markdown。"""
    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    deepseek = report["deepseek"]
    lines = [
        "# R1.7 正式运行验收报告",
        "",
        "**结论：PASS。**",
        "",
        f"- 正式记录：{report['formal_records']}（GPT 180 + DeepSeek 180）。",
        "- 每个模型三条件均为 60 条，且与冻结提示键和提示哈希逐项一致。",
        "- GPT：180 个独立 Codex 临时会话；事件日志工具调用为 0；不报告虚构 API 美元费用。",
        f"- DeepSeek：正式批统一 max_tokens={deepseek['max_tokens']}；实际费率成本 ${deepseek['cost_usd_tariff']:.6f}；峰值保守账本 ${deepseek['cost_usd_peak_conservative']:.6f}/$10。",
        f"- DeepSeek 系统指纹：{', '.join(deepseek['system_fingerprints']) or 'not returned'}。",
        "",
        "验收范围包括 JSON 可解析性、唯一性、提示哈希、模型/客户端标识、GPT 独立会话与工具事件、DeepSeek 请求配置和含归档尝试的成本账本。密钥扫描由 `security_scan.py` 单独执行。",
    ]
    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    """执行全部验收并写出报告。"""
    report = audit_results()
    write_report(report)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
