# -*- coding: utf-8 -*-
"""Lrclib 插件：无需 API Key 的公共歌词数据库，支持同步/纯文本歌词。"""
from __future__ import annotations
from typing import List, Optional
from .base import LyricResult, ScraperPlugin, TrackMatch

SEARCH_URL = "https://lrclib.net/api/search"


class LrclibPlugin(ScraperPlugin):
    name = "lrclib"
    display_name = "Lrclib"

    def search(self, keyword: str, limit: int = 10) -> List[TrackMatch]:
        try:
            items = self.net.get_json(SEARCH_URL, params={"q": keyword, "page_size": limit})
        except Exception:
            return []
        if not isinstance(items, list):
            return []
        out = []
        for it in items:
            out.append(TrackMatch(
                title=it.get("trackName", ""),
                artists=[it.get("artistName", "")] if it.get("artistName") else [],
                album=it.get("albumName", ""),
                source=self.name, source_name=self.display_name,
                track_id=str(it.get("id", "")),
                duration=float(it.get("duration", 0) or 0),
                extra={"syncedLyrics": it.get("syncedLyrics", ""),
                       "plainLyrics": it.get("plainLyrics", "")},
                raw=it,
            ))
        return out

    def get_lyrics(self, track: TrackMatch) -> Optional[LyricResult]:
        synced = (track.extra or {}).get("syncedLyrics", "")
        plain = (track.extra or {}).get("plainLyrics", "")
        if not synced and not plain:
            return None
        return LyricResult(
            synced=synced, plain=plain, format="lrc", source=self.name,
            title=track.title, artist=track.artist_text,
        )

    def get_cover(self, track: TrackMatch) -> Optional[bytes]:
        return None
