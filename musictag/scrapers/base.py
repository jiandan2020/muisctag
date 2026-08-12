# -*- coding: utf-8 -*-
"""刮削插件统一接口 —— 对齐 Lyrico-Plugins 插件协议。

参考 https://github.com/Replica0110/Lyrico-Plugins 的接口设计：
每个插件是一个"搜索源"，通过三个统一能力与宿主通信：

  * search_songs(request)  —— 按关键词搜索歌曲，返回归一化 Song 列表
  * get_lyrics(request)    —— 获取结构化歌词（原文/译文/罗马音三语合并）
  * search_covers(request) —— 搜索带封面的候选（search_songs 过滤）

Request 统一携带 {keyword, page, page_size, separator, config, song?}，
config 为插件配置项（对应 Lyrico 的 configFields）。
歌词返回 structured 结构：original / translated / romanization 三组行，
每行与 Lyrico 的 [startMs, endMs, text] 或 [startMs, endMs, [word...]] 等价
（此处用 LyricLine / LyricWord 数据类表达）。

宿主能力（HTTP/加密/缓存/日志等）由 utils.network 与 lyrics 模块提供，
插件只依赖这些抽象，可独立开发与注册。
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..lyrics.model import LyricLine
from ..utils.network import Network

# ---------------------------------------------------------------------------
# 协议常量（对应 Lyrico spec.js）
# ---------------------------------------------------------------------------

#: 插件能力集合
CAPABILITIES = ("searchSongs", "getLyrics", "searchCovers")

#: 标准字段键（snake_case，与 Lyrico STANDARD_FIELD_KEYS 对齐）
STANDARD_FIELD_KEYS = (
    "title", "artist", "album", "album_artist", "genre", "date",
    "track_number", "disc_number", "composer", "lyricist", "comment",
    "lyrics", "cover_url", "language", "copyright", "rating",
    "replaygain_track_gain", "replaygain_track_peak",
    "replaygain_album_gain", "replaygain_album_peak",
    "replaygain_reference_loudness",
)

#: 配置字段类型（与 Lyrico CONFIG_FIELD_TYPES 对齐）
CONFIG_FIELD_TYPES = ("text", "password", "number", "switch", "dropdown",
                      "textarea", "markdown")


# ---------------------------------------------------------------------------
# 模型
# ---------------------------------------------------------------------------

@dataclass
class PluginConfigField:
    """插件配置项（对应 manifest.json 的 configFields）。"""
    key: str
    title: str
    type: str = "text"
    summary: str = ""
    group: str = "通用"
    default: str = ""
    options: List[Dict[str, str]] = field(default_factory=list)  # [{value,label}]


@dataclass
class PluginManifest:
    """插件清单（对应 Lyrico 的 manifest.json）。"""
    id: str                       # 如 com.neteasecloudmusic.source
    name: str                     # 显示名
    key: str = ""                 # 简短注册键（如 netease/qq/kugou），默认取 id
    version: str = "0.1.0"
    author: str = ""
    description: str = ""
    capabilities: List[str] = field(default_factory=lambda: list(CAPABILITIES))
    config_fields: List[PluginConfigField] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.key:
            self.key = self.id
        # 兼容 dict 形式的 config_fields（与 Lyrico manifest 解析一致）
        self.config_fields = [
            f if isinstance(f, PluginConfigField) else PluginConfigField(**f)
            for f in self.config_fields
        ]


@dataclass
class Song:
    """归一化歌曲（对应 Lyrico 插件的 Song 对象）。

    artist 为按 separator 连接的多艺术家文本；fields 提供标准键的完整元数据。
    """
    id: str = ""
    title: str = ""
    artist: str = ""              # 多艺术家用 "/" 连接（separator）
    album: str = ""
    duration: float = 0.0         # 秒
    date: str = ""                # 发行日期（如 2024-01-01 或 2024）
    track_number: str = ""
    disc_number: str = ""
    cover_url: str = ""
    source: str = ""              # 平台标识（net/qq/kugou...）
    source_name: str = ""         # 平台显示名
    fields: Dict[str, str] = field(default_factory=dict)   # 标准键字段
    internal: Dict[str, Any] = field(default_factory=dict)  # 平台私有数据
    extra: Dict[str, Any] = field(default_factory=dict)

    # ---- 便捷属性 ----
    @property
    def artists(self) -> List[str]:
        return [a.strip() for a in self.artist.split("/") if a.strip()]

    @property
    def artist_text(self) -> str:
        return self.artist

    @property
    def year(self) -> str:
        return (self.date or "")[:4]

    def keyword(self) -> str:
        return f"{self.title} {self.artist}".strip()

    def to_fields(self) -> Dict[str, Any]:
        """转换为写入标签用的字段字典（供批处理直接使用）。"""
        out: Dict[str, Any] = {
            "title": self.title,
            "artists": self.artists,
            "album": self.album,
            "year": self.year,
            "track": self.track_number,
            "disc": self.disc_number,
        }
        for key, tag_key in (("genre", "genre"), ("composer", "composer"),
                             ("lyricist", "lyricist"), ("comment", "comment"),
                             ("copyright", "copyright")):
            if self.fields.get(key):
                out[tag_key] = self.fields[key]
        return out


@dataclass
class SongSearchRequest:
    """searchSongs 请求。"""
    keyword: str = ""
    page: int = 1
    page_size: int = 10
    separator: str = "/"
    config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CoverSearchRequest:
    """searchCovers 请求。"""
    keyword: str = ""
    page: int = 1
    page_size: int = 5
    separator: str = "/"
    config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LyricsRequest:
    """getLyrics 请求：优先使用 song 精确获取，否则按 keyword 搜索候选。"""
    song: Optional[Song] = None
    keyword: str = ""
    page: int = 1
    page_size: int = 5
    separator: str = "/"
    config: Dict[str, Any] = field(default_factory=dict)

    @property
    def query(self) -> str:
        if self.song and self.song.id and self.song.id != "local-song":
            return self.song.keyword()
        return self.keyword or (self.song.keyword() if self.song else "")


@dataclass
class LyricsResult:
    """结构化歌词（对应 Lyrico 的 structured 歌词结果）。

    original / translated / romanization 均为按时间排序的 LyricLine 列表；
    逐字歌词的行内 words 携带字级时间。无时间轴时用 plain。
    """
    type: str = "structured"
    tags: Dict[str, str] = field(default_factory=dict)   # ti/ar/al/date
    original: List[LyricLine] = field(default_factory=list)
    translated: List[LyricLine] = field(default_factory=list)
    romanization: List[LyricLine] = field(default_factory=list)
    plain: str = ""
    format: str = "lrc"           # lrc / yrc / krc / plain
    source: str = ""
    title: str = ""
    artist: str = ""

    @property
    def has_lyrics(self) -> bool:
        return bool(self.original or self.translated or self.romanization or self.plain)

    def line_text(self, lines: Optional[List[LyricLine]] = None) -> str:
        """把行列表渲染为纯文本。"""
        src = lines if lines is not None else self.original
        return "\n".join(ln.text for ln in src)

    def to_lrc(self, with_translation: bool = True,
               with_romanization: bool = True) -> str:
        """渲染为 LRC 文本（原文 + 可选译文/罗马音按行合并）。"""
        from .lyric_utils import render_structured_lrc
        return render_structured_lrc(self, with_translation=with_translation,
                                     with_romanization=with_romanization)

    # ---- 兼容旧接口 ----
    @property
    def synced(self) -> str:
        return self.to_lrc()

    @property
    def translation(self) -> str:
        from .lyric_utils import lines_to_lrc
        return lines_to_lrc(self.translated)

    def best_text(self, prefer: str = "synced") -> str:
        if prefer == "plain" and self.plain:
            return self.plain
        return self.to_lrc()


# ---------------------------------------------------------------------------
# 插件基类
# ---------------------------------------------------------------------------

class Plugin(ABC):
    """平台插件基类。子类实现三个能力方法即可接入（与 Lyrico 对齐）。"""

    manifest: PluginManifest

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.net = Network(self.config)

    # ---- 标识属性（兼容注册表 / GUI 使用） ----
    @property
    def key(self) -> str:
        """简短注册键，如 netease/qq/kugou。"""
        return self.manifest.key

    @property
    def name(self) -> str:
        """平台显示名。"""
        return self.manifest.name

    @property
    def display_name(self) -> str:
        """平台显示名（兼容旧接口）。"""
        return self.manifest.name

    # ---- 统一能力接口 ----
    @abstractmethod
    def search_songs(self, request: SongSearchRequest) -> List[Song]:
        """按关键词搜索歌曲，返回归一化 Song 列表。"""

    def get_lyrics(self, request: LyricsRequest) -> Optional[LyricsResult]:
        """获取结构化歌词；不支持时返回 None。"""
        return None

    def search_covers(self, request: CoverSearchRequest) -> List[Song]:
        """搜索带封面的候选歌曲。默认基于 search_songs 过滤。"""
        songs = self.search_songs(SongSearchRequest(
            keyword=request.keyword, page=request.page,
            page_size=request.page_size, separator=request.separator,
            config=request.config))
        return [s for s in songs if s.cover_url]

    # ---- 兼容旧接口（内部调用，供 GUI/批处理使用） ----
    def search(self, keyword: str, limit: int = 10) -> List[Song]:
        return self.search_songs(SongSearchRequest(
            keyword=keyword, page_size=limit,
            config=self._plugin_config()))

    def get_cover(self, song: Song) -> Optional[bytes]:
        return self._safe_get_bytes(song.cover_url)

    def _plugin_config(self) -> Dict[str, Any]:
        return self.config.get("plugin_config", {}) or {}

    # ---- 辅助 ----
    def _safe_get_bytes(self, url: str) -> Optional[bytes]:
        if not url:
            return None
        try:
            return self.net.get_bytes(url)
        except Exception:
            return None

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.manifest.name}>"
