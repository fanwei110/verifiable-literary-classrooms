"""计算成本—效用权衡（回应 R4.4；只用冻结日志，不调用任何模型）。

数据：ext_e1b_m2 / ext_e1b_m4（同一批确认集 group 上运行 resample、F1、F2、F3 四臂，
各臂共享同一个 k=0 生成，因此 k=0 失败池完全相同，臂间比较公平）；
k=0 生成成本另用主样本 ext_e1c_m1–m4 按条件报告（含 grounding 窗口的输入开销）。

口径（规则写定在先）：
- 失败池 = k=0 strict 失败的确认集 group；每臂只计 k≥1 的额外调用。
- resample 臂在实验中固定抽满 3 次（不早停），F1–F3 首次通过即停。故 resample 同时报告
  "实际执行"与"首次通过即停的回放"两种开销；回放只截取已观察到的轮次，不补造生成。
- 成功 = k≤3 内任一轮 strict 通过；报告成功率、成功者首次通过的平均轮次、k=3 后仍失败比例。
- token 分输入与输出报告（F 臂累积对话历史，输入随轮次增长）；推理 token 若日志有则单列。
- latency_s 是客户端墙钟时间（含网络与排队），不是课堂响应时间保证。
- 不同模型的 token 不换算成统一货币。日志中没有 F4 臂记录，不报告。
- verifier 计时：本机对主样本 1,319 条 k=0 输出逐条判定，分冷启动（首次加载语料）与热态。

输出 out/cost_utility.md、out/cost_utility.csv。
"""
from __future__ import annotations

import csv
import platform
import statistics
import time
from collections import defaultdict
from pathlib import Path

import r2_common as C

OUT = Path(__file__).resolve().parent / "out"
ARMS = ["resample", "F1", "F2", "F3"]


def usage(rd):
    u = rd.get("usage") or {}
    det = u.get("completion_tokens_details") or {}
    return (int(u.get("prompt_tokens") or 0), int(u.get("completion_tokens") or 0),
            int(det.get("reasoning_tokens") or 0), float(rd.get("latency_s") or 0.0))


def passed(rd):
    return bool((rd.get("judge") or {}).get("strict_correct"))


def arm_stats(recs, stop_at_first):
    n = len(recs)
    succ, first_rounds, calls, tin, tout, treas, lat = 0, [], 0, 0, 0, 0, 0.0
    for r in recs:
        extra = r["rounds"][1:4]
        used = extra
        hit = next((i for i, rd in enumerate(extra, 1) if passed(rd)), None)
        if stop_at_first and hit is not None:
            used = extra[:hit]
        if hit is not None:
            succ += 1
            first_rounds.append(hit)
        calls += len(used)
        for rd in used:
            a, b, c, d = usage(rd)
            tin, tout, treas, lat = tin + a, tout + b, treas + c, lat + d
    return {"n_fail_pool": n, "successes": succ, "success_rate": succ / n,
            "still_failing_after_k3": 1 - succ / n,
            "mean_first_success_round": statistics.mean(first_rounds) if first_rounds else float("nan"),
            "extra_calls_per_item": calls / n, "extra_input_tok_per_item": tin / n,
            "extra_output_tok_per_item": tout / n, "extra_reasoning_tok_per_item": treas / n,
            "extra_latency_s_per_item": lat / n,
            "extra_total_tok_per_success": (tin + tout) / succ if succ else float("nan"),
            "extra_latency_s_per_success": lat / succ if succ else float("nan")}


def verifier_timing(rows):
    t0 = time.perf_counter()
    J = C.J
    J.load_corpus()  # 冷启动：首次加载并缓存冻结语料索引
    cold = time.perf_counter() - t0
    times = []
    for r in rows:
        s = time.perf_counter()
        J.judge(r["task_id"], r["rounds"][0]["completion"], r["condition"])
        times.append(time.perf_counter() - s)
    times.sort()
    return cold, statistics.median(times), times[int(0.95 * len(times))], sum(times)


def main() -> None:
    C.utf8_stdout()
    OUT.mkdir(exist_ok=True)
    out_rows = []
    md = ["# Computational cost–utility of in-loop verification (frozen logs only)", ""]
    for tag in ("e1b_m2", "e1b_m4"):
        recs = [r for r in C.read_jsonl(C.ROOT / "runs" / "raw" / f"ext_{tag}" / f"{tag}.jsonl")
                if r["task_id"].split("_")[0] not in C.DEV]
        by_arm = defaultdict(list)
        for r in recs:
            if not r["k0_strict"]:
                by_arm[r["arm"]].append(r)
        pools = {a: sorted(x["group_id"] for x in by_arm[a]) for a in ARMS}
        assert all(pools[a] == pools["F3"] for a in ARMS), f"{tag}: 各臂失败池不一致"
        model = recs[0]["model"]
        md += [f"## {model} ({recs[0]['model_slug']}), k=0 failure pool n = {len(pools['F3'])}", "",
               "| Arm | Accounting | Success within k≤3 | Mean first-success round | Extra calls / item | "
               "Extra input tok / item | Extra output tok / item | Reasoning tok / item | Extra latency (s) / item | "
               "Extra tokens / success | Extra latency (s) / success |",
               "|---|---|---|---|---|---|---|---|---|---|---|"]
        for arm in ARMS:
            for stop, acc in ((arm != "resample", "as executed"), (True, "stop-at-first replay")):
                if arm != "resample" and acc == "stop-at-first replay":
                    continue
                s = arm_stats(by_arm[arm], stop_at_first=stop)
                out_rows.append({"model": model, "arm": arm, "accounting": acc, **s})
                md.append(f"| {arm} | {acc} | {100*s['success_rate']:.1f}% ({s['successes']}/{s['n_fail_pool']}) | "
                          f"{s['mean_first_success_round']:.2f} | {s['extra_calls_per_item']:.2f} | "
                          f"{s['extra_input_tok_per_item']:.0f} | {s['extra_output_tok_per_item']:.0f} | "
                          f"{s['extra_reasoning_tok_per_item']:.0f} | {s['extra_latency_s_per_item']:.1f} | "
                          f"{s['extra_total_tok_per_success']:.0f} | {s['extra_latency_s_per_success']:.1f} |")
        md.append("")

    # k=0 单次生成成本（主样本，按条件）
    rows = C.load_primary()
    md += ["## Single k=0 generation cost by condition (primary sample, all four models pooled)", "",
           "| Condition | n | Input tok (mean) | Output tok (mean) | Latency s (median) |", "|---|---|---|---|---|"]
    for cnd in ("C1", "C2", "C3", "C4"):
        us = [usage(r["rounds"][0]) for r in rows if r["condition"] == cnd]
        md.append(f"| {cnd} | {len(us)} | {statistics.mean(u[0] for u in us):.0f} | {statistics.mean(u[1] for u in us):.0f} | "
                  f"{statistics.median(u[3] for u in us):.1f} |")
    cold, med, p95, tot = verifier_timing(rows)
    md += ["", "## Deterministic verifier runtime (no model call)", "",
           f"Machine: {platform.processor() or platform.machine()}, Python {platform.python_version()}. "
           f"Cold start (load frozen corpus index once): {cold*1000:.0f} ms. "
           f"Per-generation judgement over {len(rows)} k=0 outputs: median {med*1000:.2f} ms, "
           f"95th percentile {p95*1000:.2f} ms, total {tot:.2f} s.", "",
           "Notes: latency is client-side wall-clock time and includes network and queueing. Tokens are not converted "
           "to a common currency across providers. No F4 records exist in the released logs, so F4 is not reported."]
    with (OUT / "cost_utility.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out_rows[0]))
        w.writeheader()
        w.writerows(out_rows)
    (OUT / "cost_utility.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
