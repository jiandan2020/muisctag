# -*- coding: utf-8 -*-
"""Musixmatch 插件（需 API Key，在设置中填写）。

对齐 Lyrico-Plugins 的 musixmatch 插件：
  * 搜索:  track.search
  * 歌词:  track.lyrics.get（纯文本，Musixmatch 无时间轴）
  * 封面:  album.get（通过搜索结果的 album_id 获取）
"""
from __future__ import annotations
from typing import List, Optional

from .base import (CoverSearchRequest, LyricsRequest, LyricsResult, Plugin,
                   PluginConfigField, PluginManifest, Song, SongSearchRequest)

API = "https://api.musixmatch.com/ws/1.1"


class MusixmatchPlugin(Plugin):
    manifest = PluginManifest(
        id="com.musixmatch.source",
        key="musixmatch",
        name="Musixmatch",
        version="0.2.0",
        author="MusicTag",
        description="Musixmatch 搜索源插件：搜索歌曲、获取纯文本歌词与封面（需 API Key）",
        capabilities=["searchSongs", "getLyrics", "searchCovers"],
        config_fields=[
            PluginConfigField(
                key="api_key", title="Musixmatch API Key",
                summary="在 Musixmatch Developer 申请（免费额度约 100 次/天）",
                group="通用", type="password", default=""),
        ],
    )

    @property
    def api_key(self) -> str:
        cfg = self._plugin_config()
        if cfg.get("api_key"):
            return cfg["api_key"]
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

    # ---------------- 搜索 ----------------
    def search_songs(self, request: SongSearchRequest) -> List[Song]:
        body = self._get("track.search", q_track=request.keyword,
                         page_size=request.page_size, s_track_rating="desc")
        items = ((body or {}).get("track_list")) or []
        out = []
        for it in items:
            t = it.get("track") or {}
            title = str(t.get("track_name", ""))
            artist = str(t.get("artist_name", ""))
            out.append(Song(
                id=str(t.get("track_id", "")), title=title, artist=artist,
                album=str(t.get("album_name", "")),
                duration=float(t.get("track_length", 0) or 0),
                source=self.manifest.key, source_name=self.manifest.name,
                fields={"title": title, "artist": artist,
                        "album": str(t.get("album_name", ""))},
                internal={"album_id": str(t.get("album_id", "")),
                          "has_lyrics": t.get("has_lyrics") == 1},
            ))
        return out

    # ---------------- 歌词 ----------------
    def get_lyrics(self, request: LyricsRequest) -> Optional[LyricsResult]:
        song = request.song
        if song is None or not song.id:
            songs = self.search_songs(SongSearchRequest(
                keyword=request.keyword or (song.keyword() if song else ""),
                page_size=5))
            if not songs:
                return None
            song = songs[0]
        body = self._get("track.lyrics.get", track_id=song.id)
        if not body:
            return None
        lyr = (body.get("lyrics") or {}).get("lyrics_body") or ""
        if not lyr:
            return None
        # Musixmatch 返回的歌词带 150 字符截断提示，去掉
        lyr = lyr.split("******* This Lyrics is NOT for Commercial use *******")[0].strip()
        if not lyr:
            return None
        tags = {"ti": song.title, "ar": song.artist, "al": song.album}
        return LyricsResult(type="structured", tags=tags, plain=lyr, format="plain",
                            source=self.manifest.key, title=song.title, artist=song.artist)

    # ---------------- 封面 ----------------
    def search_covers(self, request: CoverSearchRequest) -> List[Song]:
        # Musixmatch 封面需要 album_id，直接复用搜索结果候选
        return self.search_songs(SongSearchRequest(
            keyword=request.keyword, page_size=request.page_size))

    def get_cover(self, song: Song) -> Optional[bytes]:
        album_id = (song.internal or {}).get("album_id", "")
        if not album_id:
            return None
        body = self._get("album.get", album_id=album_id)
        if not body:
            return None
        url = (body.get("album") or {}).get("album_coverart_100x100") or ""
        return self._safe_get_bytes(url)
