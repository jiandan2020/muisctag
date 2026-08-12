# -*- coding: utf-8 -*-
"""刮削插件统一接口。

参考 Lyrico-Plugins 的插件化设计：每个音乐平台实现三个核心能力
  * search      —— 按关键词搜索歌曲
  * get_lyrics  —— 获取歌词（LRC / 译文等）
  * get_cover   —— 获取专辑封面
宿主（GUI / 批处理）只依赖本模块的抽象，不关心具体平台。
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..utils.network import Network


@dataclass
class TrackMatch:
    """搜索结果（已归一化，供 GUI 展示与后续取歌词/封面）。"""
    title: str
    artists: List[str]
    album: str
    source: str                 # 平台标识
    source_name: str            # 平台显示名
    track_id: str = ""          # 平台内歌曲 ID
    album_id: str = ""
    duration: float = 0.0       # 秒
    cover_url: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)
    raw: Any = None

    @property
    def artist_text(self) -> str:
        return ", ".join(self.artists)

    def keyword(self) -> str:
        """用于精确获取歌词/封面的关键词（平台不同写法不同）。"""
        base = f"{self.title} {self.artist_text}"
        return base


@dataclass
class LyricResult:
    """歌词结果。"""
    synced: str = ""            # 带时间轴的 LRC 文本
    plain: str = ""             # 纯文本
    translation: str = ""       # 译文（若有，LRC 或纯文本）
    format: str = "lrc"         # lrc / krc / qrc
    source: str = ""
    title: str = ""
    artist: str = ""

    def best_text(self, prefer: str = "synced") -> str:
        if prefer == "plain" and self.plain:
            return self.plain
        return self.synced or self.plain


class ScraperPlugin(ABC):
    """平台插件基类。子类实现三个抽象方法即可接入。"""

    name: str = "base"
    display_name: str = "基础"

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.net = Network(self.config)

    # -- 统一能力 --
    @abstractmethod
    def search(self, keyword: str, limit: int = 10) -> List[TrackMatch]:
        """按关键词搜索歌曲。"""

    def get_lyrics(self, track: TrackMatch) -> Optional[LyricResult]:
        """获取歌词；不支持时返回 None。"""
        return None

    def get_cover(self, track: TrackMatch) -> Optional[bytes]:
        """获取封面二进制；不支持时返回 None。"""
        return None

    # -- 辅助 --
    def _safe_get_bytes(self, url: str) -> Optional[bytes]:
        if not url:
            return None
        try:
            return self.net.get_bytes(url)
        except Exception:
            return None

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.display_name}>"
