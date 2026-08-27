"""repair_loop 零 API 单元测试：反馈构造、信息封顶、prompt 路径、judge 集成。"""
import json
import sys
from pathlib import Path

import pytest

EXT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EXT))

import repair_loop as rl  # noqa: E402


TASK = rl.load_task("TGU1_T1")  # Hamlet / To be or not to be / Act III Scene I / Hamlet


def make_verdict(completion: str) -> dict:
    return rl.judge_mod.judge("TGU1_T1", completion, condition="C1")


FAB_COMPLETION = json.dumps({
    "answer": "A line about hesitation.",
    "evidence": [{
        "quote": "To hesitate is to die a little every day",   # 编造
        "author": "William Shakespeare",
        "work": "Hamlet",
        "locator": "Act II, Scene II",
        "speaker_or_narrator": "Polonius",
        "use": "explains hesitation",
    }],
    "limits": "none",
})


def test_judge_integration_fabrication():
    v = make_verdict(FAB_COMPLETION)
    assert v["strict_correct"] is False
    assert v["error_class_candidate"] == "fabricated_quotation"


def test_feedback_tiers_no_leak():
    v = make_verdict(FAB_COMPLETION)
    for tier in ("F1", "F2", "F3"):
        fb = rl.build_feedback(tier, v, TASK)
        rl.assert_no_leak(fb, TASK)          # 不得抛异常
        assert "To be, or not to be" not in fb
        assert "Act III" not in fb
    f2 = rl.build_feedback("F2", v, TASK)
    assert "fabricated_quotation" in f2
    f3 = rl.build_feedback("F3", v, TASK)
    assert "quoted string itself was not found" in f3


def test_leak_guard_catches_locator_and_quote():
    with pytest.raises(RuntimeError, match="LEAK"):
        rl.assert_no_leak("hint: check Act III, Scene I", TASK)
    with pytest.raises(RuntimeError, match="LEAK"):
        rl.assert_no_leak("the line is 'To be, or not to be, that is the q'", TASK)


def test_oracle_f4_contains_answer_and_is_flagged_only_for_f4():
    v = make_verdict(FAB_COMPLETION)
    f4 = rl.build_feedback("F4", v, TASK)
    assert "To be, or not to be" in f4      # oracle 臂应含正确值
    with pytest.raises(RuntimeError):
        rl.assert_no_leak(f4, TASK)          # 同一守卫必须能识别它是泄漏级内容


def test_prompt_paths_exist_for_dev_tasks():
    for t in ("TGU2_T1", "TGU2_T2", "TGU2_T3", "TGU4_T1", "TGU4_T2", "TGU4_T3"):
        for c in ("C1", "C2", "C3", "C4"):
            variant = "A" if c in ("C1", "C3") else "canonical"
            p = rl.prompt_path(c, t, variant)
            assert p.exists(), p


def test_history_truncation_keeps_original_prompt():
    msgs = [{"role": "user", "content": "ORIGINAL" + "x" * 20000},
            {"role": "assistant", "content": "y" * 20000},
            {"role": "user", "content": "fb1"},
            {"role": "assistant", "content": "z" * 20000},
            {"role": "user", "content": "fb2"}]
    kept, truncated = rl.truncate_history(msgs)
    assert truncated and kept[0]["content"].startswith("ORIGINAL") and kept[-1]["content"] == "fb2"


def test_build_groups_unique_ids():
    groups = rl.build_groups(["TGU2_T1"], ["C1", "C3"], ["M2", "M4"], 3)
    ids = [g["group_id"] for g in groups]
    assert len(ids) == len(set(ids)) == 2 * 2 * 3
