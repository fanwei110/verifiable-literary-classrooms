"""R2 返修（Access-2026-43510）离线分析的公共层。

只读冻结日志与语料，不调用任何模型。所有新口径都是"同一批已观察输出在新规则下的
通过情况"，不是用新 verifier 在线重跑的结果（停止规则与反馈会随之改变，无法回放）。

内容：
- load_primary(): 确认集主样本（ext_e1c_m{1..4}，arm == F3，排除开发任务 TGU2/TGU4，
  k=0），即正文 1,319 观测 / 12 个任务簇的样本。
- VariantJudge: 可配置的判定器。所有开关关闭时必须逐条复现日志中的 k0_strict
  （check_anchor() 断言），这是任何新口径可信的前提。
- grounding_effect(): 正文口径的 grounding 效应——12 个任务各自
  (C3,C4 通过率 − C1,C2 通过率) 的均值，并按任务做簇自助百分位区间。

变体规则在看任何结果之前写定，见 VariantJudge 的 docstring；不因结果调整。
"""
from __future__ import annotations

import json
import random
import re
import string
import sys
import unicodedata
from collections import defaultdict
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))
sys.path.insert(0, str(ROOT / "journal_extension"))

import judge as J  # noqa: E402
import apply_corrections  # noqa: E402

apply_corrections.patch(J)  # 与正文一致：注入已核验的 gold-locator 修正层

DEV = {"TGU2", "TGU4"}
PRIMARY_TAGS = ["e1c_m1", "e1c_m2", "e1c_m3", "e1c_m4"]
GROUNDED = {"C3", "C4"}
UNGROUNDED = {"C1", "C2"}
BOOT_N = 2000
BOOT_SEED = 20260823  # 与 R1 GEE 附录同一种子；主口径复现正文 CI [21, 63]


def utf8_stdout() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def load_primary() -> list[dict]:
    """确认集主样本：每个 group 取 F3 臂记录（各臂共享同一个 k=0，取一臂即去重）。"""
    rows = []
    for tag in PRIMARY_TAGS:
        for r in read_jsonl(ROOT / "runs" / "raw" / f"ext_{tag}" / f"{tag}.jsonl"):
            if r.get("arm") == "F3" and r["task_id"].split("_")[0] not in DEV:
                rows.append(r)
    return rows


# ---------------------------------------------------------------- 归一化变体
_KEEP = set(string.ascii_lowercase + string.digits)
_PUNCT = set(string.punctuation)
_ELLIPSIS_RE = re.compile(r"(?:\.\s*){3,}|…")


def norm_text(text: str, nfkd: bool) -> str:
    """nfkd=False 时与 judge.normalize_text 逐字相同；nfkd=True 时先做 NFKD 去组合附加符，
    并把 U+2026 视作分隔符（而非静默删除）。"""
    text = text or ""
    if nfkd:
        text = text.replace("…", " ")
        text = "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch))
    for src, dst in {"‘": "'", "’": "'", "“": '"', "”": '"', "—": "-", "–": "-"}.items():
        text = text.replace(src, dst)
    keep = []
    for ch in text.lower():
        if ch in _KEEP:
            keep.append(ch)
        elif ch.isspace() or ch in _PUNCT:
            keep.append(" ")
    return re.sub(r"\s+", " ", "".join(keep)).strip()


@lru_cache(maxsize=None)
def _norm_cached(text: str, nfkd: bool) -> str:
    return norm_text(text, nfkd)


# ---------------------------------------------------------------- locator 变体
def ordered_locator_match(claimed: str, gold: str) -> bool:
    """有序数字规则：金标准 locator 的数字序列（罗马数字已转阿拉伯）必须是自报 locator
    数字序列的前缀。例：gold Act III, Scene I → (3,1)；自报 '3.1.56' → (3,1,56) 通过；
    'Act I, Scene III' → (1,3) 不通过；'Chapter 3' 对 gold 'Chapter 36' 不通过。"""
    def nums(s: str) -> tuple:
        return tuple(int(t) for t in J.canonical_locator(s).split() if t.isdigit())
    g, c = nums(gold), nums(claimed)
    if not g:
        return J.locator_match(claimed, gold)
    return c[: len(g)] == g


# ---------------------------------------------------------------- 判定器
SPEAKER_ALIASES = {"ulysses": ["odysseus"]}  # Butler 译本的拉丁化人名；只此一条，预先写定


class VariantJudge:
    """可配置判定器。

    level:
      'L0'     语料成员关系（引文在该作品冻结语料中出现），不参照任务策展证据
      'L1'     L0 + 作者、作品与任务元数据一致，不参照任务策展证据
      'L2'     L1 + speaker + （C3/C4）窗口归属；去掉 locator（即正文 67% vs 27% 反事实）
      'strict' 正文主口径：L2 + locator
    开关（均为敏感性，主口径全部关闭）：
      alias      speaker 接受 SPEAKER_ALIASES 中的译名别名
      ordered    locator 用 ordered_locator_match 代替原规则
      ellipsis   引文内部省略号（前后都有文本）时按片段匹配：每片段归一化后 ≥3 词，
                 所有片段须在同一 segment 内按序出现，相邻片段间隔 ≤ MAX_GAP 个归一化字符；
                 C3/C4 的窗口归属同样按片段、按序判定
      nfkd       NFKD 去变音并把 U+2026 视作分隔符
    """

    MAX_GAP = 300

    def __init__(self, level="strict", alias=False, ordered=False, ellipsis=False, nfkd=False):
        self.level, self.alias, self.ordered, self.ellipsis, self.nfkd = level, alias, ordered, ellipsis, nfkd
        self.corpus = J.load_corpus()
        self._tasks: dict = {}

    def task(self, tid):
        if tid not in self._tasks:
            self._tasks[tid] = J.load_task(tid)
        return self._tasks[tid]

    def n(self, s):
        return _norm_cached(s or "", self.nfkd)

    # 片段化：仅内部省略号触发
    def fragments(self, quote: str) -> list[str] | None:
        if not self.ellipsis:
            return None
        parts = [p for p in _ELLIPSIS_RE.split(quote or "")]
        parts = [self.n(p) for p in parts]
        inner = [p for p in parts if p]
        if len(inner) < 2:
            return None
        if any(len(p.split()) < 3 for p in inner):
            return []  # 有内部省略但片段过短：不放宽，按失配处理
        return inner

    def frags_in(self, frags: list[str], hay: str) -> bool:
        pos = 0
        first = True
        for f in frags:
            i = hay.find(f, pos)
            if i < 0:
                return False
            if not first and i - pos > self.MAX_GAP:
                return False
            pos, first = i + len(f), False
        return True

    def contains(self, quote: str, hay_raw: str) -> bool:
        hay = self.n(hay_raw)
        frags = self.fragments(quote)
        if frags is None:
            nq = self.n(quote)
            return bool(nq) and nq in hay
        return bool(frags) and self.frags_in(frags, hay)

    def found(self, quote, work) -> bool:
        if not self.n(quote):
            return False
        if any(self.contains(quote, seg["text"]) for seg in work["segments"]):
            return True
        frags = self.fragments(quote)
        if frags is None:  # 与 judge.find_in_segments 一致：整书回退
            return self.contains(quote, work["clean_text"])
        return False  # 片段匹配只在同一 segment 内认可，不做整书回退

    def record(self, rec: dict, task: dict, condition: str) -> bool:
        work = self.corpus[task["work_id"]]
        quote = str(rec.get("quote", ""))
        if not self.found(quote, work):
            return False
        if self.level == "L0":
            return True
        author_ok = J.normalize_name(str(rec.get("author", ""))) == J.normalize_name(task["author"])
        work_ok = J.normalize_name(str(rec.get("work", ""))) == J.normalize_name(task["work_title"])
        if not (author_ok and work_ok):
            return False
        if self.level == "L1":
            return True
        # 与 judge.evidence_result 相同的策展证据映射（含无下限的 approx 回退）
        frags = self.fragments(quote)
        nq = self.n(quote) if frags is None else " ".join(frags)
        matched = None
        for ev in task["expected_evidence"]:
            ne = self.n(ev["quote"])
            if frags is None:
                hit = ne in nq or nq in ne
            else:
                hit = any(f in ne or ne in f for f in frags)
            if hit:
                matched = ev
                break
        if matched is None:
            best = 0.0
            for ev in task["expected_evidence"]:
                s = SequenceMatcher(None, nq, self.n(ev["quote"])).ratio()
                if s > best:
                    best, matched = s, ev
        if matched is None:
            return False
        claimed_sp = J.normalize_name(str(rec.get("speaker_or_narrator", "")))
        gold_sp = J.normalize_name(matched["speaker_or_narrator"])
        names = [gold_sp] + (SPEAKER_ALIASES.get(gold_sp, []) if self.alias else [])
        speaker_ok = any(nm in claimed_sp for nm in names)
        grounded_ok = True
        if condition in GROUNDED:
            grounded_ok = self.contains(quote, matched["source_window"])
        if not (speaker_ok and grounded_ok):
            return False
        if self.level == "L2":
            return True
        claimed_loc = str(rec.get("locator", ""))
        if self.ordered:
            return ordered_locator_match(claimed_loc, matched["locator"])
        return J.locator_match(claimed_loc, matched["locator"])

    def completion(self, task_id: str, text: str, condition: str) -> bool:
        task = self.task(task_id)
        obj, _ = J.extract_json_object(text)
        if obj is None:
            return False
        ev = obj.get("evidence")
        k = task["required_evidence_count"]
        if not isinstance(ev, list) or len(ev) < k:
            return False
        recs = [r for r in ev[:k] if isinstance(r, dict)]
        if len(recs) < k:
            return False
        return all(self.record(r, task, condition) for r in recs)

    def k0(self, row: dict) -> bool:
        return self.completion(row["task_id"], row["rounds"][0]["completion"], row["condition"])


def check_anchor(rows: list[dict]) -> int:
    """主口径、全部开关关闭时，变体判定器必须逐条复现日志 k0_strict。返回不一致条数。"""
    vj = VariantJudge()
    bad = sum(1 for r in rows if vj.k0(r) != bool(r["k0_strict"]))
    assert bad == 0, f"VariantJudge 未能复现冻结 k0_strict：{bad} 处不一致"
    return bad


# ---------------------------------------------------------------- 效应与区间
def task_diffs(rows: list[dict], outcome: dict) -> dict[str, float]:
    """outcome: run_id -> 0/1。返回每个任务的 grounded − ungrounded 通过率差（百分点）。"""
    by = defaultdict(lambda: {"g": [], "u": []})
    for r in rows:
        by[r["task_id"]]["g" if r["condition"] in GROUNDED else "u"].append(outcome[r["run_id"]])
    return {t: 100 * (sum(d["g"]) / len(d["g"]) - sum(d["u"]) / len(d["u"]))
            for t, d in sorted(by.items()) if d["g"] and d["u"]}


def boot_mean(values: list[float], n=BOOT_N, seed=BOOT_SEED) -> tuple[float, float, float]:
    """任务簇自助：对任务层数值有放回重抽，取均值的 2.5/97.5 百分位。"""
    rng = random.Random(seed)
    k = len(values)
    point = sum(values) / k
    bs = sorted(sum(rng.choice(values) for _ in range(k)) / k for _ in range(n))
    return point, bs[int(0.025 * n)], bs[int(0.975 * n) - 1]


def grounding_effect(rows, outcome):
    d = task_diffs(rows, outcome)
    return (*boot_mean(list(d.values())), d)


def wilson(k: int, n: int, z: float = 1.959964) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / den
    return c - h, c + h
