# -*- coding: utf-8 -*-
"""歌词行解析与三语合并工具 —— 对齐 Lyrico-Plugins 的歌词处理方式。

Lyrico 插件把歌词统一为 "行" 结构：
  * 行级：[startMs, endMs, text]
  * 词级：[startMs, endMs, [[wordStartMs, wordEndMs, wordText], ...]]
本模块用 musictag.lyrics.model 的 LyricLine / LyricWord 表达等价结构，
并提供与插件一致的解析与合并语义：

  * parse_lrc_lines     普通 LRC → 行级（end = 下一行 start - 10ms，末行 +3000ms）
  * parse_yrc_lines     QQ/网易逐字 YRC → 词级
  * parse_krc_lines     酷狗 KRC（解密后文本）→ 词级，含 language 罗马音标签
  * merge_lyrics        把译文/罗马音按行合并进原文
  * render_structured_lrc / lines_to_lrc  渲染回 LRC 文本
"""
from __future__ import annotations
import json
import re
from typing import Dict, List, Optional

from ..lyrics.model import LyricLine, LyricWord

_TIME_RE = re.compile(r"\[(\d{1,}):(\d{2})(?:[.:](\d{1,3}))?]")


def _parse_ms(min_str: str, sec_str: str, frac: str = "") -> int:
    frac = (frac or "0").ljust(3, "0")[:3]
    return (int(min_str) * 60 + int(sec_str)) * 1000 + int(frac)


# ---------------------------------------------------------------------------
# 解析
# ---------------------------------------------------------------------------

def parse_lrc_lines(text: str) -> List[LyricLine]:
    """普通 LRC → 行级 LyricLine（对齐 Lyrico parseLrc）。"""
    items: List[tuple] = []
    for raw in String(text or "").splitlines():
        matches = list(_TIME_RE.finditer(raw))
        if not matches:
            continue
        last = matches[-1]
        content = raw[last.end():].strip()
        if not content:
            continue
        for m in matches:
            items.append((_parse_ms(m.group(1), m.group(2), m.group(3)), content))
    items.sort(key=lambda x: x[0])
    lines = []
    for i, (start, content) in enumerate(items):
        end = max(start, items[i + 1][0] - 10) if i + 1 < len(items) else start + 3000
        lines.append(LyricLine(time_ms=start, text=content, end_ms=end,
                               words=[LyricWord(time_ms=start, text=content,
                                                duration_ms=max(0, end - start))]))
    return lines


def parse_yrc_lines(text: str) -> List[LyricLine]:
    """逐字 YRC（`[start,duration]` + `(ws,wd,0)字`）→ 词级 LyricLine。"""
    out: List[LyricLine] = []
    for raw in String(text or "").splitlines():
        line = raw.strip()
        m = re.match(r"^\[(\d+),(\d+)](.*)$", line)
        if not m:
            continue
        start = int(m.group(1))
        duration = int(m.group(2))
        end = start + duration
        content = m.group(3)
        words: List[LyricWord] = []
        for wm in re.finditer(r"\((\d+),(\d+),\d+\)([^()]*)", content):
            ws = start + int(wm.group(1))
            wd = int(wm.group(2))
            wtext = wm.group(3)
            if wtext:
                words.append(LyricWord(time_ms=ws, text=wtext, duration_ms=wd))
        if not words and content:
            words.append(LyricWord(time_ms=start, text=content, duration_ms=duration))
        if not words:
            continue
        words.sort(key=lambda w: w.time_ms)
        out.append(LyricLine(time_ms=start, text="".join(w.text for w in words),
                             end_ms=end, words=words))
    out.sort(key=lambda ln: ln.time_ms)
    return out


def parse_krc_lines(text: str, language: bool = False) -> List[LyricLine]:
    """解密后的 KRC 文本 → 词级 LyricLine。

    language=True 时返回 language 标签中的罗马音行（对齐 Lyrico parseKrc）。
    """
    if language:
        # 从 [language:base64] 标签解析罗马音行
        m = re.search(r"\[language:([^\]]+)]", text or "")
        if not m:
            return []
        try:
            root = json.loads(base64_decode(m.group(1)))
        except Exception:
            return []
        items = []
        for it in root.get("content", []):
            if isinstance(it, dict):
                items.append({"start": int(it.get("t", 0)), "text": it.get("tx", "")})
        return _build_line_level(items)

    out: List[LyricLine] = []
    for raw in String(text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if re.match(r"^\[(\w+):([^\]]*)]$", line):
            continue  # [ti:xxx] 等标签行
        m = re.match(r"^\[(\d+),(\d+)](.*)$", line)
        if not m:
            continue
        start = int(m.group(1))
        duration = int(m.group(2))
        end = start + duration
        content = m.group(3)
        offsets = [(int(wm.group(1)), wm.group(4)) for wm in
                   re.finditer(r"<(\d+),(\d+),(\d+)>([^<]*)", content)]
        words: List[LyricWord] = []
        for i, (offset, wtext) in enumerate(offsets):
            ws = start + offset
            we = start + offsets[i + 1][0] if i + 1 < len(offsets) else end
            if wtext:
                words.append(LyricWord(time_ms=ws, text=wtext,
                                       duration_ms=max(0, we - ws)))
        if not words and content:
            words.append(LyricWord(time_ms=start, text=content, duration_ms=duration))
        if not words:
            continue
        out.append(LyricLine(time_ms=start, text="".join(w.text for w in words),
                             end_ms=end, words=words))
    out.sort(key=lambda ln: ln.time_ms)
    return out


def _build_line_level(items: List[dict]) -> List[LyricLine]:
    items = sorted(items, key=lambda x: int(x.get("start", 0)))
    out = []
    for i, it in enumerate(items):
        start = int(it.get("start", 0))
        text = str(it.get("text", "")).strip()
        if not text:
            continue
        next_start = int(items[i + 1]["start"]) if i + 1 < len(items) else start + 3000
        end = max(start, next_start - 10)
        out.append(LyricLine(time_ms=start, text=text, end_ms=end,
                             words=[LyricWord(time_ms=start, text=text,
                                              duration_ms=max(0, end - start))]))
    return out


def parse_netease_original(yrc: str, lrc: str) -> List[LyricLine]:
    """网易原文歌词：优先逐字 YRC，其次富文本 JSON，最后普通 LRC。"""
    if yrc:
        lines = parse_yrc_lines(yrc)
        if lines:
            return lines
        rich = parse_rich_json_lines(yrc)
        if rich:
            return rich
    if lrc and lrc.strip():
        rich = parse_rich_json_lines(lrc)
        if rich:
            return rich
        return parse_lrc_lines(lrc)
    return []


def parse_rich_json_lines(text: str) -> List[LyricLine]:
    """网易逐字 JSON 歌词（每行一个 {t, c:[{tx}]} 对象）→ 行级。"""
    items = []
    for raw in String(text or "").splitlines():
        line = raw.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
            parts = [str(it.get("tx", "")) for it in obj.get("c", []) if it.get("tx")]
            text = "".join(parts).strip()
            if text:
                items.append({"start": int(obj.get("t", 0)), "text": text})
        except Exception:
            continue
    return _build_line_level(items)


# ---------------------------------------------------------------------------
# 合并（对齐 Lyrico lyricsMerge）
# ---------------------------------------------------------------------------

def extract_line_text(line: LyricLine) -> str:
    return line.text


def merge_lyrics(original: List[LyricLine],
                 translated: List[LyricLine]) -> List[LyricLine]:
    """把译文/罗马音按行索引合并进原文（行数不足则保留原文行）。"""
    if not original or not translated:
        return list(original)
    out: List[LyricLine] = []
    for i, ln in enumerate(original):
        if i < len(translated) and translated[i].text:
            out.append(LyricLine(time_ms=ln.time_ms, end_ms=ln.end_ms,
                                 text=f"{ln.text} | {translated[i].text}",
                                 words=ln.words))
        else:
            out.append(ln)
    return out


# ---------------------------------------------------------------------------
# 渲染
# ---------------------------------------------------------------------------

def _fmt_lrc_time(ms: int) -> str:
    ms = max(0, int(ms))
    m, rem = divmod(ms, 60000)
    s, frac = divmod(rem, 1000)
    return f"[{m:02d}:{s:02d}.{frac:02d}]"


def lines_to_lrc(lines: List[LyricLine]) -> str:
    return "\n".join(_fmt_lrc_time(ln.time_ms) + ln.text for ln in lines)


def render_structured_lrc(result, with_translation: bool = True,
                          with_romanization: bool = True) -> str:
    """把结构化歌词渲染为 LRC 文本。

    * 纯原文且带逐字时间戳 -> 保留词级 <mm:ss.xx> 输出
    * 合并了译文/罗马音     -> 按行输出 "原文 | 译文 | 罗马音"
    """
    original = result.original
    if not original:
        return result.plain or ""
    merged: List[LyricLine] = list(original)
    merged_any = False
    if with_translation and result.translated:
        merged = merge_lyrics(merged, result.translated)
        merged_any = True
    if with_romanization and result.romanization:
        merged = merge_lyrics(merged, result.romanization)
        merged_any = True

    out = []
    tags = result.tags
    for key, label in (("ti", "ti"), ("ar", "ar"), ("al", "al")):
        if tags.get(key):
            out.append(f"[{label}:{tags[key]}]")

    for ln in merged:
        ts = _fmt_lrc_time(ln.time_ms)
        if not merged_any and ln.words:
            # 词级渲染（对齐 Lyrico 逐字歌词）
            body = "".join(
                f"<{_fmt_lrc_time(w.time_ms).strip('[]')}>{w.text}"
                for w in sorted(ln.words, key=lambda x: x.time_ms))
        else:
            body = ln.text
        out.append(ts + body)
    return "\n".join(out) + ("\n" if out else "")


def String(value) -> str:
    return str(value or "")


def base64_decode(value: str) -> str:
    import base64
    try:
        return base64.b64decode(value).decode("utf-8", "replace")
    except Exception:
        return ""
