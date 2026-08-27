"""运行 R1.7 的 Codex 订阅 judge 与 DeepSeek V4-Pro judge。

每个题项均为独立单轮；脚本支持断点续跑，并把所有已计费 DeepSeek 尝试写入成本账本。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import threading
import time
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import requests

from experiment_core import (
    append_jsonl,
    build_prompt,
    canonical_json,
    deepseek_cost_usd,
    parse_json_object,
    read_jsonl,
    redact_text,
    sha256_file,
    sha256_text,
    utc_now,
    validate_verdict,
)


BASE = Path(__file__).resolve().parent
MANIFEST_PATH = BASE / "inputs" / "prompts_manifest.jsonl"
META_PATH = BASE / "inputs" / "manifest_metadata.json"
SCHEMA_PATH = BASE / "verdict.schema.json"
RUNTIME_DIR = BASE / "runtime_empty"
RAW_DIR = BASE / "raw"
SMOKE_DIR = BASE / "smoke"

GPT_MODEL = "gpt-5.6-sol"
DEEPSEEK_MODEL = "deepseek-v4-pro"
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
# 正式批采用统一 65,536 上限。16,384 已在 SEV058/gold_reference 出现纯
# reasoning 截断；提高的是输出安全上限，不改变 thinking、reasoning_effort 或提示。
DEEPSEEK_MAX_TOKENS = 65536
DEEPSEEK_PRICING_URL = "https://api-docs.deepseek.com/quick_start/pricing/"
DEEPSEEK_RESERVE_USD_PER_CALL = 0.05

WRITE_LOCK = threading.Lock()


@dataclass
class JobOutcome:
    """单个任务的结果与是否应停止整个供应商批次。"""

    status: str
    record: dict[str, Any] | None = None
    fatal: bool = False
    message: str = ""


class DeepSeekBudget:
    """以峰值费率保守计账，并为并发在途请求预留费用。"""

    def __init__(self, budget_usd: float, attempt_paths: list[Path]) -> None:
        self.budget_usd = budget_usd
        self.stop_at_usd = max(0.0, budget_usd - 0.25)
        self.lock = threading.Lock()
        self.reserved_usd = 0.0
        self.spent_peak_usd = 0.0
        self.spent_tariff_usd = 0.0
        for path in attempt_paths:
            for row in read_jsonl(path):
                self.spent_peak_usd += float(row.get("cost_usd_peak") or 0.0)
                self.spent_tariff_usd += float(row.get("cost_usd_tariff") or 0.0)

    def reserve(self) -> bool:
        """请求派发前预留最坏情形余量，避免两个并发请求共同越界。"""
        with self.lock:
            projected = (
                self.spent_peak_usd + self.reserved_usd + DEEPSEEK_RESERVE_USD_PER_CALL
            )
            if projected > self.stop_at_usd:
                return False
            self.reserved_usd += DEEPSEEK_RESERVE_USD_PER_CALL
            return True

    def settle(self, cost_peak: float, cost_tariff: float) -> None:
        """请求结束后释放预留，并登记实际 token 对应费用。"""
        with self.lock:
            self.reserved_usd = max(
                0.0, self.reserved_usd - DEEPSEEK_RESERVE_USD_PER_CALL
            )
            self.spent_peak_usd += cost_peak
            self.spent_tariff_usd += cost_tariff

    def release(self) -> None:
        """无 usage 的失败请求只释放预留，不虚构费用。"""
        with self.lock:
            self.reserved_usd = max(
                0.0, self.reserved_usd - DEEPSEEK_RESERVE_USD_PER_CALL
            )

    def snapshot(self) -> dict[str, float]:
        """返回线程安全的当前账本。"""
        with self.lock:
            return {
                "spent_peak_usd": self.spent_peak_usd,
                "spent_tariff_usd": self.spent_tariff_usd,
                "reserved_usd": self.reserved_usd,
                "stop_at_usd": self.stop_at_usd,
                "budget_usd": self.budget_usd,
            }


def load_manifest() -> list[dict[str, Any]]:
    """读取冻结提示并验证哈希与数量，防止运行中输入漂移。"""
    if not MANIFEST_PATH.exists() or not META_PATH.exists():
        raise FileNotFoundError("请先运行 prepare_manifest.py 冻结提示")
    rows = read_jsonl(MANIFEST_PATH)
    metadata = json.loads(META_PATH.read_text(encoding="utf-8"))
    if len(rows) != 180:
        raise ValueError(f"冻结提示必须为 180 条，实际为 {len(rows)}")
    if sha256_file(MANIFEST_PATH) != metadata["manifest_sha256"]:
        raise ValueError("prompts_manifest.jsonl 哈希与冻结元数据不一致")
    for row in rows:
        if sha256_text(row["prompt"]) != row["prompt_sha256"]:
            raise ValueError(f"{row['item_id']} {row['condition']} 的提示哈希失配")
    return sorted(rows, key=lambda row: int(row["dispatch_order"]))


def read_key(path: Path) -> str:
    """只在运行时读取 DeepSeek 密钥，不打印、不持久化。"""
    key = path.read_text(encoding="utf-8-sig").strip()
    if len(key) < 16 or any(char.isspace() for char in key):
        raise ValueError("DeepSeek 密钥文件格式异常")
    return key


def success_ids(path: Path) -> set[tuple[str, str]]:
    """提取已成功题项，断点续跑仅跳过完整且可解析的结果。"""
    done: set[tuple[str, str]] = set()
    for row in read_jsonl(path):
        if row.get("status") == "success":
            validate_verdict(row["response"])
            done.add((row["item_id"], row["condition"]))
    return done


def deepseek_body(prompt: str) -> dict[str, Any]:
    """生成固定请求体；thinking mode 下故意不发送温度等无效参数。"""
    return {
        "model": DEEPSEEK_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "thinking": {"type": "enabled"},
        "reasoning_effort": "high",
        "response_format": {"type": "json_object"},
        "max_tokens": DEEPSEEK_MAX_TOKENS,
        "stream": False,
    }


def run_deepseek_job(
    job: dict[str, Any],
    api_key: str,
    budget: DeepSeekBudget,
    result_path: Path,
    attempt_path: Path,
    timeout_s: int,
) -> JobOutcome:
    """执行一个 DeepSeek 单轮任务；仅网络、429 与 5xx 自动重试。"""
    body = deepseek_body(job["prompt"])
    request_sha = sha256_text(canonical_json(body))
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    transient_status = {408, 409, 429, 500, 502, 503, 504}
    for attempt_number in range(1, 4):
        if not budget.reserve():
            snapshot = budget.snapshot()
            return JobOutcome(
                status="budget_stop",
                fatal=True,
                message=(
                    "DeepSeek 峰值费率保守账本触及停止线："
                    f"${snapshot['spent_peak_usd']:.4f}/${snapshot['stop_at_usd']:.2f}"
                ),
            )
        started = utc_now()
        started_clock = time.perf_counter()
        response: requests.Response | None = None
        usage: dict[str, Any] = {}
        cost_peak = 0.0
        cost_tariff = 0.0
        attempt_status = "unknown"
        error_message = ""
        response_payload: dict[str, Any] | None = None
        try:
            response = requests.post(
                DEEPSEEK_URL,
                headers=headers,
                json=body,
                timeout=(30, timeout_s),
            )
            try:
                response_payload = response.json()
            except ValueError:
                response_payload = None
            if response_payload and isinstance(response_payload.get("usage"), dict):
                usage = response_payload["usage"]
            finished = utc_now()
            cost_peak = deepseek_cost_usd(usage, finished, force_peak=True)
            cost_tariff = deepseek_cost_usd(usage, finished, force_peak=False)
            if response.status_code != 200:
                attempt_status = f"http_{response.status_code}"
                if response_payload and isinstance(response_payload.get("error"), dict):
                    error_message = str(response_payload["error"].get("message", ""))
                else:
                    error_message = response.text[:500]
            else:
                choice = response_payload["choices"][0]
                message = choice["message"]
                raw_content = message.get("content") or ""
                parsed = validate_verdict(parse_json_object(raw_content))
                finish_reason = choice.get("finish_reason")
                if finish_reason != "stop":
                    raise ValueError(f"finish_reason={finish_reason}")
                reasoning_content = message.get("reasoning_content") or ""
                result = {
                    "status": "success",
                    "provider": "deepseek_api",
                    "model_id": DEEPSEEK_MODEL,
                    "item_id": job["item_id"],
                    "condition": job["condition"],
                    "dispatch_order": job["dispatch_order"],
                    "prompt_sha256": job["prompt_sha256"],
                    "request_sha256": request_sha,
                    "timestamp_started_utc": started,
                    "timestamp_finished_utc": finished,
                    "latency_s": round(time.perf_counter() - started_clock, 3),
                    "attempt_number": attempt_number,
                    "response": parsed,
                    "usage": usage,
                    "cost_usd_peak": cost_peak,
                    "cost_usd_tariff": cost_tariff,
                    "api_response_id": response_payload.get("id"),
                    "returned_model": response_payload.get("model"),
                    "system_fingerprint": response_payload.get("system_fingerprint"),
                    "finish_reason": finish_reason,
                    "request_config": {
                        "thinking": "enabled",
                        "reasoning_effort": "high",
                        "response_format": "json_object",
                        "max_tokens": DEEPSEEK_MAX_TOKENS,
                    },
                    "reasoning_content_chars": len(reasoning_content),
                    "reasoning_content_sha256": (
                        sha256_text(reasoning_content) if reasoning_content else None
                    ),
                    "pricing_reference": DEEPSEEK_PRICING_URL,
                }
                attempt_status = "success"
                budget.settle(cost_peak, cost_tariff)
                attempt_record = {
                    "provider": "deepseek_api",
                    "item_id": job["item_id"],
                    "condition": job["condition"],
                    "attempt_number": attempt_number,
                    "status": attempt_status,
                    "timestamp_utc": finished,
                    "request_sha256": request_sha,
                    "usage": usage,
                    "cost_usd_peak": cost_peak,
                    "cost_usd_tariff": cost_tariff,
                    "http_status": response.status_code,
                }
                with WRITE_LOCK:
                    append_jsonl(attempt_path, attempt_record)
                    append_jsonl(result_path, result)
                return JobOutcome(status="success", record=result)
        except requests.Timeout as exc:
            finished = utc_now()
            attempt_status = "timeout"
            error_message = str(exc)
        except requests.RequestException as exc:
            finished = utc_now()
            attempt_status = "network_error"
            error_message = str(exc)
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            finished = utc_now()
            attempt_status = "invalid_response"
            error_message = str(exc)
        if usage:
            budget.settle(cost_peak, cost_tariff)
        else:
            budget.release()
        sanitized_error = redact_text(error_message, [api_key])[:800]
        http_status = response.status_code if response is not None else None
        attempt_record = {
            "provider": "deepseek_api",
            "item_id": job["item_id"],
            "condition": job["condition"],
            "attempt_number": attempt_number,
            "status": attempt_status,
            "timestamp_utc": finished,
            "request_sha256": request_sha,
            "usage": usage,
            "cost_usd_peak": cost_peak,
            "cost_usd_tariff": cost_tariff,
            "http_status": http_status,
            "error": sanitized_error,
        }
        with WRITE_LOCK:
            append_jsonl(attempt_path, attempt_record)

        retryable = (
            attempt_status in {"timeout", "network_error"}
            or http_status in transient_status
        )
        if retryable and attempt_number < 3:
            time.sleep(2**attempt_number)
            continue
        # 无最终 JSON 往往意味着 reasoning 用尽输出额度；继续整批会系统性浪费预算。
        fatal = bool(
            http_status in {400, 401, 402, 403, 404}
            or attempt_status == "invalid_response"
        )
        return JobOutcome(
            status=attempt_status,
            fatal=fatal,
            message=f"{job['item_id']} {job['condition']}: {sanitized_error}",
        )
    return JobOutcome(
        status="unexpected", fatal=True, message="不应到达的 DeepSeek 分支"
    )


def find_codex_executable(explicit: str | None) -> str:
    """优先选择 npm 的 cmd 包装；WindowsApps 原生文件可能拒绝子进程执行。"""
    if explicit:
        path = Path(explicit)
        if not path.exists():
            raise FileNotFoundError(f"找不到 codex 可执行文件：{path}")
        return str(path)
    command_wrapper = shutil.which("codex.cmd")
    if command_wrapper:
        return command_wrapper
    where = subprocess.run(
        ["where.exe", "codex"], capture_output=True, text=True, check=False
    )
    candidates = [line.strip() for line in where.stdout.splitlines() if line.strip()]
    for candidate in candidates:
        if candidate.lower().endswith(".cmd"):
            return candidate
    for candidate in candidates:
        if candidate.lower().endswith(".exe"):
            return candidate
    raise FileNotFoundError("未找到 codex.cmd 或 codex.exe")


def executable_prefix(codex_exe: str) -> list[str]:
    """让 CreateProcess 通过 cmd.exe 执行批处理包装，避免 WinError 5。"""
    if codex_exe.lower().endswith((".cmd", ".bat")):
        command_processor = os.environ.get("COMSPEC", r"C:\Windows\System32\cmd.exe")
        return [command_processor, "/d", "/c", codex_exe]
    return [codex_exe]


def codex_version(codex_exe: str) -> str:
    """记录运行时 CLI 版本，模型比较不允许静默换客户端。"""
    proc = subprocess.run(
        executable_prefix(codex_exe) + ["--version"],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    if proc.returncode != 0:
        raise RuntimeError("无法读取 Codex CLI 版本")
    version = proc.stdout.strip()
    if not version.startswith("codex-cli "):
        raise RuntimeError(f"未知 Codex 版本输出：{version}")
    return version


def codex_command(codex_exe: str) -> list[str]:
    """构造隔离命令；关闭工具功能是对提示中“无工具”的技术加固。"""
    return [
        *executable_prefix(codex_exe),
        "-a",
        "never",
        "-m",
        GPT_MODEL,
        "-c",
        'model_reasoning_effort="high"',
        "-c",
        "skills.include_instructions=false",
        "-c",
        "skills.bundled.enabled=false",
        "--disable",
        "shell_tool",
        "--disable",
        "apps",
        "--disable",
        "browser_use",
        "--disable",
        "computer_use",
        "--disable",
        "in_app_browser",
        "--disable",
        "image_generation",
        "--disable",
        "multi_agent",
        "--disable",
        "workspace_dependencies",
        "--disable",
        "plugins",
        "--disable",
        "plugin_sharing",
        "--disable",
        "remote_plugin",
        "--disable",
        "skill_mcp_dependency_install",
        "--disable",
        "hooks",
        "--disable",
        "memories",
        "--disable",
        "personality",
        "--disable",
        "goals",
        "--disable",
        "tool_suggest",
        "exec",
        "--json",
        "--ephemeral",
        "--ignore-user-config",
        "--skip-git-repo-check",
        "--sandbox",
        "read-only",
        "--output-schema",
        str(SCHEMA_PATH),
        "-C",
        str(RUNTIME_DIR),
        "-",
    ]


def parse_codex_events(
    stdout: str,
) -> tuple[list[dict[str, Any]], str, dict[str, Any], bool]:
    """解析 JSONL 事件并识别任何模型工具调用。"""
    events: list[dict[str, Any]] = []
    non_json: list[str] = []
    final_text = ""
    usage: dict[str, Any] = {}
    tool_types = {
        "command_execution",
        "file_change",
        "mcp_tool_call",
        "web_search",
        "image_generation",
        "computer_use",
        "collaboration_tool_call",
    }
    tool_used = False
    for line in stdout.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            non_json.append(line)
            continue
        events.append(event)
        item = event.get("item") if isinstance(event.get("item"), dict) else {}
        item_type = item.get("type")
        if item_type in tool_types:
            tool_used = True
        if event.get("type") == "item.completed" and item_type == "agent_message":
            final_text = str(item.get("text") or "")
        if event.get("type") == "turn.completed" and isinstance(
            event.get("usage"), dict
        ):
            usage = event["usage"]
    if non_json:
        raise ValueError("Codex --json 标准输出混入非 JSON 行")
    if not final_text:
        raise ValueError("Codex 事件中没有最终 agent_message")
    return events, final_text, usage, tool_used


def run_gpt_job(
    job: dict[str, Any],
    codex_exe: str,
    cli_version: str,
    result_path: Path,
    attempt_path: Path,
    timeout_s: int,
) -> JobOutcome:
    """执行一个完全独立的 Codex 订阅会话；工具调用或坏 JSON 最多重跑两次。"""
    command = codex_command(codex_exe)
    request_sha = sha256_text(
        canonical_json({"model": GPT_MODEL, "prompt": job["prompt"]})
    )
    event_dir = RAW_DIR / "gpt_events"
    event_dir.mkdir(parents=True, exist_ok=True)
    safe_stem = f"{job['item_id']}_{job['condition']}"
    for attempt_number in range(1, 4):
        started = utc_now()
        started_clock = time.perf_counter()
        proc: subprocess.CompletedProcess[str] | None = None
        try:
            proc = subprocess.run(
                command,
                input=job["prompt"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=RUNTIME_DIR,
                timeout=timeout_s,
                check=False,
                env=os.environ.copy(),
            )
            finished = utc_now()
            event_path = event_dir / f"{safe_stem}_a{attempt_number}.jsonl"
            event_path.write_text(proc.stdout, encoding="utf-8")
            if proc.returncode != 0:
                stderr = redact_text(proc.stderr, [])[:1200]
                lowered = f"{proc.stdout}\n{proc.stderr}".lower()
                rate_limited = any(
                    marker in lowered
                    for marker in (
                        "usage limit",
                        "rate limit",
                        "too many requests",
                        "429",
                    )
                )
                status = "subscription_limit" if rate_limited else "process_error"
                attempt_record = {
                    "provider": "codex_cli_subscription",
                    "item_id": job["item_id"],
                    "condition": job["condition"],
                    "attempt_number": attempt_number,
                    "status": status,
                    "timestamp_utc": finished,
                    "request_sha256": request_sha,
                    "returncode": proc.returncode,
                    "stderr": stderr,
                    "event_log": str(event_path.relative_to(BASE)),
                }
                with WRITE_LOCK:
                    append_jsonl(attempt_path, attempt_record)
                if rate_limited:
                    return JobOutcome(
                        status=status, fatal=True, message="Codex 订阅限额中断"
                    )
                if attempt_number < 3:
                    time.sleep(2**attempt_number)
                    continue
                return JobOutcome(status=status, fatal=True, message=stderr)

            events, final_text, usage, tool_used = parse_codex_events(proc.stdout)
            parsed = validate_verdict(parse_json_object(final_text))
            if tool_used:
                status = "tool_used"
                message = "事件日志检测到工具调用，结果按方案作废"
            else:
                result = {
                    "status": "success",
                    "provider": "codex_cli_subscription",
                    "model_id": GPT_MODEL,
                    "codex_cli_version": cli_version,
                    "item_id": job["item_id"],
                    "condition": job["condition"],
                    "dispatch_order": job["dispatch_order"],
                    "prompt_sha256": job["prompt_sha256"],
                    "request_sha256": request_sha,
                    "timestamp_started_utc": started,
                    "timestamp_finished_utc": finished,
                    "latency_s": round(time.perf_counter() - started_clock, 3),
                    "attempt_number": attempt_number,
                    "response": parsed,
                    "usage": usage,
                    "tool_used": False,
                    "event_count": len(events),
                    "event_log": str(event_path.relative_to(BASE)),
                    "subscription_cost_usd": None,
                }
                attempt_record = {
                    "provider": "codex_cli_subscription",
                    "item_id": job["item_id"],
                    "condition": job["condition"],
                    "attempt_number": attempt_number,
                    "status": "success",
                    "timestamp_utc": finished,
                    "request_sha256": request_sha,
                    "usage": usage,
                    "tool_used": False,
                    "event_log": str(event_path.relative_to(BASE)),
                }
                with WRITE_LOCK:
                    append_jsonl(attempt_path, attempt_record)
                    append_jsonl(result_path, result)
                return JobOutcome(status="success", record=result)
        except subprocess.TimeoutExpired:
            finished = utc_now()
            status = "timeout"
            message = f"Codex 单题超过 {timeout_s} 秒"
        except (OSError, ValueError) as exc:
            finished = utc_now()
            status = "invalid_response"
            message = redact_text(str(exc), [])[:800]
        attempt_record = {
            "provider": "codex_cli_subscription",
            "item_id": job["item_id"],
            "condition": job["condition"],
            "attempt_number": attempt_number,
            "status": status,
            "timestamp_utc": finished,
            "request_sha256": request_sha,
            "tool_used": status == "tool_used",
            "error": message,
        }
        with WRITE_LOCK:
            append_jsonl(attempt_path, attempt_record)
        if (
            status in {"timeout", "invalid_response", "tool_used"}
            and attempt_number < 3
        ):
            time.sleep(2**attempt_number)
            continue
        return JobOutcome(status=status, fatal=False, message=message)
    return JobOutcome(status="unexpected", fatal=True, message="不应到达的 Codex 分支")


def synthetic_prompt() -> str:
    """生成不属于正式样本的结构化接口检查题。"""
    return build_prompt(
        {
            "quote": "All the world's a stage, and all the men and women merely players.",
            "author": "William Shakespeare",
            "work": "As You Like It",
            "locator": "Act II, Scene VII",
            "speaker": "Jaques",
        },
        "[No reference excerpts supplied.]",
    )


def run_smoke(
    provider: str,
    codex_exe: str | None,
    cli_version: str | None,
    api_key: str | None,
    budget: DeepSeekBudget | None,
    timeout_s: int,
    resume: bool,
) -> None:
    """每个供应商只跑一个合成题，验证鉴权、JSON 与审计字段。"""
    result_path = SMOKE_DIR / f"{provider}_results.jsonl"
    attempt_path = SMOKE_DIR / f"{provider}_attempts.jsonl"
    if result_path.exists() and not resume:
        raise FileExistsError(f"{result_path} 已存在；请使用 --resume")
    if success_ids(result_path):
        print(f"[smoke] {provider} 已通过，跳过")
        return
    prompt = synthetic_prompt()
    job = {
        "item_id": "SMOKE_SYNTHETIC",
        "condition": "closed",
        "dispatch_order": 0,
        "prompt": prompt,
        "prompt_sha256": sha256_text(prompt),
    }
    if provider == "gpt":
        assert codex_exe and cli_version
        outcome = run_gpt_job(
            job, codex_exe, cli_version, result_path, attempt_path, timeout_s
        )
    else:
        assert api_key and budget
        outcome = run_deepseek_job(
            job, api_key, budget, result_path, attempt_path, timeout_s
        )
    if outcome.status != "success":
        raise RuntimeError(f"{provider} 合成接口检查失败：{outcome.message}")
    print(f"[smoke] {provider} 通过")


def execute_pool(
    provider: str,
    jobs: list[dict[str, Any]],
    workers: int,
    worker: Callable[[dict[str, Any]], JobOutcome],
) -> tuple[int, list[JobOutcome]]:
    """增量派发任务，使致命错误出现后不会继续提交整批请求。"""
    completed = 0
    failures: list[JobOutcome] = []
    job_iter = iter(jobs)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        active: dict[Future[JobOutcome], dict[str, Any]] = {}

        def submit_next() -> bool:
            try:
                job = next(job_iter)
            except StopIteration:
                return False
            active[executor.submit(worker, job)] = job
            return True

        for _ in range(min(workers, len(jobs))):
            submit_next()
        stop = False
        while active:
            done, _ = wait(active, return_when=FIRST_COMPLETED)
            for future in done:
                job = active.pop(future)
                try:
                    outcome = future.result()
                except Exception as exc:  # 保底：未记录异常必须阻止继续花费
                    outcome = JobOutcome(
                        status="worker_exception",
                        fatal=True,
                        message=redact_text(str(exc), []),
                    )
                if outcome.status == "success":
                    completed += 1
                else:
                    failures.append(outcome)
                    print(
                        f"[{provider}] {job['item_id']} {job['condition']} 失败：{outcome.message}"
                    )
                if outcome.fatal:
                    stop = True
                if not stop:
                    submit_next()
                if completed % 10 == 0 and completed:
                    print(f"[{provider}] 本次已完成 {completed}/{len(jobs)}")
            if stop:
                for future in active:
                    future.cancel()
                break
    return completed, failures


def main() -> None:
    """命令行入口。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--deepseek-key-file", type=Path)
    parser.add_argument("--deepseek-budget-usd", type=float, default=10.0)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--gpt-workers", type=int, default=1)
    parser.add_argument("--deepseek-workers", type=int, default=2)
    parser.add_argument(
        "--provider", choices=("both", "gpt", "deepseek"), default="both"
    )
    parser.add_argument("--smoke-only", action="store_true")
    parser.add_argument("--skip-smoke", action="store_true")
    parser.add_argument("--codex-exe")
    parser.add_argument("--timeout-s", type=int, default=300)
    args = parser.parse_args()

    if args.gpt_workers != 1:
        raise ValueError("预注册方案固定 --gpt-workers 1")
    if args.deepseek_workers < 1 or args.deepseek_workers > 2:
        raise ValueError("--deepseek-workers 必须为 1 或 2")

    providers = ["gpt", "deepseek"] if args.provider == "both" else [args.provider]
    manifest = load_manifest()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    SMOKE_DIR.mkdir(parents=True, exist_ok=True)
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

    codex_exe: str | None = None
    cli_version: str | None = None
    if "gpt" in providers:
        codex_exe = find_codex_executable(args.codex_exe)
        cli_version = codex_version(codex_exe)
        if cli_version != "codex-cli 0.144.6":
            raise RuntimeError(
                f"Codex CLI 版本漂移：预注册 0.144.6，当前 {cli_version}；停止而不静默替换"
            )

    api_key: str | None = None
    budget: DeepSeekBudget | None = None
    if "deepseek" in providers:
        if not args.deepseek_key_file:
            raise ValueError("运行 DeepSeek 时必须提供 --deepseek-key-file")
        api_key = read_key(args.deepseek_key_file)
        budget = DeepSeekBudget(
            args.deepseek_budget_usd,
            [
                RAW_DIR / "deepseek_attempts.jsonl",
                SMOKE_DIR / "deepseek_attempts.jsonl",
            ],
        )

    if not args.skip_smoke:
        for provider in providers:
            run_smoke(
                provider,
                codex_exe,
                cli_version,
                api_key,
                budget,
                args.timeout_s,
                args.resume,
            )
    if args.smoke_only:
        if budget:
            print("DeepSeek 账本：" + json.dumps(budget.snapshot(), sort_keys=True))
        return

    for provider in providers:
        result_path = RAW_DIR / f"{provider}_results.jsonl"
        attempt_path = RAW_DIR / f"{provider}_attempts.jsonl"
        if result_path.exists() and not args.resume:
            raise FileExistsError(f"{result_path} 已存在；请使用 --resume")
        done = success_ids(result_path)
        jobs = [
            row for row in manifest if (row["item_id"], row["condition"]) not in done
        ]
        print(f"[{provider}] 待运行 {len(jobs)}，已完成 {len(done)}")
        if provider == "gpt":
            assert codex_exe and cli_version

            def worker(job: dict[str, Any]) -> JobOutcome:
                return run_gpt_job(
                    job,
                    codex_exe,
                    cli_version,
                    result_path,
                    attempt_path,
                    args.timeout_s,
                )

            completed, failures = execute_pool(provider, jobs, args.gpt_workers, worker)
        else:
            assert api_key and budget

            def worker(job: dict[str, Any]) -> JobOutcome:
                return run_deepseek_job(
                    job,
                    api_key,
                    budget,
                    result_path,
                    attempt_path,
                    args.timeout_s,
                )

            completed, failures = execute_pool(
                provider, jobs, args.deepseek_workers, worker
            )
            print("DeepSeek 账本：" + json.dumps(budget.snapshot(), sort_keys=True))
        print(f"[{provider}] 本次成功 {completed}，失败 {len(failures)}")
        if any(outcome.fatal for outcome in failures):
            raise RuntimeError(f"{provider} 出现致命中断，已保留断点")


if __name__ == "__main__":
    main()
