"""补证 A4：gold-locator 全审计（零 API）。

回应"locator 修正是否穷尽"的致命攻击：对全部英文 gold 证据项，用冻结语料自身的
结构标记（BOOK/ACT/SCENE/CHAPTER 的大写标题）反推每条引文真实所在的规范 locator，
与 task YAML 里声称的 gold locator（修正前 / 修正后）逐条核对。

方法（全部相对冻结语料，不用模型记忆）：
1. 成员性：用 harness.judge.find_in_segments 判断 gold 引文是否为语料子串。
2. 真值 locator：在 raw clean_text 里正则找大写结构标题（如 'BOOK I.'、'ACT III'、
   'CHAPTER XI'），记其字符位置；用 gold 引文的前若干词构成弹性正则定位引文起点；
   取该位置之前最近的标题（戏剧取最近 ACT+最近 SCENE）作为真值 locator。
3. 一致性：canonical_locator（罗马数字→整数）后比对 gold(修正前) / gold(修正后) 与真值。

输出：每条一行审计结果 + 汇总（已知修正命中数 / 残余新缺陷数）。
用法：python journal_extension/gold_locator_audit.py    # 退出码 0=通过，1=验收失败
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "harness"))
sys.path.insert(0, str(ROOT / "journal_extension"))

import judge as judge_mod  # noqa: E402
import apply_corrections  # noqa: E402

apply_corrections.patch(judge_mod)  # 用修正后的 gold 做"修正后"一列

CORPUS = judge_mod.load_corpus()
TASK_DIR = ROOT / "tasks"

# 大写结构标题（heading），避免匹配散文里的小写 act/book
MARKER_RE = re.compile(r"\b(BOOK|ACT|SCENE|CHAPTER)\s+([IVXLCDM]+|\d+)\b")


def canon(s: str) -> str:
    return judge_mod.canonical_locator(s or "")


def find_markers(raw: str):
    """返回 [(pos, kind, canon_locator)]，kind in BOOK/ACT/SCENE/CHAPTER。"""
    out = []
    for m in MARKER_RE.finditer(raw):
        kind = m.group(1)
        num = canon(m.group(2))  # 罗马→整数
        out.append((m.start(), kind, num))
    return out


def locate_quote(raw: str, quote: str) -> int | None:
    """用 gold 引文前若干 alnum 词构弹性正则，在 raw clean_text 找引文起点。"""
    toks = re.findall(r"[A-Za-z0-9]+", quote)
    if not toks:
        return None
    toks = toks[:8]
    pat = r"\W+".join(re.escape(t) for t in toks)
    m = re.search(pat, raw, re.IGNORECASE)
    return m.start() if m else None


def true_locator(work_id: str, quote: str, mode: str) -> str | None:
    """引文位置之前最近的结构标题。戏剧=最近 ACT+最近 SCENE。
    chapter 模式兜底：若引文之前无章标题（首章标题在清洗中丢失/引文在书题区），
    用其后第一个 CHAPTER N 反推——引文属第 N-1 章（N≥2）或首章区（N=1→Ch 1）。"""
    raw = CORPUS[work_id]["clean_text"]
    pos = locate_quote(raw, quote)
    if pos is None:
        return None
    all_markers = find_markers(raw)
    before = [mk for mk in all_markers if mk[0] <= pos]
    if mode == "drama":
        acts = [mk for mk in before if mk[1] == "ACT"]
        scenes = [mk for mk in before if mk[1] == "SCENE"]
        if not acts or not scenes:
            return None
        return f"Act {acts[-1][2]}, Scene {scenes[-1][2]}"
    if mode == "book":
        books = [mk for mk in before if mk[1] == "BOOK"]
        return f"Book {books[-1][2]}" if books else None
    if mode == "chapter":
        chaps = [mk for mk in before if mk[1] == "CHAPTER"]
        if chaps:
            return f"Chapter {chaps[-1][2]}"
        # 兜底：引文之前无章标题 → 看其后第一个章标题
        after = [mk for mk in all_markers if mk[1] == "CHAPTER" and mk[0] > pos]
        if after:
            try:
                nxt = int(after[0][2])
                return f"Chapter {max(1, nxt - 1)}"
            except ValueError:
                return None
        return None
    return None


# --- 验收检查模式（acceptance check）---------------------------------------
# 本脚本既是一次性审计报告，也是可对语料扩展运行的验收检查：
#   - 任一 gold 项出现成员性失败、修正后仍不符、或无法判定 → 进程以非零码退出；
#   - 语料若含未在 MODE 中登记结构模式的新作品 → 同样判失败，不静默放行。
# 因此可直接挂进 CI 或发布前脚本；退出码 0 = 通过，1 = 失败。
# Windows 控制台默认 GBK 会在打印 √/★ 时抛 UnicodeEncodeError，故此处显式转 UTF-8。
import io as _io
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

MODE = {
    "hamlet": "drama", "macbeth": "drama",
    "pride_prejudice": "chapter", "tale_two_cities": "chapter",
    "paradise_lost": "book", "odyssey_butler": "book",
}

# 修正前的原始 gold（不打补丁），用 orig load_task
_orig_load = judge_mod.load_task.__wrapped__ if hasattr(judge_mod.load_task, "__wrapped__") else None


def raw_task(task_id: str) -> dict:
    """直接读 YAML 拿修正前 gold。"""
    return yaml.safe_load((TASK_DIR / f"{task_id}.yaml").read_text(encoding="utf-8"))


def main():
    tasks = sorted(p.stem for p in TASK_DIR.glob("TGU*_T*.yaml"))
    n_items = 0
    n_member_fail = 0
    n_mismatch_before = 0  # 修正前 gold 与真值不符
    n_mismatch_after = 0   # 修正后仍不符（=残余缺陷）
    n_uncertain = 0
    n_unsupported = 0
    unsupported_works = set()
    rows = []
    for tid in tasks:
        raw = raw_task(tid)                       # 修正前
        patched = judge_mod.load_task(tid)        # 修正后
        work = raw["work_id"]
        mode = MODE.get(work)
        if mode is None:
            # 新作品未登记结构模式：无法独立重导 locator，按验收失败处理，不静默放行
            n_unsupported += 1
            unsupported_works.add(work)
            mode = "?"
        for i, ev in enumerate(raw["expected_evidence"]):
            n_items += 1
            quote = ev["quote"]
            gold_before = ev.get("locator", "")
            gold_after = patched["expected_evidence"][i].get("locator", "")
            # 成员性
            found = judge_mod.find_in_segments(quote, CORPUS[work])
            member = found is not None
            if not member:
                n_member_fail += 1
            # 真值 locator
            truth = true_locator(work, quote, mode)
            if truth is None:
                n_uncertain += 1
                verdict = "UNCERTAIN(无标题锚)"
            else:
                ok_before = judge_mod.locator_match(gold_before, truth)
                ok_after = judge_mod.locator_match(gold_after, truth)
                if not ok_before:
                    n_mismatch_before += 1
                if not ok_after:
                    n_mismatch_after += 1
                if ok_after and not ok_before:
                    verdict = "已修复✓"
                elif ok_after and ok_before:
                    verdict = "本就正确✓"
                else:
                    verdict = "★残余缺陷★"
            rows.append((tid, i, work, quote[:34], gold_before, gold_after, truth, verdict, member))

    print(f"{'task':10} {'#':2} {'work':16} {'quote':36} {'gold前':14} {'gold后':14} {'真值':16} {'判定':14} member")
    print("-" * 150)
    for r in rows:
        print(f"{r[0]:10} {r[1]:<2} {r[2]:16} {r[3]:36} {str(r[4]):14} {str(r[5]):14} {str(r[6]):16} {r[7]:14} {r[8]}")
    print("-" * 150)
    print(f"gold 证据项总数        : {n_items}")
    print(f"成员性失败(引文不在语料): {n_member_fail}")
    print(f"修正前 locator 不符    : {n_mismatch_before}  (= 应被修正的缺陷数)")
    print(f"修正后 locator 仍不符  : {n_mismatch_after}  (= ★残余新缺陷★)")
    print(f"无标题锚无法判定       : {n_uncertain}")
    print(f"已登记修正条数(json)   : {apply_corrections.n_corrections()}")
    print(f"未登记结构模式的作品   : {n_unsupported}"
          + (f"  {sorted(unsupported_works)}" if unsupported_works else ""))

    # --- 验收判定 ---------------------------------------------------------
    # 通过条件：无成员性失败、无残余不符、无不可判定项、无未登记作品。
    # 修正前不符（n_mismatch_before）不计入失败——那正是本层已修好的已知缺陷。
    failures = []
    if n_member_fail:
        failures.append(f"{n_member_fail} 项引文不在冻结语料中")
    if n_mismatch_after:
        failures.append(f"{n_mismatch_after} 项修正后 locator 仍不符")
    if n_uncertain:
        failures.append(f"{n_uncertain} 项无标题锚、无法独立重导")
    if n_unsupported:
        failures.append(f"{n_unsupported} 项属未登记结构模式的作品 {sorted(unsupported_works)}")

    print("-" * 150)
    if failures:
        print("ACCEPTANCE CHECK: FAILED")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("ACCEPTANCE CHECK: PASSED"
          f"  ({n_items} 项全部可独立重导且与 gold 一致)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
