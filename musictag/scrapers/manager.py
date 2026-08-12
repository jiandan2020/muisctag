# -*- coding: utf-8 -*-
"""刮削管理器：插件注册、多平台聚合搜索、去重、批处理。"""
from __future__ import annotations
import re
import unicodedata
from typing import Callable, Dict, List, Optional, Tuple
from .base import LyricResult, ScraperPlugin, TrackMatch
from .apple import ApplePlugin
from .kugou import KugouPlugin
from .lrclib import LrclibPlugin
from .musixmatch import MusixmatchPlugin
from .netease import NeteasePlugin
from .qq import QQPlugin

#: 全部插件注册表（name -> 工厂函数）
PLUGIN_REGISTRY: Dict[str, Tuple[str, type]] = {
    "netease": ("网易云音乐", NeteasePlugin),
    "qq": ("QQ音乐", QQPlugin),
    "kugou": ("酷狗音乐", KugouPlugin),
    "lrclib": ("Lrclib", LrclibPlugin),
    "apple": ("Apple Music", ApplePlugin),
    "musixmatch": ("Musixmatch", MusixmatchPlugin),
}

#: 默认启用（musixmatch 需要 API Key，默认关闭）
DEFAULT_ENABLED = ["netease", "qq", "kugou", "lrclib", "apple"]


def _norm(text: str) -> str:
    t = unicodedata.normalize("NFKC", (text or "").lower())
    return re.sub(r"[\W_]+", "", t)


def similarity(a: str, b: str) -> float:
    """简单的字符级相似度（0~1）。"""
    x, y = _norm(a), _norm(b)
    if not x or not y:
        return 0.0
    if x == y:
        return 1.0
    short, long = (x, y) if len(x) <= len(y) else (y, x)
    if short in long:
        return len(short) / len(long)
    # 简单 LCS 比例
    dp = [[0] * (len(long) + 1) for _ in range(len(short) + 1)]
    for i in range(1, len(short) + 1):
        for j in range(1, len(long) + 1):
            dp[i][j] = dp[i - 1][j - 1] + 1 if short[i - 1] == long[j - 1] else max(dp[i - 1][j], dp[i][j - 1])
    return (2 * dp[-1][-1]) / (len(short) + len(long))


class ScrapeManager:
    """聚合多个平台插件，提供合并去重的搜索接口。"""

    def __init__(self, config: Optional[Dict] = None, enabled: Optional[List[str]] = None):
        self.config = config or {}
        self.enabled = enabled or DEFAULT_ENABLED
        self.plugins: List[ScraperPlugin] = []
        for name in self.enabled:
            info = PLUGIN_REGISTRY.get(name)
            if info and name != "musixmatch":
                self.plugins.append(info[1](self.config))
            elif info and name == "musixmatch":
                self.plugins.append(info[1](self.config))
        self._cache: Dict[str, List[TrackMatch]] = {}

    def plugin_names(self) -> List[str]:
        return [p.name for p in self.plugins]

    # ---------------- 聚合搜索 ----------------
    def search_all(self, keyword: str, limit: int = 10,
                   progress: Optional[Callable[[str, int], None]] = None) -> List[TrackMatch]:
        """并发搜索所有启用平台，按标题+艺术家去重合并。"""
        from concurrent.futures import ThreadPoolExecutor
        results: List[TrackMatch] = []
        total = len(self.plugins)

        def run(p: ScraperPlugin) -> List[TrackMatch]:
            if progress:
                progress(p.display_name, 0)
            try:
                return p.search(keyword, limit=limit)
            except Exception:
                return []

        with ThreadPoolExecutor(max_workers=min(8, total)) as ex:
            futures = {ex.submit(run, p): p for p in self.plugins}
            for i, fut in enumerate(futures):
                try:
                    results.extend(fut.result())
                except Exception:
                    pass
                if progress:
                    progress("", int((i + 1) / total * 100))
        return self._dedup(results)

    @staticmethod
    def _dedup(items: List[TrackMatch]) -> List[TrackMatch]:
        """按 (归一化标题, 归一化艺术家) 去重；同平台同歌去重。"""
        seen: Dict[Tuple[str, str], TrackMatch] = {}
        out: List[TrackMatch] = []
        for it in items:
            key = (_norm(it.title), _norm(it.artist_text))
            if not key[0]:
                continue
            if key in seen:
                # 同平台完全重复则跳过；跨平台保留（供用户选择）
                prev = seen[key]
                if prev.source == it.source:
                    continue
                # 若已有条目信息更全，则用新条目补齐封面
                if not prev.cover_url and it.cover_url:
                    prev.cover_url = it.cover_url
                continue
            seen[key] = it
            out.append(it)
        return out

    # ---------------- 获取详情 ----------------
    def get_lyrics(self, track: TrackMatch) -> Optional[LyricResult]:
        plugin = self._plugin(track.source)
        if plugin is None:
            return None
        try:
            return plugin.get_lyrics(track)
        except Exception:
            return None

    def get_cover(self, track: TrackMatch) -> Optional[bytes]:
        plugin = self._plugin(track.source)
        if plugin is None:
            return None
        try:
            return plugin.get_cover(track)
        except Exception:
            return None

    def _plugin(self, name: str) -> Optional[ScraperPlugin]:
        for p in self.plugins:
            if p.name == name:
                return p
        return None

    # ---------------- 批量刮削 ----------------
    def scrape_file(self, keyword: str, prefer: str = "synced",
                    with_cover: bool = True, with_lyrics: bool = True
                    ) -> Tuple[Optional[TrackMatch], Optional[LyricResult], Optional[bytes]]:
        """对单个关键词执行完整刮削：取最佳匹配 + 歌词 + 封面。"""
        tracks = self.search_all(keyword, limit=5)
        if not tracks:
            return None, None, None
        best = tracks[0]
        lyric = self.get_lyrics(best) if with_lyrics else None
        cover = self.get_cover(best) if with_cover else None
        return best, lyric, cover
