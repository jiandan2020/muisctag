# -*- coding: utf-8 -*-
"""歌词数据模型。

统一表示：Lyrics 由若干 LyricLine 组成，每行可携带逐字时间（LyricWord）。
时间一律用毫秒整数，转换输出时再格式化为 mm:ss.xx 等。
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class LyricWord:
    """逐字歌词中的一个字/词片段。"""
    time_ms: int
    text: str
    duration_ms: int = 0


@dataclass
class LyricLine:
    """一行歌词。"""
    time_ms: int
    text: str
    words: List[LyricWord] = field(default_factory=list)
    end_ms: int = 0

    @property
    def has_word_times(self) -> bool:
        return bool(self.words)


@dataclass
class Lyrics:
    """整首歌词。"""
    lines: List[LyricLine] = field(default_factory=list)
    meta: Dict[str, str] = field(default_factory=dict)   # ti/ar/al/by/offset 等
    source: str = ""                                     # 来源标识（如 qq/netease）
    is_translation: bool = False                         # 是否为译文

    def sorted_lines(self) -> List[LyricLine]:
        return sorted(self.lines, key=lambda x: x.time_ms)

    def plain_text(self) -> str:
        return "\n".join(ln.text for ln in self.sorted_lines())

    def duration_ms(self) -> int:
        if not self.lines:
            return 0
        return max(ln.end_ms or ln.time_ms for ln in self.lines)
