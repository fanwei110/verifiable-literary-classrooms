"""R1.7 实验的无网络单元测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from experiment_core import (
    assert_no_truth_leak,
    build_prompt,
    deepseek_cost_usd,
    parse_json_object,
    prompt_shell,
    read_jsonl,
    validate_verdict,
)
from run_experiment import (
    DeepSeekBudget,
    codex_command,
    deepseek_body,
    parse_codex_events,
)


CLAIM = {
    "quote": "A test quotation.",
    "author": "Author",
    "work": "Work",
    "locator": "Chapter 1",
    "speaker": "Narrator",
}


def test_conditions_change_only_evidence_block() -> None:
    """同一题的三条件只能改变证据块。"""
    closed = build_prompt(CLAIM, "[No reference excerpts supplied.]")
    rag = build_prompt(CLAIM, "[Reference excerpt 1]\nRetrieved text")
    gold = build_prompt(CLAIM, "[Reference excerpt 1]\nFrozen reference text")
    assert prompt_shell(closed) == prompt_shell(rag) == prompt_shell(gold)


def test_truth_leak_is_rejected() -> None:
    """隐藏错误类别不得进入模型提示。"""
    with pytest.raises(ValueError):
        assert_no_truth_leak("label=fabricated_quotation")


def test_verdict_parser_and_validation() -> None:
    """围栏 JSON 可解析，但多余字段和自由文本会失败。"""
    valid = parse_json_object(
        '```json\n{"verdict":"unsure","confidence":0.4,'
        '"rationale":"Insufficient evidence.","cited_evidence":[]}\n```'
    )
    assert validate_verdict(valid)["verdict"] == "unsure"
    with pytest.raises(ValueError):
        parse_json_object("not json")
    valid["extra"] = True
    with pytest.raises(ValueError):
        validate_verdict(valid)


def test_deepseek_body_uses_supported_thinking_parameters() -> None:
    """thinking mode 请求不得混入无效采样参数。"""
    body = deepseek_body("prompt")
    assert body["model"] == "deepseek-v4-pro"
    assert body["thinking"] == {"type": "enabled"}
    assert body["reasoning_effort"] == "high"
    assert body["max_tokens"] == 65536
    assert body["response_format"] == {"type": "json_object"}
    for unsupported in (
        "temperature",
        "top_p",
        "presence_penalty",
        "frequency_penalty",
    ):
        assert unsupported not in body


def test_codex_command_disables_skills_and_tools() -> None:
    """Codex 隔离必须显式移除 skills catalogue 并关闭工具能力。"""
    command = codex_command(r"C:\tools\codex.exe")
    joined = " ".join(command)
    assert "skills.include_instructions=false" in command
    assert "skills.bundled.enabled=false" in command
    for feature in (
        "shell_tool",
        "apps",
        "browser_use",
        "computer_use",
        "plugins",
        "workspace_dependencies",
    ):
        assert f"--disable {feature}" in joined
    assert "--ephemeral" in command
    assert "--ignore-user-config" in command
    assert command[command.index("--sandbox") + 1] == "read-only"


def test_deepseek_cost_peak_and_offpeak() -> None:
    """费用按缓存命中、未命中与输出分项并区分峰谷。"""
    usage = {
        "prompt_tokens": 3000,
        "prompt_cache_hit_tokens": 1000,
        "prompt_cache_miss_tokens": 2000,
        "completion_tokens": 500,
    }
    offpeak = deepseek_cost_usd(usage, "2026-08-23T12:00:00Z")
    peak = deepseek_cost_usd(usage, "2026-08-24T02:00:00Z")
    expected_offpeak = (1000 * 0.022 + 2000 * 0.66 + 500 * 1.98) / 1_000_000
    expected_peak = (1000 * 0.044 + 2000 * 1.32 + 500 * 3.96) / 1_000_000
    assert offpeak == pytest.approx(expected_offpeak)
    assert peak == pytest.approx(expected_peak)


def test_budget_resume_reads_prior_attempts() -> None:
    """续跑预算必须包含既有尝试，不能因重启归零。"""
    attempts = Path(__file__).with_name("_budget_attempts.jsonl")
    try:
        attempts.write_text(
            json.dumps({"cost_usd_peak": 4.74, "cost_usd_tariff": 2.37}) + "\n",
            encoding="utf-8",
        )
        budget = DeepSeekBudget(5.0, [attempts])
        assert budget.snapshot()["spent_peak_usd"] == pytest.approx(4.74)
        assert not budget.reserve()
    finally:
        attempts.unlink(missing_ok=True)


def test_codex_event_parser_detects_tools() -> None:
    """任何命令事件都会使 GPT 结果失效。"""
    lines = [
        {"type": "item.completed", "item": {"type": "command_execution"}},
        {
            "type": "item.completed",
            "item": {
                "type": "agent_message",
                "text": json.dumps(
                    {
                        "verdict": "accurate",
                        "confidence": 0.8,
                        "rationale": "Supported.",
                        "cited_evidence": [],
                    }
                ),
            },
        },
        {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 5}},
    ]
    events, final_text, usage, tool_used = parse_codex_events(
        "\n".join(json.dumps(line) for line in lines)
    )
    assert len(events) == 3
    assert parse_json_object(final_text)["verdict"] == "accurate"
    assert usage["input_tokens"] == 10
    assert tool_used


def test_frozen_manifest_integrity() -> None:
    """冻结清单必须为 60×3，且同题三条件只改变证据块。"""
    manifest_path = (
        Path(__file__).resolve().parents[1] / "inputs" / "prompts_manifest.jsonl"
    )
    rows = read_jsonl(manifest_path)
    assert len(rows) == 180
    assert len({(row["item_id"], row["condition"]) for row in rows}) == 180
    assert {row["condition"] for row in rows} == {
        "closed",
        "rag_top3",
        "gold_reference",
    }
    by_item: dict[str, list[dict]] = {}
    for row in rows:
        assert_no_truth_leak(row["prompt"])
        by_item.setdefault(row["item_id"], []).append(row)
    assert len(by_item) == 60
    for item_rows in by_item.values():
        assert len(item_rows) == 3
        assert len({prompt_shell(row["prompt"]) for row in item_rows}) == 1
