# -*- coding: utf-8 -*-
"""Apple Music / iTunes Search API 插件（无需密钥，公开接口）。

提供搜索与封面能力；歌词需 Apple Music 付费 API 令牌，未实现
（与 Lyrico-Plugins 的 apple 插件一致，capabilities 不含 getLyrics）。
"""
from __future__ import annotations
from typing import List, Optional

from .base import (LyricsRequest, LyricsResult, Plugin, PluginManifest,
                   Song, SongSearchRequest)

SEARCH_URL = "https://itunes.apple.com/search"


class ApplePlugin(Plugin):
    manifest = PluginManifest(
        id="com.apple.music.source",
        key="apple",
        name="Apple Music",
        version="0.2.0",
        author="MusicTag",
        description="Apple Music / iTunes Search：搜索歌曲与高清封面",
        capabilities=["searchSongs", "searchCovers"],
        config_fields=[
            {"key": "country", "title": "地区（ISO 3166-1 alpha-2）",
             "type": "text", "default": "CN", "group": "地区偏好"},
            {"key": "cover_size", "title": "封面尺寸", "type": "dropdown",
             "default": "300x300",
             "options": [{"value": "100x100", "label": "100px"},
                         {"value": "300x300", "label": "300px"},
                         {"value": "600x600", "label": "600px"}]},
        ],
    )

    def search_songs(self, request: SongSearchRequest) -> List[Song]:
        cfg = self._plugin_config()
        country = str(cfg.get("country") or "CN")
        try:
            data = self.net.get_json(SEARCH_URL, params={
                "term": request.keyword, "media": "music",
                "country": country, "limit": request.page_size,
            })
        except Exception:
            return []
        results = (data or {}).get("results") or []
        size = str(cfg.get("cover_size") or "300x300")
        out = []
        for r in results:
            if r.get("wrapperType") != "track":
                continue
            art = str(r.get("artworkUrl100", "") or "")
            art = art.replace("100x100bb", f"{size}bb") if art else ""
            artist = str(r.get("artistName", ""))
            date = str(r.get("releaseDate", ""))[:10]
            fields = {
                "title": str(r.get("trackName", "")),
                "artist": artist,
                "album": str(r.get("collectionName", "")),
                "date": date,
                "track_number": str(r.get("trackNumber", "") or ""),
                "disc_number": str(r.get("discNumber", "") or ""),
                "cover_url": art,
                "genre": str(r.get("primaryGenreName", "") or ""),
            }
            out.append(Song(
                id=str(r.get("trackId", "")), title=fields["title"], artist=artist,
                album=fields["album"],
                duration=float(r.get("trackTimeMillis", 0) or 0) / 1000.0,
                date=date, track_number=fields["track_number"],
                disc_number=fields["disc_number"], cover_url=art,
                source=self.manifest.key, source_name=self.manifest.name,
                fields=fields,
                internal={"collectionId": str(r.get("collectionId", ""))},
            ))
        return out

    def get_lyrics(self, request: LyricsRequest) -> Optional[LyricsResult]:
        # Apple Music 官方歌词接口需要付费开发者令牌，未实现
        return None
