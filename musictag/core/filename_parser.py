# -*- coding: utf-8 -*-
"""从文件名 / 文件夹结构自动推断标签。

支持常见命名：
  * "艺术家 - 歌曲名.mp3"
  * "03 - 艺术家 - 歌曲名.flac"
  * "03. 歌曲名 (专辑名) [2004].ogg"
  * 文件夹层级: 艺术家/专辑/曲目号 歌曲名.mp3
"""
from __future__ import annotations
import os
import re
from typing import Any, Dict, List

#: 统一分隔符（连字符/破折号/中点等），连字符显式转义避免区间警告
_SEP = r"[\s\u00a0]*[~\u00b7\-\u2013\u2014:：|/\\][\s\u00a0]*"
#: 行内注释、年份等修饰（方括号或圆括号）
_META = re.compile(r"[\s\u00a0]*[\[【(（](?P<meta>[^\]】)）]+)[\]】)）]")

#: 匹配顺序即优先级
PATTERNS: List[re.Pattern] = [
    # 1. 曲目号. 艺术家 - 标题
    re.compile(r"^(?P<track>\d{1,3})[\s\.\-_]+(?P<artist>.+?)" + _SEP + r"(?P<title>.+)$"),
    # 2. 曲目号 - 标题
    re.compile(r"^(?P<track>\d{1,3})" + _SEP + r"(?P<title>.+)$"),
    # 3. 艺术家 - 标题
    re.compile(r"^(?P<artist>.+?)" + _SEP + r"(?P<title>.+)$"),
]

_TRAILING = re.compile(r"\s+[\-\u2013\u2014:：]+\s*$")


def _clean_title(title: str) -> str:
    """剥离标题尾部修饰（如 "xxx - 单曲版"），去掉末尾括号注释。"""
    t = _TRAILING.sub("", title).strip()
    t = re.sub(r"[\s\u00a0]*[\[【(（][^\]】)）]+[\])）]\s*$", "", t).strip()
    return t


def parse_filename(stem: str) -> Dict[str, Any]:
    """解析文件名（不含扩展名），返回部分字段字典。"""
    result: Dict[str, Any] = {}
    name = stem.strip()
    for pat in PATTERNS:
        m = pat.match(name)
        if m:
            g = m.groupdict()
            if g.get("track"):
                result["track"] = str(int(g["track"]))
            if g.get("artist"):
                result["artists"] = [a.strip() for a in re.split(r"[,，&和/]", g["artist"]) if a.strip()]
            if g.get("title"):
                result["title"] = _clean_title(g["title"])
            break
    if not result.get("title"):
        result["title"] = _clean_title(name)
    # 括号/方括号中的年份与专辑
    for m in _META.finditer(name):
        meta = m.group("meta").strip()
        if re.fullmatch(r"(19|20)\d{2}", meta) and not result.get("year"):
            result["year"] = meta
        elif not result.get("album") and 2 <= len(meta) <= 40 and " - " not in meta:
            result["album"] = meta
    return result


def infer_from_path(path: str) -> Dict[str, Any]:
    """结合目录结构推断：专辑文件夹 -> album，上层 -> albumartist，CDx -> disc。"""
    result = parse_filename(os.path.splitext(os.path.basename(path))[0])
    parts = [p for p in os.path.dirname(os.path.abspath(path)).split(os.sep) if p]
    cd_pat = re.compile(r"^(cd|disc|disk)\s*(\d+)$", re.I)
    cd_m = None
    if parts:
        cd_m = cd_pat.match(parts[-1])
    if cd_m:
        result["disc"] = str(int(cd_m.group(2)))
        parts = parts[:-1]
    if len(parts) >= 2:
        folder = parts[-1]
        if not result.get("album"):
            result["album"] = folder
        if len(parts) >= 3 and not result.get("albumartist"):
            result["albumartist"] = parts[-2]
    elif len(parts) == 1 and not result.get("album"):
        result["album"] = parts[0]
    # 文件夹中常见 "艺术家 - 专辑 (2004)" 形式
    album = result.get("album") or ""
    m = re.match(r"^(?P<aa>.+?)\s*[-\u2013\u2014]\s*(?P<al>.+?)(?:\s*[(（]\s*(?P<yr>(19|20)\d{2})\s*[)）])?$", album)
    if m and m.group("aa") and m.group("al"):
        if not result.get("albumartist"):
            result["albumartist"] = m.group("aa")
        result["album"] = m.group("al")
        if m.group("yr") and not result.get("year"):
            result["year"] = m.group("yr")
    return result
