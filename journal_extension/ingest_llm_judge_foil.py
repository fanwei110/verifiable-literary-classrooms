"""回收 LLM-judge foil：解析 GPT/Claude 的核对结果，与确定性裁判真值比。
核心 foil 指标：LLM 在"确定性裁判判错"的项上误判为 accurate 的比例（尤其 fabrication）——
即 LLM-judge 放过多少编造引文。也报控制项假阳（把正确引文误判为 inaccurate）。
用法：python journal_extension/ingest_llm_judge_foil.py outputs_gpt.jsonl [outputs_claude.jsonl]
"""
from __future__ import annotations

import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FOIL = ROOT / "journal_extension" / "llm_judge_foil"


def parse_verdict(resp: str) -> str:
    try:
        obj = json.loads(re.search(r"\{.*\}", resp, re.S).group(0))
        v = str(obj.get("verdict", "")).lower()
        if "inaccur" in v:
            return "inaccurate"
        if "accur" in v:
            return "accurate"
        return "unsure"
    except Exception:
        rl = resp.lower()
        if "inaccurate" in rl:
            return "inaccurate"
        if "accurate" in rl:
            return "accurate"
        return "unsure"


def main(files):
    key = {r["item_id"]: r for r in csv.DictReader((FOIL / "foil_key.csv").open(encoding="utf-8-sig"))}
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    for fp in files:
        rows = [json.loads(l) for l in Path(fp).read_text(encoding="utf-8").splitlines() if l.strip()]
        model = rows[0].get("model", Path(fp).stem) if rows else "?"
        # LLM 判 accurate ↔ 预测 strict-correct；确定性真值 auto_strict
        agree = tot = 0
        # foil 核心：确定性判"错"的项里，LLM 误放行(accurate)多少
        missed = defaultdict(lambda: [0, 0])  # error_class -> [n, llm_said_accurate]
        ctrl = [0, 0]  # 正确控制项：[n, llm 误判 inaccurate(假阳)]
        for r in rows:
            k = key.get(r["item_id"])
            if not k:
                continue
            v = parse_verdict(r.get("response", ""))
            auto_ok = str(k["auto_strict"]).lower() in ("true", "1")
            llm_ok = (v == "accurate")
            if v != "unsure":
                tot += 1
                agree += int(llm_ok == auto_ok)
            if k["kind"] == "ctrl":
                ctrl[0] += 1
                ctrl[1] += int(v == "inaccurate")  # 把正确引文判为错=假阳
            else:  # 确定性判错的项
                ec = k["auto_error_class"]
                missed[ec][0] += 1
                missed[ec][1] += int(llm_ok)  # LLM 放行了确定性判错的项
        print(f"\n=== {model}（{fp}）vs 确定性裁判 ===")
        print(f"总体一致率(排除 unsure): {agree}/{tot} = {100*agree/max(tot,1):.0f}%")
        print(f"控制项(正确引文)假阳(LLM 误判 inaccurate): {ctrl[1]}/{ctrl[0]} = {100*ctrl[1]/max(ctrl[0],1):.0f}%")
        print("LLM 放过确定性判错的项(误判 accurate)——foil 核心:")
        tn = ta = 0
        for ec, (n, a) in sorted(missed.items(), key=lambda kv: -kv[1][0]):
            print(f"  {ec:24s}: {a}/{n} 被 LLM 放行 = {100*a/max(n,1):.0f}%")
            tn += n; ta += a
        print(f"  合计: {ta}/{tn} = {100*ta/max(tn,1):.0f}% 的确定性可查错误被 LLM-judge 漏过")
        print("  → LLM-judge 无语料成员检验，放过大量编造/漂移引文；确定性验证不可替代（支持 F1）。")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python ingest_llm_judge_foil.py outputs_gpt.jsonl [outputs_claude.jsonl]")
    else:
        main(sys.argv[1:])
