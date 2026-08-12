# -*- coding: utf-8 -*-
"""歌词格式转换：LRC / SRT / ASS / TTML / 纯文本，以及时间调整、译文合并。"""
from __future__ import annotations
import re
from typing import List, Optional
from .model import LyricLine, Lyrics
from .parser import parse_text


def _fmt_ms(ms: int, sep: str = ".") -> str:
    ms = max(0, int(ms))
    frac = ms % 1000
    total_s = ms // 1000
    m, s = divmod(total_s, 60)
    return f"{m:02d}:{s:02d}{sep}{frac:03d}"[:9] if sep == "." else f"{m:02d}:{s:02d}"


def _fmt_lrc_time(ms: int) -> str:
    ms = max(0, int(ms))
    m, rem = divmod(ms, 60000)
    s, frac = divmod(rem, 1000)
    return f"[{m:02d}:{s:02d}.{frac:02d}]"


def _fmt_srt_time(ms: int) -> str:
    ms = max(0, int(ms))
    h, rem = divmod(ms, 3600000)
    m, rem = divmod(rem, 60000)
    s, frac = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{frac:03d}"


def _fmt_ass_time(ms: int) -> str:
    ms = max(0, int(ms))
    h, rem = divmod(ms, 3600000)
    m, rem = divmod(rem, 60000)
    s, frac = divmod(rem, 1000)
    return f"{h}:{m:02d}:{s:02d}.{frac:02d}"


def to_lrc(lyrics: Lyrics, with_words: bool = False) -> str:
    """输出 LRC。with_words=True 时保留逐字时间戳（增强型 LRC）。"""
    out = []
    meta = lyrics.meta
    for key, label in (("ti", "ti"), ("ar", "ar"), ("al", "al"), ("by", "by")):
        if meta.get(key):
            out.append(f"[{label}:{meta[key]}]")
    offset = meta.get("offset")
    if offset and offset != "0":
        out.append(f"[offset:{offset}]")
    for ln in lyrics.sorted_lines():
        line = _fmt_lrc_time(ln.time_ms)
        if with_words and ln.words:
            body = []
            # 逐字输出：<mm:ss.xx>文本
            for w in sorted(ln.words, key=lambda x: x.time_ms):
                ms = max(0, int(w.time_ms))
                m, rem = divmod(ms, 60000)
                s, frac = divmod(rem, 1000)
                body.append(f"<{m:02d}:{s:02d}.{frac:02d}>{w.text}")
            out.append(line + "".join(body))
        else:
            out.append(line + ln.text)
    return "\n".join(out) + ("\n" if out else "")


def to_srt(lyrics: Lyrics) -> str:
    out = []
    for i, ln in enumerate(lyrics.sorted_lines(), 1):
        end = ln.end_ms or (ln.time_ms + 2500)
        out.append(f"{i}\n{_fmt_srt_time(ln.time_ms)} --> {_fmt_srt_time(end)}\n{ln.text}\n")
    return "\n".join(out)


def to_ass(lyrics: Lyrics, title: str = "MusicTag") -> str:
    out = [
        "[Script Info]",
        f"Title: {title}",
        "ScriptType: v4.00+",
        "PlayResX: 1920",
        "PlayResY: 1080",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: Default,Microsoft YaHei,72,&H00FFFFFF,&H000000FF,&H00000000,&H96000000,0,0,0,0,100,100,0,0,1,2,1,2,40,40,40,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for ln in lyrics.sorted_lines():
        end = ln.end_ms or (ln.time_ms + 2500)
        text = ln.text.replace("\\", "\\\\").replace("\n", "\\N")
        out.append(f"Dialogue: 0,{_fmt_ass_time(ln.time_ms)},{_fmt_ass_time(end)},Default,,0,0,0,,{text}")
    return "\n".join(out)


def to_ttml(lyrics: Lyrics) -> str:
    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<tt xmlns="http://www.w3.org/ns/ttml" xmlns:tts="http://www.w3.org/ns/ttml#styling">',
        "  <body><div>",
    ]
    for ln in lyrics.sorted_lines():
        end = ln.end_ms or (ln.time_ms + 2500)
        out.append(f'    <p begin="{_fmt_srt_time(ln.time_ms)}" end="{_fmt_srt_time(end)}">{ln.text}</p>')
    out.append("  </div></body>")
    out.append("</tt>")
    return "\n".join(out)


def to_plain(lyrics: Lyrics) -> str:
    return lyrics.plain_text()


FORMATS = {
    "lrc": to_lrc,
    "srt": to_srt,
    "ass": to_ass,
    "ttml": to_ttml,
    "plain": to_plain,
}


def convert_text(text: str, target: str, with_words: bool = False) -> str:
    """自动识别输入格式并转换为目标格式。"""
    lyrics = parse_text(text)
    if target not in FORMATS:
        raise ValueError(f"不支持的输出格式: {target}")
    if target == "lrc":
        return to_lrc(lyrics, with_words=with_words)
    return FORMATS[target](lyrics)


def adjust_time(lyrics: Lyrics, delta_ms: int) -> Lyrics:
    """整体平移时间轴（delta_ms 可为负）。"""
    for ln in lyrics.lines:
        ln.time_ms = max(0, ln.time_ms + delta_ms)
        if ln.end_ms:
            ln.end_ms = max(0, ln.end_ms + delta_ms)
        for w in ln.words:
            w.time_ms = max(0, w.time_ms + delta_ms)
    return lyrics


def merge_translation(original: Lyrics, translation: Lyrics) -> Lyrics:
    """把译文合并进原歌词（同时间行拼接，时间以原文为准）。"""
    result = Lyrics(meta=dict(original.meta), source=original.source)
    trans = {ln.time_ms: ln.text for ln in translation.sorted_lines()}
    for ln in original.sorted_lines():
        t = trans.get(ln.time_ms)
        if t:
            result.lines.append(LyricLine(time_ms=ln.time_ms,
                                          text=f"{ln.text} | {t}",
                                          words=ln.words, end_ms=ln.end_ms))
        else:
            result.lines.append(ln)
    return result
