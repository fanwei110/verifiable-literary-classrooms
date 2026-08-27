"""中文规范化（judge_zh 与 corpus 构建共用）。
三步：繁→简(OpenCC t2s) → 去标点(中英文标点全去) → 去空白。
镜像英文 judge 的"去标点+去空白+统一大小写"，但针对中文：核心是繁简统一 + 标点/句读剥离，
使模型的简体、不同标点、异体字输出能与繁体语料做子串匹配。
"""
from __future__ import annotations

import re

from opencc import OpenCC

_T2S = OpenCC("t2s")  # 繁→简

# 中英文标点、引号、书名号、间隔号、破折号、省略号等——匹配时一律剥离
_PUNCT = (
    "，。；：？！、（）《》〈〉「」『』【】〔〕·—…～“”‘’\"'"
    ".,;:?!()<>[]{}/\\|-_=+*&^%$#@~`　 \t\n\r"
)
_PUNCT_RE = re.compile("[" + re.escape(_PUNCT) + "]+")


def normalize_zh(text: str) -> str:
    """繁→简 → 去标点 → 去空白 → 小写（对夹杂的拉丁字母）。"""
    if not text:
        return ""
    s = _T2S.convert(str(text))
    s = _PUNCT_RE.sub("", s)
    return s.lower()


def zh_len(text: str) -> int:
    """规范化后的字符数（用于最短引文规则）。"""
    return len(normalize_zh(text))
