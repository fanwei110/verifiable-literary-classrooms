"""期刊扩展版双路由 API 客户端：DeepSeek 官方 + OpenRouter。

- 同一 OpenAI-compatible chat 接口；retry/backoff/timeout 逻辑仿 runner.py。
- 每次调用把 usage 记入成本台账 journal_extension/cost_ledger.csv；
  累计花费超过警戒线（$85）时 raise BudgetAlert（外层攒批问用户）。
- 价格：OpenRouter 模型优先读 config/model_price_snapshot.json；
  DeepSeek 官方按常量估计（台账存 token 数，价格可随时重算）。
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import os
import re
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
EXT = Path(__file__).resolve().parent
LEDGER = EXT / "cost_ledger.csv"
PRICE_SNAPSHOT = ROOT / "config" / "model_price_snapshot.json"

DS_KEY_ENV = "DEEPSEEK_API_KEY"
OR_KEY_ENV = "OPENROUTER_API_KEY"

BUDGET_ALERT_USD = 85.0
TIMEOUT_S = 180
RETRY_BACKOFF = [5, 15, 60]

# 扩展版模型注册表（冻结版 M1–M3 沿用编号；差异记入 DEVIATIONS_ext）
EXT_MODELS = {
    "M1": {  # 仅核心格子
        "label": "Mistral Large 2512",
        "provider": "openrouter",
        "slug": "mistralai/mistral-large-2512",
    },
    "M2": {  # 主力；官方 API（与冻结版 openrouter slug 的差异记 deviation）
        "label": "DeepSeek V4 (official chat)",
        "provider": "deepseek",
        "slug": "deepseek-chat",
    },
    "M3": {
        "label": "Qwen3 235B A22B",
        "provider": "openrouter",
        "slug": "qwen/qwen3-235b-a22b-2507",
    },
    "M4": {  # 新增推理模型
        "label": "DeepSeek Reasoner (official)",
        "provider": "deepseek",
        "slug": "deepseek-reasoner",
    },
}

# DeepSeek 官方价（USD / 1M tokens，2026-07 估计值；台账存 token，可重算）
DS_PRICES = {
    "deepseek-chat": (0.27, 1.10),
    "deepseek-reasoner": (0.55, 2.19),
}


class BudgetAlert(RuntimeError):
    pass


def _read_key(env_var: str, pattern: str) -> str:
    text = os.getenv(env_var, "")
    m = re.search(pattern, text)
    if not m:
        raise SystemExit(f"set {env_var} before running API-backed scripts")
    return m.group(0)


def _or_prices() -> dict[str, tuple[float, float]]:
    """OpenRouter 价格表（USD / 1M tokens），读快照。"""
    out = {}
    if PRICE_SNAPSHOT.exists():
        data = json.loads(PRICE_SNAPSHOT.read_text(encoding="utf-8"))
        models = data.get("models", data) if isinstance(data, dict) else data
        for m in models:
            if not isinstance(m, dict):
                continue
            p = m.get("pricing") or {}
            try:
                out[m["id"]] = (float(p.get("prompt", 0)) * 1e6, float(p.get("completion", 0)) * 1e6)
            except (TypeError, ValueError):
                continue
    return out


class Client:
    _HEADER = ["ts_utc", "model_key", "provider", "slug", "prompt_tokens",
               "completion_tokens", "est_cost_usd", "tag"]

    def __init__(self) -> None:
        self.ds_key = _read_key(DS_KEY_ENV, r"sk-[A-Za-z0-9_-]+")
        self.or_key = _read_key(OR_KEY_ENV, r"sk-or-[A-Za-z0-9_-]+")
        self.or_prices = _or_prices()
        # 每进程独立台账：多进程并发 append 同一 CSV 会撕裂出残行，曾致 spent() 读到 None 而全面失败。
        # 各进程只写自己的 cost_ledger_p{pid}.csv；spent() 汇总所有 cost_ledger*.csv。
        self.ledger = EXT / f"cost_ledger_p{os.getpid()}.csv"
        if not self.ledger.exists():
            with self.ledger.open("w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(self._HEADER)

    # ---- 台账 ----
    def spent(self) -> float:
        total = 0.0
        for led in EXT.glob("cost_ledger*.csv"):   # 主台账 + 各进程台账
            try:
                with led.open(encoding="utf-8") as f:
                    for row in csv.DictReader(f):
                        try:
                            total += float(row.get("est_cost_usd"))
                        except (TypeError, ValueError):
                            pass  # 跳过残行 / 坏值 / 空字段
            except OSError:
                pass
        return total

    def _log_cost(self, model_key: str, slug: str, provider: str,
                  usage: dict, tag: str) -> None:
        pt = int(usage.get("prompt_tokens") or 0)
        ct = int(usage.get("completion_tokens") or 0)
        if provider == "deepseek":
            pin, pout = DS_PRICES.get(slug, (0.5, 2.0))
        else:
            pin, pout = self.or_prices.get(slug, (1.0, 3.0))
        cost = pt / 1e6 * pin + ct / 1e6 * pout
        with self.ledger.open("a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(
                [dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                 model_key, provider, slug, pt, ct, f"{cost:.6f}", tag]
            )

    # ---- 调用 ----
    def chat(self, model_key: str, messages: list[dict], max_tokens: int = 2048,
             tag: str = "") -> tuple[str, dict, float]:
        """返回 (completion_text, meta, latency_s)。失败重试 3 次后抛异常。"""
        spec = EXT_MODELS[model_key]
        if spec["provider"] == "deepseek":
            url = "https://api.deepseek.com/chat/completions"
            key = self.ds_key
        else:
            url = "https://openrouter.ai/api/v1/chat/completions"
            key = self.or_key
        body = {"model": spec["slug"], "messages": messages, "max_tokens": max_tokens}
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

        last_err: Exception | None = None
        for attempt in range(len(RETRY_BACKOFF) + 1):
            t0 = time.time()
            try:
                resp = requests.post(url, headers=headers, json=body, timeout=TIMEOUT_S)
                if resp.status_code in (429, 500, 502, 503, 504):
                    raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
                resp.raise_for_status()
                data = resp.json()
                latency = time.time() - t0
                choice = data["choices"][0]
                text = choice["message"].get("content") or ""
                usage = data.get("usage") or {}
                meta = {
                    "provider": spec["provider"],
                    "model_id": data.get("model"),
                    "usage": usage,
                    "finish_reason": choice.get("finish_reason"),
                }
                self._log_cost(model_key, spec["slug"], spec["provider"], usage, tag)
                total = self.spent()
                if total > BUDGET_ALERT_USD:
                    raise BudgetAlert(f"cost ledger total ${total:.2f} > ${BUDGET_ALERT_USD}")
                return text, meta, latency
            except BudgetAlert:
                raise
            except Exception as e:  # 网络/限流/解析
                last_err = e
                if attempt < len(RETRY_BACKOFF):
                    time.sleep(RETRY_BACKOFF[attempt])
        raise RuntimeError(f"API call failed after retries ({model_key}): {last_err}")


if __name__ == "__main__":
    c = Client()
    print("keys loaded; ledger total = $%.4f" % c.spent())
    txt, meta, lat = c.chat("M2", [{"role": "user", "content": "Reply with the single word: ok"}],
                            max_tokens=8, tag="selftest")
    print("M2 selftest:", txt.strip()[:40], "| latency %.1fs" % lat, "| usage", meta["usage"])
