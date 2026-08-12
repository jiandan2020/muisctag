# -*- coding: utf-8 -*-
"""Apple Music / iTunes Search API 插件（无需密钥，公开接口）。

歌词需要 Apple Music API 授权令牌，本插件暂不提供；
封面通过 artworkUrl100 换尺寸获取高清版本。
"""
from __future__ import annotations
from typing import List, Optional
from .base import LyricResult, ScraperPlugin, TrackMatch

SEARCH_URL = "https://itunes.apple.com/search"


class ApplePlugin(ScraperPlugin):
    name = "apple"
    display_name = "Apple Music"

    def search(self, keyword: str, limit: int = 10) -> List[TrackMatch]:
        try:
            data = self.net.get_json(SEARCH_URL, params={
                "term": keyword, "media": "music", "limit": limit,
            })
        except Exception:
            return []
        results = (data or {}).get("results") or []
        out = []
        for r in results:
            if r.get("wrapperType") != "track":
                continue
            art = r.get("artworkUrl100", "")
            art300 = art.replace("100x100bb", "300x300bb") if art else ""
            out.append(TrackMatch(
                title=r.get("trackName", ""),
                artists=[r.get("artistName", "")] if r.get("artistName") else [],
                album=r.get("collectionName", ""),
                source=self.name, source_name=self.display_name,
                track_id=str(r.get("trackId", "")),
                album_id=str(r.get("collectionId", "")),
                duration=float(r.get("trackTimeMillis", 0) or 0) / 1000.0,
                cover_url=art300,
                extra={"year": str(r.get("releaseDate", ""))[:4]},
                raw=r,
            ))
        return out

    def get_lyrics(self, track: TrackMatch) -> Optional[LyricResult]:
        # Apple Music 官方歌词接口需要付费 API 令牌，未实现
        return None

    def get_cover(self, track: TrackMatch) -> Optional[bytes]:
        return self._safe_get_bytes(track.cover_url)
