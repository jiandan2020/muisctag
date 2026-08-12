# -*- coding: utf-8 -*-
"""Musixmatch 插件（需 API Key，在设置中填写）。

  * 搜索: track.search
  * 歌词: track.lyrics.get
  * 封面: album.get
"""
from __future__ import annotations
from typing import List, Optional
from .base import LyricResult, ScraperPlugin, TrackMatch

API = "https://api.musixmatch.com/ws/1.1"


class MusixmatchPlugin(ScraperPlugin):
    name = "musixmatch"
    display_name = "Musixmatch"

    @property
    def api_key(self) -> str:
        return (self.config.get("translate") or {}).get("musixmatch_api_key", "") \
            or (self.config.get("scrape") or {}).get("musixmatch_api_key", "")

    def _get(self, method: str, **params):
        if not self.api_key:
            return None
        try:
            data = self.net.get_json(f"{API}/{method}", params={"apikey": self.api_key, **params})
            return ((data or {}).get("message") or {}).get("body") or {}
        except Exception:
            return None

    def search(self, keyword: str, limit: int = 10) -> List[TrackMatch]:
        body = self._get("track.search", q_track=keyword, page_size=limit, s_track_rating="desc")
        items = ((body or {}).get("track_list")) or []
        out = []
        for it in items:
            t = it.get("track") or {}
            out.append(TrackMatch(
                title=t.get("track_name", ""),
                artists=[t.get("artist_name", "")] if t.get("artist_name") else [],
                album=t.get("album_name", ""),
                source=self.name, source_name=self.display_name,
                track_id=str(t.get("track_id", "")),
                album_id=str(t.get("album_id", "")),
                duration=float(t.get("track_length", 0) or 0),
                extra={"has_lyrics": t.get("has_lyrics") == 1},
                raw=t,
            ))
        return out

    def get_lyrics(self, track: TrackMatch) -> Optional[LyricResult]:
        body = self._get("track.lyrics.get", track_id=track.track_id)
        if not body:
            return None
        lyr = (body.get("lyrics") or {}).get("lyrics_body") or ""
        if not lyr:
            return None
        # Musixmatch 返回的歌词带 150 字符截断提示，去掉
        lyr = lyr.split("******* This Lyrics is NOT for Commercial use *******")[0].strip()
        return LyricResult(synced="", plain=lyr, format="plain", source=self.name,
                           title=track.title, artist=track.artist_text)

    def get_cover(self, track: TrackMatch) -> Optional[bytes]:
        body = self._get("album.get", album_id=track.album_id)
        if not body:
            return None
        url = (body.get("album") or {}).get("album_coverart_100x100") or ""
        return self._safe_get_bytes(url)
