# -*- coding: utf-8 -*-
"""多格式歌词解析器。

支持：LRC（逐行 / 逐字增强型）、YRC（QQ 逐字）、QRC（QQ 加密）、
KRC（酷狗加密）、SRT、ASS、TTML、纯文本。

解析结果统一为 lyrics.model.Lyrics。
"""
from __future__ import annotations
import base64
import re
import xml.etree.ElementTree as ET
import zlib
from typing import List, Optional

from .model import LyricLine, LyricWord, Lyrics

_TIME_RE = re.compile(r"(?:(\d+):)?(\d{1,2}):(\d{1,2})(?:[.,](\d{1,3}))?")
_WORD_RE = re.compile(r"<(\d{1,2}):(\d{1,2})(?:[.,](\d{1,3}))?>([^<]*)")
_OFFSET_RE = re.compile(r"\[offset:\s*(-?\d+)\s*\]", re.I)


def _time_to_ms(h: str, m: str, s: str, frac: str = "") -> int:
    ms = int(h or 0) * 3600000 + int(m) * 60000 + int(s) * 1000
    if frac:
        frac = frac.ljust(3, "0")[:3]
        ms += int(frac)
    return ms


def _parse_time_text(text: str) -> Optional[int]:
    """解析 "mm:ss.xx" 或 "HH:MM:SS,mmm"。"""
    m = _TIME_RE.search(text)
    if not m:
        return None
    return _time_to_ms(m.group(1), m.group(2), m.group(3), m.group(4))


# ---------------------------------------------------------------------------
# LRC / 增强型 LRC / YRC
# ---------------------------------------------------------------------------

_TOK_RE = re.compile(
    r"\[(\d{1,2}):(\d{1,2})(?:[.,](\d{1,3}))?\]"
    r"|<(\d{1,2}):(\d{1,2})(?:[.,](\d{1,3}))?>"
)


def _tok_time(tok: re.Match) -> int:
    """提取 token 时间（毫秒）。LRC 使用 mm:ss.xx（无小时位）。"""
    if tok.group(0).startswith("["):
        return _time_to_ms("", tok.group(1), tok.group(2), tok.group(3))
    return _time_to_ms("", tok.group(4), tok.group(5), tok.group(6))


def parse_lrc(text: str) -> Lyrics:
    """解析 LRC（含增强型逐字时间戳 <mm:ss.xx> 与 [offset:]）。

    [mm:ss.xx]       行时间戳
    <mm:ss.xx>字     逐字时间戳（其后文本属于该字）
    [offset:500]     整体偏移（毫秒）
    [ti:标题] 等     元数据
    """
    lyrics = Lyrics()
    offset = 0
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        m = _OFFSET_RE.search(line)
        if m:
            offset = int(m.group(1))
            continue
        tokens = list(_TOK_RE.finditer(line))
        if not tokens:
            # 无时间戳 -> 元数据行
            if line.startswith("[") and line.endswith("]") and ":" in line[1:-1]:
                key, _, val = line[1:-1].partition(":")
                lyrics.meta[key.strip().lower()] = val.strip()
            continue
        line_time = None
        words: List[LyricWord] = []
        frags: List[str] = []
        for i, tok in enumerate(tokens):
            seg_start = tok.end()
            seg_end = tokens[i + 1].start() if i + 1 < len(tokens) else len(line)
            frag = line[seg_start:seg_end]
            if tok.group(0).startswith("["):
                if line_time is None:
                    line_time = _tok_time(tok) + offset
            elif frag:
                words.append(LyricWord(time_ms=_tok_time(tok) + offset, text=frag))
            frags.append(frag)
        if line_time is None:
            continue
        text = "".join(frags).strip()
        if text:
            lyrics.lines.append(LyricLine(time_ms=line_time, text=text, words=words))
    lyrics.meta.setdefault("offset", str(offset))
    return lyrics


# ---------------------------------------------------------------------------
# SRT
# ---------------------------------------------------------------------------

def parse_srt(text: str) -> Lyrics:
    """解析 SRT（字幕格式）。"""
    lyrics = Lyrics()
    blocks = re.split(r"\n\s*\n", text.strip())
    for block in blocks:
        lines = [l.strip() for l in block.splitlines() if l.strip()]
        if len(lines) < 2:
            continue
        time_idx = next((i for i, l in enumerate(lines) if "-->" in l), None)
        if time_idx is None or time_idx + 1 >= len(lines):
            continue
        m = re.search(r"(\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})\s*-->\s*(\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})", lines[time_idx])
        if not m:
            continue
        start = _parse_time_text(m.group(1)) or 0
        end = _parse_time_text(m.group(2)) or 0
        body = " ".join(lines[time_idx + 1:])
        body = re.sub(r"<[^>]+>", "", body)  # 去 SRT 内联样式
        if body:
            lyrics.lines.append(LyricLine(time_ms=start, text=body, end_ms=end))
    return lyrics


# ---------------------------------------------------------------------------
# ASS
# ---------------------------------------------------------------------------

def parse_ass(text: str) -> Lyrics:
    """解析 ASS/SSA 字幕（取 Dialogue 行，去掉样式覆盖标签）。"""
    lyrics = Lyrics()
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("Dialogue:"):
            continue
        parts = line.split(",", 9)
        if len(parts) < 10:
            continue
        start = _parse_time_text(parts[1]) or 0
        end = _parse_time_text(parts[2]) or 0
        body = re.sub(r"\{[^}]*\}", "", parts[9]).replace("\\N", " ").strip()
        if body:
            lyrics.lines.append(LyricLine(time_ms=start, text=body, end_ms=end))
    return lyrics


# ---------------------------------------------------------------------------
# TTML
# ---------------------------------------------------------------------------

def parse_ttml(text: str) -> Lyrics:
    """解析 TTML/DFXP 字幕（XML）。"""
    lyrics = Lyrics()
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return lyrics
    ns = {"tt": "http://www.w3.org/ns/ttml",
          "tts": "http://www.w3.org/ns/ttml#styling"}
    for p in root.iter("{http://www.w3.org/ns/ttml}p"):
        begin = p.get("begin")
        end = p.get("end")
        start = _parse_time_text(begin) if begin else 0
        end_ms = _parse_time_text(end) if end else 0
        body = " ".join("".join(p.itertext()).split())
        if body:
            lyrics.lines.append(LyricLine(time_ms=start, text=body, end_ms=end_ms))
    return lyrics


# ---------------------------------------------------------------------------
# QRC（QQ 音乐加密歌词）
# ---------------------------------------------------------------------------

def decrypt_qrc(data: bytes) -> str:
    """解密 QRC（QQ 逐字歌词）。

    算法：跳过头部后，密文长度以小端 4 字节记录；
    密钥为密文本身的 CRC32（4 字节小端），按字节循环异或。
    """
    if len(data) < 8:
        return ""
    # 跳过文件头（可能是 "QRC"+版本 或 长度字段）
    head = data[:4]
    if head in (b"QRC1", b"QRC2", b"QRC3", b"QRC4"):
        data = data[4:]
    if len(data) < 4:
        return ""
    length = int.from_bytes(data[:4], "little")
    if 0 < length < len(data):
        encrypted = data[4:4 + length]
    else:
        encrypted = data[4:]
    if not encrypted:
        return ""
    crc = zlib.crc32(encrypted) & 0xFFFFFFFF
    key = crc.to_bytes(4, "little")
    decrypted = bytes(b ^ key[i % 4] for i, b in enumerate(encrypted))
    try:
        return decrypted.decode("utf-8")
    except UnicodeDecodeError:
        # 部分实现头部多 4 字节，尝试跳过再解
        return decrypted[4:].decode("utf-8", "replace")


# ---------------------------------------------------------------------------
# KRC（酷狗加密歌词）
# ---------------------------------------------------------------------------

_KRC_KEY = bytes([
    0x40, 0x47, 0x61, 0x77, 0x5E, 0x32, 0x74, 0x47,
    0x51, 0x36, 0x31, 0x2D, 0xCE, 0xD2, 0x6E, 0x69,
])


def decrypt_krc(data: bytes) -> str:
    """解密 KRC：跳过 "krc1" 头，按固定 16 字节密钥循环异或后 zlib 解压。"""
    if data[:4] == b"krc1":
        data = data[4:]
    decrypted = bytes(b ^ _KRC_KEY[i % 16] for i, b in enumerate(data))
    try:
        return zlib.decompress(decrypted).decode("utf-8", "replace")
    except zlib.error:
        return ""


_KRC_LINE_RE = re.compile(r"<(\d+),(\d+)(?:,(\d+))?>([^<]*)")


def parse_krc(text: str) -> Lyrics:
    """解析解密后的 KRC 文本。"""
    lyrics = Lyrics()
    offset = 0
    m = _OFFSET_RE.search(text)
    if m:
        offset = int(m.group(1))
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]") and ":" in line[1:-1]:
            key, _, val = line[1:-1].partition(":")
            lyrics.meta[key.strip().lower()] = val.strip()
            continue
        segs = list(_KRC_LINE_RE.finditer(line))
        if not segs:
            continue
        first_start = int(segs[0].group(1))
        words: List[LyricWord] = []
        for sm in segs:
            start = int(sm.group(1))
            end = int(sm.group(2))
            seg_text = sm.group(4)
            if seg_text:
                words.append(LyricWord(time_ms=start + offset, text=seg_text,
                                       duration_ms=max(0, end - start)))
        text = "".join(w.text for w in words)
        lyrics.lines.append(LyricLine(time_ms=first_start + offset, text=text, words=words))
    return lyrics


def decrypt_krc_bytes(data: bytes) -> Lyrics:
    """解密并解析 KRC 文件内容。"""
    return parse_krc(decrypt_krc(data))


def decrypt_qrc_bytes(data: bytes) -> Lyrics:
    """解密并解析 QRC 文件内容。"""
    return parse_lrc(decrypt_qrc(data))


# ---------------------------------------------------------------------------
# 自动识别
# ---------------------------------------------------------------------------

def detect_format(text: str) -> str:
    """根据文本内容猜测格式。"""
    stripped = text.lstrip("\ufeff \t\r\n")
    if stripped.startswith("<?xml") or stripped.startswith("<tt "):
        return "ttml"
    if "Dialogue:" in text:
        return "ass"
    if re.search(r"\d{1,2}:\d{2}:\d{2}[,.]\d{1,3}\s*-->\s*\d{1,2}:\d{2}:\d{2}", text):
        return "srt"
    if re.search(r"\[\d{1,2}:\d{2}(?:[.,]\d{1,3})?\]", text):
        return "lrc"
    return "plain"


def parse_text(text: str) -> Lyrics:
    """按内容自动识别并解析。"""
    fmt = detect_format(text)
    if fmt == "srt":
        return parse_srt(text)
    if fmt == "ass":
        return parse_ass(text)
    if fmt == "ttml":
        return parse_ttml(text)
    if fmt == "lrc":
        return parse_lrc(text)
    # 纯文本：无时间戳
    lyrics = Lyrics()
    for i, line in enumerate(text.splitlines()):
        line = line.strip()
        if line:
            lyrics.lines.append(LyricLine(time_ms=0, text=line))
    return lyrics
