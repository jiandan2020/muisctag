# -*- coding: utf-8 -*-
"""根据元数据自动重命名 / 整理目录结构。

命名模板支持占位符，例如：
  {artist}/{album}/{track2} {title}.{ext}
  {artists} - {title} [{year}].{ext}

模板中使用 "/" 或 "\\" 可生成多级目录；相对路径在指定根目录下创建。
"""
from __future__ import annotations
import os
import re
from typing import Any, Dict, List, Optional, Tuple

#: Windows 文件名非法字符
_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_TRAILING_DOT = re.compile(r"[. ]+$")
_RESERVED = {"CON", "PRN", "AUX", "NUL", "COM1", "COM2", "COM3", "COM4", "COM5",
             "COM6", "COM7", "COM8", "COM9", "LPT1", "LPT2", "LPT3", "LPT4",
             "LPT5", "LPT6", "LPT7", "LPT8", "LPT9"}

#: 可用占位符及说明
PLACEHOLDERS = {
    "title": "歌曲标题",
    "artists": "艺术家（多艺术家用 , 连接）",
    "artist": "艺术家（第一个）",
    "albumartist": "专辑艺术家",
    "album": "专辑名称",
    "track": "曲目编号（1）",
    "track2": "曲目编号（补零 01）",
    "tracktotal": "总曲数",
    "disc": "碟片编号",
    "disc2": "碟片编号（补零）",
    "disctotal": "总碟数",
    "year": "发行年份",
    "genre": "流派",
    "ext": "扩展名（不含点）",
}


def sanitize_name(name: str) -> str:
    """清理为合法的 Windows 文件名/目录名。"""
    name = _INVALID_CHARS.sub(" ", name)
    name = re.sub(r"\s+", " ", name).strip()
    name = _TRAILING_DOT.sub("", name)
    if not name:
        name = "Unknown"
    if name.upper() in _RESERVED:
        name = f"_{name}"
    return name


def _field(fields: Dict[str, Any], key: str) -> str:
    v = fields.get(key)
    if isinstance(v, list):
        v = ", ".join(str(x) for x in v if x)
    return str(v or "").strip()


def build_relative_path(template: str, fields: Dict[str, Any], ext: str) -> str:
    """按模板生成相对路径（不包含根目录）。"""
    artists = _field(fields, "artists")
    artist = artists.split(",")[0].strip() if artists else _field(fields, "albumartist")
    track = _field(fields, "track")
    tracktotal = _field(fields, "tracktotal")
    disc = _field(fields, "disc")
    disc2 = str(disc).zfill(2) if disc.isdigit() else disc

    def repl(match: re.Match) -> str:
        key = match.group(1)
        if key == "artist":
            return artist
        if key == "artists":
            return artists
        if key == "track2":
            return track.zfill(2) if track.isdigit() else track
        if key == "disc2":
            return disc2
        if key == "ext":
            return ext.lstrip(".")
        return _field(fields, key)

    out = re.sub(r"\{(\w+)\}", repl, template)
    parts = [sanitize_name(p) for p in re.split(r"[\\/]+", out) if p.strip()]
    return os.path.join(*parts) if parts else sanitize_name(artist or "Unknown")


def plan_rename(path: str, fields: Dict[str, Any], template: str,
                root: Optional[str] = None, move: bool = True) -> Tuple[str, str, bool]:
    """计算重命名/移动目标，返回 (源路径, 目标路径, 是否需要变更)。

    模板为纯文件名时（不含 "/"）默认原地重命名；含目录分隔符时若提供 root
    则在其下创建目录结构，否则以文件所在目录为根。
    """
    src = os.path.abspath(path)
    ext = os.path.splitext(src)[1]
    rel = build_relative_path(template, fields, ext)
    if os.sep in rel or (os.altsep and os.altsep in rel):
        base = os.path.abspath(root) if root else os.path.dirname(src)
        dst = os.path.join(base, rel)
    else:
        dst = os.path.join(os.path.dirname(src), rel)
    dst = os.path.abspath(dst)
    if dst.lower() == src.lower():
        return src, dst, False
    if not dst.lower().endswith(ext.lower()):
        dst += ext
    return src, dst, True
