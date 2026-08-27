"""judge_zh 对抗验证集：核验中文裁判的假阳/假阴行为（新裁判，须像英文 40 例集一样验证）。
每例构造一个 completion JSON + 期望判定，断言 judge_zh 分类正确。
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from judge_zh import judge_zh  # noqa: E402


def comp(quote, speaker="子（孔子）", work="論語", locator="學而第一", n=1, quote2=None):
    ev = [{"quote": quote, "work": work, "speaker_or_narrator": speaker,
           "locator": locator, "use_in_answer": "x"}]
    if quote2 is not None:
        ev.append({"quote": quote2, "work": work, "speaker_or_narrator": "子（孔子）",
                   "locator": locator, "use_in_answer": "x"})
    return json.dumps({"answer": "a", "evidence": ev, "limits": ""}, ensure_ascii=False)


# (task_id, completion, condition, 期望 strict, 期望 error_class 或 None)
CASES = [
    # 1 正确（简体输出匹配繁体语料）
    ("ZTGU1_T1", comp("学而时习之，不亦说乎"), "C1", True, None),
    # 2 正确（繁体输出）
    ("ZTGU1_T1", comp("學而時習之，不亦說乎"), "C1", True, None),
    # 3 说话人错（学而时习是孔子，标成曾子）→ context_displacement
    ("ZTGU1_T1", comp("学而时习之，不亦说乎", speaker="曾子"), "C1", False, "context_displacement"),
    # 4 捏造（貌似论语实则不在）→ fabricated
    ("ZTGU1_T1", comp("君子坦荡荡，小人长戚戚"), "C1", False, "fabricated_quotation"),
    # 5 太短（子曰仁）→ too_short
    ("ZTGU1_T1", comp("仁"), "C1", False, "too_short_or_format"),
    # 6 版本漂移（一字之差：说→悦，但整体近似）——应 found=False 走 drift/fab
    ("ZTGU1_T1", comp("学而时习之，不亦乐乎"), "C1", False, None),  # 只断言非 strict
    # 7 T2 曾子自省 正确
    ("ZTGU1_T2", comp("吾日三省吾身", speaker="曾子"), "C1", True, None),
    # 8 T2 说话人错（标成孔子）
    ("ZTGU1_T2", comp("吾日三省吾身", speaker="孔子"), "C1", False, "context_displacement"),
    # 9 locator 宽松匹配（"论语·学而" 应算对）
    ("ZTGU1_T2", comp("吾日三省吾身", speaker="曾子", locator="論語·學而"), "C1", True, None),
    # 10 T3 两句都对
    ("ZTGU1_T3", comp("君子务本，本立而道生", speaker="有子", n=2, quote2="巧言令色，鲜矣仁"), "C1", True, None),
    # 11 T3 一句对一句捏造 → 非 strict
    ("ZTGU1_T3", comp("君子务本，本立而道生", speaker="有子", n=2, quote2="学而不思则罔"), "C1", False, None),
    # 12 格式坏（非 JSON）
    ("ZTGU1_T1", "这是一段没有 JSON 的自然语言回答。", "C1", False, "format_failure"),
]


def run():
    passed = 0
    for i, (tid, completion, cond, exp_strict, exp_err) in enumerate(CASES, 1):
        v = judge_zh(tid, completion, condition=cond)
        ok = (bool(v["strict_correct"]) == exp_strict)
        if exp_err is not None and not exp_strict:
            ok = ok and (v.get("error_class_candidate") == exp_err)
        status = "PASS" if ok else "FAIL"
        if ok:
            passed += 1
        else:
            print(f"  [{status}] case {i}: got strict={v['strict_correct']} "
                  f"err={v.get('error_class_candidate')}; expected strict={exp_strict} err={exp_err}")
    print(f"judge_zh 对抗集：{passed}/{len(CASES)} 通过")
    assert passed == len(CASES), "judge_zh 对抗集有失败项"


if __name__ == "__main__":
    run()
    print("OK")
