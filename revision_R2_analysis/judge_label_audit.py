"""LLM 裁判实验（正文 Table 8）的参照标签审计与重算（回应 R3.1/R3.4；post hoc 更正）。

问题：build_severity_package.py 只把每份回答的第一条证据（evidence[0]）展示给裁判，
参照标签却继承了整份回答的判定。T3 任务要求两条证据：第一条正确、第二条错误时，
整份回答失败，但裁判看到的那条是对的。

做法（不重跑任何模型，不改 360 条原始回答）：
1. 用公开的 formal_corr.jsonl 与原抽样规则在内存中重建 60 个 item → run 映射，
   与公开 foil_key.csv 逐项核对 auto_strict / auto_error_class / kind，
   与冻结提示清单逐项核对展示给裁判的五个 claim 字段。
2. 用同一修正后 verifier 对"展示给裁判的那条证据"单独判定，得到记录级参照标签。
3. 主口径（D6）：记录级标签，判据与正文 verifier 完全相同。
   敏感性：(a) 去掉裁判提示中未交代的窗口归属约束；(b) 再加译名别名 Ulysses/Odysseus。
4. 重算 strict accuracy、错误接受、正确接受、unsure、Wilson 区间、exact McNemar + Holm、
   去掉 unsure 的准确率，以及 gold-reference 条件下按错误类别的接受率。

输出 out/judge_label_audit.md、out/judge_item_audit.csv、out/judge_metrics_relabelled.csv。
"""
from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import r2_common as C

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
LJ = C.ROOT / "revision_R1_analysis" / "llm_judge_openbook"
sys.path.insert(0, str(LJ))
import analyze_results as AR  # noqa: E402

FORMAL = C.ROOT / "runs" / "raw" / "formal" / "formal_corr.jsonl"
FOIL_KEY = C.ROOT / "journal_extension" / "llm_judge_foil" / "foil_key.csv"
CONDS = ["closed", "rag_top3", "gold_reference"]
FIELDS = ("quote", "author", "work", "locator", "speaker_or_narrator")


def claimed_record(completion: str) -> dict:
    """与 build_severity_package.claimed_fields 相同的取法，但返回原始 dict 供判定。"""
    try:
        obj = json.loads(re.search(r"\{.*\}", completion, re.S).group(0))
        return (obj.get("evidence") or [{}])[0], obj
    except Exception:
        return {}, None


def rebuild_items() -> dict[str, dict]:
    """逐字复刻 build_severity_package.main 的抽样与编号。"""
    rows = C.read_jsonl(FORMAL)
    by_class, controls = defaultdict(list), []
    for r in rows:
        j = r.get("judge", {})
        rec, obj = claimed_record(r.get("completion", ""))
        cf = {k: str(rec.get(k, "")) for k in FIELDS} if rec else {}
        if not cf.get("quote"):
            continue
        item = {"run": r, "rec": rec, "obj": obj, **cf, "strict": r.get("strict_correct"),
                "error_class": j.get("error_class_candidate"), "run_id": r["run_id"]}
        if r.get("strict_correct"):
            controls.append(item)
        elif j.get("error_class_candidate"):
            by_class[j["error_class_candidate"]].append(item)

    def pick(items, n):
        items = sorted(items, key=lambda x: x["run_id"])
        step = max(1, len(items) // n)
        return items[::step][:n]

    sample = []
    for ec in ("fabricated_quotation", "misattribution", "version_drift", "context_displacement"):
        sample += [("err", it) for it in pick(by_class.get(ec, []), 12)]
    sample += [("ctrl", it) for it in pick(controls, 12)]
    sample.sort(key=lambda x: x[1]["run_id"][::-1])
    return {f"SEV{i:03d}": {"kind": k, **it} for i, (k, it) in enumerate(sample, 1)}


def verify_rebuild(items: dict) -> None:
    key = {r["item_id"]: r for r in AR.read_csv(FOIL_KEY)}
    assert set(key) == set(items), "item 集合不一致"
    for iid, it in items.items():
        k = key[iid]
        assert str(bool(it["strict"])) == k["auto_strict"], iid
        assert (it["error_class"] or "") == k["auto_error_class"], iid
        assert it["kind"] == k["kind"], iid
    # 展示给裁判的 claim 字段必须出现在冻结提示里
    man = C.read_jsonl(LJ / "inputs" / "prompts_manifest.jsonl")
    for m in man:
        it = items[m["item_id"]]
        for f in ("quote", "locator", "speaker_or_narrator"):
            assert it[f] in m["prompt"], (m["item_id"], f)


def record_label(it: dict, vj_kwargs: dict, window: bool) -> tuple[bool, str]:
    """对展示的那条证据单独判定。返回 (是否正确, 失败字段说明)。"""
    r = it["run"]
    task = C.J.load_task(r["task_id"])
    corpus = C.J.load_corpus()
    cond = r["condition"] if window else "C1"  # C1 = 不施加窗口归属
    if not vj_kwargs:
        d = C.J.evidence_result(it["rec"], task, corpus, cond, C.J.has_version_note(it["obj"] or {}))
        fails = [n for n, ok in (("quote", d["quote_found"]), ("author", d["claimed_author_ok"]),
                                 ("work", d["claimed_work_ok"]), ("locator", d["locator_ok"]),
                                 ("speaker", d["speaker_ok"]), ("window", d["grounded_ok"])) if not ok]
        return bool(d["strict"]), "+".join(fails)
    vj = C.VariantJudge(**vj_kwargs)
    return vj.record(it["rec"], task, cond), ""


def metrics(scored: list[dict], label: dict[str, bool], eclass: dict[str, str]) -> list[dict]:
    out = []
    for model in AR.MODEL_FILES:
        for cond in CONDS:
            rows = [x for x in scored if x["model"] == model and x["condition"] == cond]
            ok = [x["verdict"] == ("accurate" if label[x["item_id"]] else "inaccurate") for x in rows]
            n = len(rows)
            s = sum(ok)
            lo, hi = AR.wilson(s, n)
            err = [x for x in rows if not label[x["item_id"]]]
            cor = [x for x in rows if label[x["item_id"]]]
            uns = sum(x["verdict"] == "unsure" for x in rows)
            nu = n - uns
            out.append({
                "model": model, "condition": cond, "n_items": n, "n_correct_items": len(cor),
                "n_error_items": len(err), "strict_accuracy": s / n, "wilson_lo": lo, "wilson_hi": hi,
                "error_acceptance": sum(x["verdict"] == "accurate" for x in err) / len(err),
                "error_accepted": sum(x["verdict"] == "accurate" for x in err),
                "correct_acceptance": sum(x["verdict"] == "accurate" for x in cor) / len(cor),
                "unsure_rate": uns / n,
                "accuracy_excl_unsure": (sum(o for o, x in zip(ok, rows) if x["verdict"] != "unsure") / nu) if nu else float("nan"),
            })
    return out


def mcnemar(scored, label):
    from scipy.stats import binomtest
    out = []
    for model in AR.MODEL_FILES:
        look = {(x["item_id"], x["condition"]): x["verdict"] == ("accurate" if label[x["item_id"]] else "inaccurate")
                for x in scored if x["model"] == model}
        ids = sorted({i for i, _ in look})
        rows = []
        for a, b in (("closed", "rag_top3"), ("rag_top3", "gold_reference"), ("closed", "gold_reference")):
            ab = sum(look[(i, a)] and not look[(i, b)] for i in ids)
            ba = sum(not look[(i, a)] and look[(i, b)] for i in ids)
            p = binomtest(min(ab, ba), ab + ba, 0.5).pvalue if ab + ba else 1.0
            rows.append({"model": model, "a": a, "b": b, "a_only": ab, "b_only": ba, "p": p})
        for r, adj in zip(rows, AR.holm_adjust(r["p"] for r in rows)):
            r["p_holm"] = adj
            out.append(r)
    return out


def main() -> None:
    C.utf8_stdout()
    OUT.mkdir(exist_ok=True)
    items = rebuild_items()
    verify_rebuild(items)
    scored = AR.load_scored()
    orig = {iid: bool(it["strict"]) for iid, it in items.items()}
    orig_ec = {iid: it["error_class"] or "correct" for iid, it in items.items()}

    rec, rec_ec, nowin, alias = {}, {}, {}, {}
    audit = []
    for iid, it in sorted(items.items()):
        ok, fails = record_label(it, {}, window=True)
        rec[iid] = ok
        d = C.J.evidence_result(it["rec"], C.J.load_task(it["run"]["task_id"]), C.J.load_corpus(),
                                it["run"]["condition"], C.J.has_version_note(it["obj"] or {}))
        rec_ec[iid] = "correct" if ok else (d["error_class_candidate"] or "fabricated_quotation")
        nowin[iid] = record_label(it, {}, window=False)[0]
        alias[iid] = record_label(it, {"alias": True}, window=False)[0]
        n_ev = len((it["obj"] or {}).get("evidence") or [])
        audit.append({"item_id": iid, "run_id": it["run_id"], "task_id": it["run"]["task_id"],
                      "condition": it["run"]["condition"], "evidence_in_response": n_ev,
                      "required_evidence": C.J.load_task(it["run"]["task_id"])["required_evidence_count"],
                      "original_label": "correct" if orig[iid] else "error",
                      "original_error_class": orig_ec[iid],
                      "displayed_record_label": "correct" if ok else "error",
                      "displayed_record_failing_fields": fails,
                      "displayed_record_error_class": rec_ec[iid],
                      "label_changed": orig[iid] != ok,
                      "sens_no_window": "correct" if nowin[iid] else "error",
                      "sens_no_window_alias": "correct" if alias[iid] else "error",
                      "shown_speaker": it["speaker_or_narrator"], "shown_locator": it["locator"]})
    with (OUT / "judge_item_audit.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(audit[0]))
        w.writeheader()
        w.writerows(audit)

    variants = [("original (response-level labels, as published)", orig, orig_ec),
                ("primary: displayed-record labels", rec, rec_ec),
                ("sensitivity: + window constraint not imposed", nowin, None),
                ("sensitivity: + window not imposed + Ulysses/Odysseus alias", alias, None)]
    allm = []
    for name, lab, _ in variants:
        for m in metrics(scored, lab, {}):
            allm.append({"variant": name, **m})
    with (OUT / "judge_metrics_relabelled.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(allm[0]))
        w.writeheader()
        w.writerows(allm)

    changed = [a for a in audit if a["label_changed"]]
    md = ["# LLM-judge reference-label audit (post hoc correction)", "",
          "Rebuild check: the 60 items re-derived in memory from `runs/raw/formal/formal_corr.jsonl` with the original "
          "sampling rule match the public `foil_key.csv` on auto_strict, auto_error_class and kind for all 60 items, and "
          "the displayed quote, locator and speaker appear verbatim in every frozen prompt (180 prompts).", "",
          f"Items whose displayed record passes the same verifier although the whole response failed: **{len(changed)}**", "",
          "| item | run | task | cond | evidence in response | original class | displayed-record verdict |",
          "|---|---|---|---|---|---|---|"]
    for a in changed:
        md.append(f"| {a['item_id']} | {a['run_id']} | {a['task_id']} | {a['condition']} | {a['evidence_in_response']} | "
                  f"{a['original_error_class']} | {a['displayed_record_label']} |")
    lab_counts = Counter(rec_ec.values())
    md += ["", f"Primary labels: {sum(rec.values())} correct, {60 - sum(rec.values())} error items; "
           f"error classes {dict(lab_counts)}.", "",
           f"Sensitivity labels: window not imposed → {sum(nowin.values())} correct; "
           f"+ alias → {sum(alias.values())} correct.", ""]
    for name, lab, _ in variants:
        md += [f"## {name}", "",
               "| Judge | Evidence | Strict accuracy [Wilson 95%] | Error acceptance | Correct acceptance | Unsure | Acc. excl. unsure |",
               "|---|---|---|---|---|---|---|"]
        for m in [x for x in allm if x["variant"] == name]:
            md.append(f"| {m['model']} | {m['condition']} | {100*m['strict_accuracy']:.1f}% [{100*m['wilson_lo']:.1f}, {100*m['wilson_hi']:.1f}] | "
                      f"{100*m['error_acceptance']:.1f}% ({m['error_accepted']}/{m['n_error_items']}) | "
                      f"{100*m['correct_acceptance']:.1f}% | {100*m['unsure_rate']:.1f}% | {100*m['accuracy_excl_unsure']:.1f}% |")
        md += ["", "| Judge | Contrast | a only | b only | exact p | Holm p |", "|---|---|---|---|---|---|"]
        for r in mcnemar(scored, lab):
            md.append(f"| {r['model']} | {r['a']} vs {r['b']} | {r['a_only']} | {r['b_only']} | {r['p']:.4f} | {r['p_holm']:.4f} |")
        md.append("")
    # 主口径下 gold-reference 按错误类别的接受率
    md += ["## Primary labels: gold-reference acceptance by error class", "",
           "| Judge | Class | accepted / n |", "|---|---|---|"]
    for model in AR.MODEL_FILES:
        for ec in ("fabricated_quotation", "misattribution", "version_drift", "context_displacement"):
            rows = [x for x in scored if x["model"] == model and x["condition"] == "gold_reference" and rec_ec[x["item_id"]] == ec]
            if rows:
                md.append(f"| {model} | {ec} | {sum(x['verdict']=='accurate' for x in rows)}/{len(rows)} |")
    # 主口径下 RAG 条件按检索命中分层（对应正文 IV-E 的检索分层叙述）
    md += ["", "## Primary labels: RAG top-3 strict accuracy by retrieval hit", "",
           "| Judge | Hit definition | Hit | n | Strict accuracy |", "|---|---|---|---|---|"]
    for model in AR.MODEL_FILES:
        rag = [x for x in scored if x["model"] == model and x["condition"] == "rag_top3"]
        for flag in ("task_gold_hit_at_3", "claim_exact_hit_at_3"):
            for hit in (True, False):
                rows = [x for x in rag if x[flag] is hit]
                k = sum(x["verdict"] == ("accurate" if rec[x["item_id"]] else "inaccurate") for x in rows)
                md.append(f"| {model} | {flag} | {hit} | {len(rows)} | {100*k/len(rows):.1f}% ({k}/{len(rows)}) |")
    (OUT / "judge_label_audit.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("changed", len(changed), [a["item_id"] for a in changed])
    print("->", OUT / "judge_label_audit.md")


if __name__ == "__main__":
    main()
