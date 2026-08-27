"""R1.7 双模型开放式引文评判实验的共享组件。

本模块只处理冻结提示、结构化输出与成本核算；绝不读取 API 密钥。
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable


CONDITIONS = ("closed", "rag_top3", "gold_reference")
MODELS = ("gpt_subscription", "deepseek_v4_pro")
VERDICTS = {"accurate", "inaccurate", "unsure"}
TRUTH_LEAK_TOKENS = (
    "fabricated_quotation",
    "misattribution",
    "version_drift",
    "context_displacement",
    "auto_strict",
    "auto_error_class",
    "auto_severity_tier",
)

VERDICT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "verdict": {
            "type": "string",
            "enum": ["accurate", "inaccurate", "unsure"],
        },
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "rationale": {"type": "string", "minLength": 1, "maxLength": 800},
        "cited_evidence": {
            "type": "array",
            "items": {"type": "string", "maxLength": 500},
            "maxItems": 3,
        },
    },
    "required": ["verdict", "confidence", "rationale", "cited_evidence"],
    "additionalProperties": False,
}

PROMPT_PREFIX = """You are an automated verifier of literary quotations.

Evaluate whether the claimed quotation is verbatim in the stated edition and whether its author, work, locator, and speaker or narrator are correctly attributed. A claim is accurate only if all material elements are supported. If the supplied information is insufficient for a reliable decision, answer unsure.

Do not use tools, web search, local files, external retrieval, or unstated evidence. Use only your internal model knowledge and the reference excerpts explicitly included below. The excerpts may support, contradict, or be irrelevant to the claim.

Claimed quotation: {quote}
Claimed author: {author}
Claimed work: {work}
Claimed locator: {locator}
Claimed speaker or narrator: {speaker}

<REFERENCE_EXCERPTS>
{evidence_block}
</REFERENCE_EXCERPTS>

Return only one JSON object with exactly these fields:
{{
  "verdict": "accurate" | "inaccurate" | "unsure",
  "confidence": <number from 0.0 to 1.0>,
  "rationale": "<one concise sentence>",
  "cited_evidence": ["<up to three short supporting or contradicting excerpts; use an empty array when none is available>"]
}}
"""


def sha256_text(text: str) -> str:
    """返回 UTF-8 文本的 SHA-256，用于冻结请求而非安全存储密钥。"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    """流式计算文件哈希，避免把大语料整体复制到内存。"""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json(data: Any) -> str:
    """生成稳定 JSON，确保相同请求拥有相同哈希。"""
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """读取 JSONL；空行被忽略，损坏行立即报错以防静默跳样本。"""
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path} 第 {line_number} 行不是有效 JSON") from exc
    return rows


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    """追加单条 UTF-8 JSONL；调用方负责并发锁。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()


def build_prompt(claim: dict[str, str], evidence_block: str) -> str:
    """构建模型共用提示，模型与条件差异不得进入基础指令。"""
    prompt = PROMPT_PREFIX.format(
        quote=claim["quote"],
        author=claim["author"],
        work=claim["work"],
        locator=claim["locator"],
        speaker=claim["speaker"],
        evidence_block=evidence_block,
    )
    assert_no_truth_leak(prompt)
    return prompt


def prompt_shell(prompt: str) -> str:
    """移除条件证据，用于证明同一题三条件只改变证据块。"""
    return re.sub(
        r"<REFERENCE_EXCERPTS>.*?</REFERENCE_EXCERPTS>",
        "<REFERENCE_EXCERPTS>__CONDITION_EVIDENCE__</REFERENCE_EXCERPTS>",
        prompt,
        flags=re.DOTALL,
    )


def assert_no_truth_leak(prompt: str) -> None:
    """阻止隐藏真值字段或错误类别进入模型提示。"""
    lowered = prompt.lower()
    leaked = [token for token in TRUTH_LEAK_TOKENS if token in lowered]
    if leaked:
        raise ValueError(f"提示中检测到隐藏标签字段：{leaked}")


def parse_json_object(text: str) -> dict[str, Any]:
    """解析模型最终 JSON，容忍 Markdown 围栏但不猜测多个对象。"""
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:json)?\s*", "", candidate, flags=re.IGNORECASE)
        candidate = re.sub(r"\s*```$", "", candidate)
    try:
        obj = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ValueError("模型最终输出不是单一有效 JSON 对象") from exc
    if not isinstance(obj, dict):
        raise ValueError("模型最终输出的 JSON 根节点不是对象")
    return obj


def validate_verdict(obj: dict[str, Any]) -> dict[str, Any]:
    """严格验证评判结构，防止缺字段或自由文本静默进入统计。"""
    expected = {"verdict", "confidence", "rationale", "cited_evidence"}
    if set(obj) != expected:
        raise ValueError(f"评判字段必须恰为 {sorted(expected)}，实际为 {sorted(obj)}")
    if obj["verdict"] not in VERDICTS:
        raise ValueError(f"未知 verdict：{obj['verdict']}")
    confidence = obj["confidence"]
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise ValueError("confidence 必须是数值")
    if not 0.0 <= float(confidence) <= 1.0:
        raise ValueError("confidence 必须位于 [0, 1]")
    if not isinstance(obj["rationale"], str) or not obj["rationale"].strip():
        raise ValueError("rationale 必须是非空字符串")
    evidence = obj["cited_evidence"]
    if not isinstance(evidence, list) or len(evidence) > 3:
        raise ValueError("cited_evidence 必须是至多三项的数组")
    if not all(isinstance(item, str) for item in evidence):
        raise ValueError("cited_evidence 的每一项必须是字符串")
    return {
        "verdict": obj["verdict"],
        "confidence": float(confidence),
        "rationale": obj["rationale"].strip(),
        "cited_evidence": [item.strip() for item in evidence],
    }


def utc_now() -> str:
    """返回秒级 UTC 时间戳，避免本地时区混淆费率与批次。"""
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_utc(timestamp_utc: str) -> dt.datetime:
    """解析本实验生成的 UTC 时间戳。"""
    return dt.datetime.strptime(timestamp_utc, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=dt.timezone.utc
    )


def deepseek_is_peak(timestamp_utc: str) -> bool:
    """按 DeepSeek 2026-08-23 公布时段判断 V4 峰值费率。"""
    moment = parse_utc(timestamp_utc)
    if moment.weekday() >= 5:
        return False
    return 1 <= moment.hour < 4 or 6 <= moment.hour < 10


def deepseek_cost_usd(
    usage: dict[str, Any], timestamp_utc: str, force_peak: bool = False
) -> float:
    """依据命中/未命中/输出 token 分项核算 DeepSeek V4-Pro 成本。

    参数
    ----
    usage:
        DeepSeek 返回的 usage 字段。
    timestamp_utc:
        请求完成时间，格式为 ``YYYY-mm-ddTHH:MM:SSZ``。
    force_peak:
        为 True 时使用峰值价格，作为预算硬上限的保守账本。
    """
    peak = force_peak or deepseek_is_peak(timestamp_utc)
    if peak:
        hit_rate, miss_rate, output_rate = 0.044, 1.32, 3.96
    else:
        hit_rate, miss_rate, output_rate = 0.022, 0.66, 1.98
    prompt_total = int(usage.get("prompt_tokens") or 0)
    hit = int(usage.get("prompt_cache_hit_tokens") or 0)
    miss = int(usage.get("prompt_cache_miss_tokens") or max(0, prompt_total - hit))
    output = int(usage.get("completion_tokens") or 0)
    return (hit * hit_rate + miss * miss_rate + output * output_rate) / 1_000_000


def redact_text(text: str, secrets: Iterable[str]) -> str:
    """从错误信息中移除密钥，并压缩本机绝对路径。"""
    redacted = text
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, "[REDACTED_SECRET]")
    redacted = re.sub(r"[A-Za-z]:\\[^\r\n\t\"]+", "[LOCAL_PATH]", redacted)
    return redacted
