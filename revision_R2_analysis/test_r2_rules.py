"""判定规则的正负反例（回应 R4.1/R4.2）：把冻结 verifier 的已知行为——包括宽松处——
写成可执行的规格，并检验 R2 敏感性规则确实封住了这些宽松处。

用法：python -m pytest revision_R2_analysis/test_r2_rules.py -q
"""
from __future__ import annotations

import r2_common as C

J = C.J


# ---- 归一化（judge.normalize_text）的实际行为 ----
def test_normalization_folds_typographic_variants():
    assert J.normalize_text("“To  be,” or\nnot") == J.normalize_text('"To be," or not') == "to be or not"
    assert J.normalize_text("A—B") == J.normalize_text("A-B") == "a b"
    assert J.normalize_text("Act III / Scene I") == "act iii scene i"


def test_normalization_deletes_non_ascii_letters():
    # 已知局限：非 ASCII 字符被直接删除（不是替换为空格）
    assert J.normalize_text("café") == "caf"
    assert J.normalize_text("To…be") == "tobe"
    assert J.normalize_text("To...be") == "to be"
    # NFKD 敏感性规则修复变音与 U+2026
    assert C.norm_text("Evrémonde", nfkd=True) == C.norm_text("Evremonde", nfkd=True)
    assert C.norm_text("To…be", nfkd=True) == "to be"


# ---- locator 原规则的已知宽松处，以及有序规则 ----
def test_original_locator_rule_known_laxities():
    assert J.locator_match("Chapter 10", "Chapter 1")  # 字符串互为子串
    assert J.locator_match("Act I, Scene III", "Act III, Scene I")  # 无序 token 集合
    assert J.locator_match("Act III, Scene II", "Act III, Scene I")  # 子串
    assert not J.locator_match("Act IV, Scene II", "Act III, Scene I")


def test_ordered_locator_rule_closes_laxities():
    o = C.ordered_locator_match
    assert not o("Chapter 10", "Chapter 1")
    assert not o("Act I, Scene III", "Act III, Scene I")
    assert not o("Act III, Scene II", "Act III, Scene I")
    assert o("Act 3, Scene 1, lines 66-69", "Act III, Scene I")
    assert o("3.1.56", "Act III, Scene I")
    assert o("Book IX, line 210", "Book Ix")


# ---- speaker 规则 ----
def test_speaker_containment_and_alias():
    task = J.load_task("TGU6_T2")
    rec = {"quote": task["expected_evidence"][0]["quote"], "author": task["author"], "work": task["work_title"],
           "locator": task["expected_evidence"][0]["locator"], "speaker_or_narrator": "Odysseus"}
    assert not C.VariantJudge().record(rec, task, "C1")  # 原规则：译名不同即失败
    assert C.VariantJudge(alias=True).record(rec, task, "C1")  # 别名敏感性
    rec2 = dict(rec, speaker_or_narrator="Not Ulysses, but Alcinous")
    assert C.VariantJudge().record(rec2, task, "C1")  # 已知局限：包含式匹配不识别否定


# ---- 省略号片段规则 ----
def test_ellipsis_fragment_rule():
    task = J.load_task("TGU1_T1")
    base = {"author": task["author"], "work": task["work_title"], "locator": "Act III, Scene I",
            "speaker_or_narrator": "Hamlet"}
    q = "To be, or not to be, that is the question ... the slings and arrows of outrageous fortune"
    assert not C.VariantJudge().record(dict(base, quote=q), task, "C1")
    assert C.VariantJudge(ellipsis=True).record(dict(base, quote=q), task, "C1")
    # 片段过短不放宽
    assert not C.VariantJudge(ellipsis=True).record(dict(base, quote="To be ... question"), task, "C1")
    # 片段顺序颠倒不通过
    rev = "the slings and arrows of outrageous fortune ... To be, or not to be, that is the question"
    assert not C.VariantJudge(ellipsis=True).record(dict(base, quote=rev), task, "C1")
    # 末尾省略号在原规则下即已通过
    assert C.VariantJudge().record(dict(base, quote="To be, or not to be, that is the question..."), task, "C1")
