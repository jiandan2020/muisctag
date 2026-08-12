# -*- coding: utf-8 -*-
"""标签清理与标准化。

功能：
  * 去除多余空格 / 零宽字符 / 统一 Unicode 规范化（NFC）
  * 统一 "Feat." 写法
  * 英文标题大小写规范化（可关闭）
  * 繁简转换（依赖可选的 opencc，缺失时跳过）
"""
from __future__ import annotations
import re
import unicodedata
from typing import Any, Dict, List

#: "featuring" 系列写法的统一替换
_FEAT_PATTERNS = [
    (re.compile(r"\s*[\(\[]?\s*(?:feat\.?|ft\.?|featuring)\s*[:：]?\s*", re.I), " feat. "),
    (re.compile(r"\s*[\(\[]?\s*(?:feat\.?|ft\.?|featuring)\s*[\)\]]\s*$", re.I), ""),
]
_FEAT_NORMALIZE = re.compile(r"(\s*feat\.\s+)", re.I)

#: 需要保留大小写的词（英文常见缩写/冠词）
_KEEP_CASE = {"feat.", "ft.", "vs.", "dj", "mc", "mv", "cd", "dvd", "vol", "pt", "no", "ac", "dc"}


def _opencc_available() -> bool:
    try:
        import opencc  # noqa: F401
        return True
    except Exception:
        return False


_HAS_OPENCC = _opencc_available()


def normalize_unicode(text: str) -> str:
    """Unicode NFC 规范化并去掉零宽字符。"""
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"[\u200b\u200c\u200d\ufeff\u2060]", "", text)
    return text


def collapse_whitespace(text: str) -> str:
    """压缩连续空白为单个空格。"""
    return re.sub(r"\s+", " ", text).strip()


def standardize_feat(text: str) -> str:
    """把 feat./ft./featuring 统一为 "feat." 格式。"""
    t = text
    for pat, repl in _FEAT_PATTERNS:
        t = pat.sub(repl, t)
    t = re.sub(r"feat\.\s*\.", "feat.", t, flags=re.I)
    return t


def title_case(text: str) -> str:
    """英文标题式大小写：每个词的实词首字母大写，保留中文原样。"""
    def cap_word(word: str) -> str:
        if word.lower() in _KEEP_CASE:
            return word
        if re.fullmatch(r"[A-Za-z0-9'\-]+", word):
            return word[:1].upper() + word[1:].lower()
        return word
    words = text.split(" ")
    out = []
    for i, w in enumerate(words):
        lower = w.lower()
        # 冠词/介词/连词在非首尾位置保持小写
        if lower in {"a", "an", "the", "and", "or", "but", "of", "for", "to",
                     "in", "on", "at", "by", "with", "from", "as"} and 0 < i < len(words) - 1:
            out.append(w.lower())
        else:
            out.append(cap_word(w))
    return " ".join(out)


def to_simplified(text: str) -> str:
    """繁转简（需安装 opencc-python-reimplemented）。"""
    if not _HAS_OPENCC:
        return text
    try:
        import opencc
        converter = opencc.OpenCC("t2s")
        return converter.convert(text)
    except Exception:
        return text


def to_traditional(text: str) -> str:
    """简转繁（需安装 opencc-python-reimplemented）。"""
    if not _HAS_OPENCC:
        return text
    try:
        import opencc
        converter = opencc.OpenCC("s2t")
        return converter.convert(text)
    except Exception:
        return text


def clean_fields(fields: Dict[str, Any], options: Dict[str, bool]) -> Dict[str, Any]:
    """按选项清理一张字段字典，返回新字典（不修改原字典）。

    options 可用键：
      trim           去首尾/压缩空格（默认 True）
      nfc            Unicode NFC 规范化（默认 True）
      feat           统一 feat. 写法（默认 True）
      title_case     英文标题式大小写（默认 False）
      chinese        繁简转换: "" / "s2t" / "t2s"（默认 ""）
    """
    out: Dict[str, Any] = dict(fields)
    trim = options.get("trim", True)
    nfc = options.get("nfc", True)
    feat = options.get("feat", True)
    title = options.get("title_case", False)
    zh = options.get("chinese", "")

    def clean(value: str) -> str:
        v = value or ""
        if nfc:
            v = normalize_unicode(v)
        if trim:
            v = collapse_whitespace(v)
        if feat and v:
            v = standardize_feat(v)
        if title and v:
            v = title_case(v)
        if zh == "s2t" and v:
            v = to_traditional(v)
        elif zh == "t2s" and v:
            v = to_simplified(v)
        return v

    from .metadata import TEXT_FIELDS, LIST_FIELDS
    for k in TEXT_FIELDS:
        if k in out:
            out[k] = clean(str(out[k] or ""))
    for k in LIST_FIELDS:
        out[k] = [x for x in (clean(str(v)) for v in (out.get(k) or [])) if x]
    # 年份/编号规范化：去除内部空格
    for k in ("track", "tracktotal", "disc", "disctotal", "bpm", "year"):
        if out.get(k):
            out[k] = str(out[k]).strip()
    return out
