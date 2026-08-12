# -*- coding: utf-8 -*-
"""Lrclib 插件：无需 API Key 的公共歌词数据库，提供同步/纯文本歌词。"""
from __future__ import annotations
from typing import List, Optional

from .base import (LyricsRequest, LyricsResult, Plugin, PluginManifest,
                   Song, SongSearchRequest)
from .lyric_utils import parse_lrc_lines

SEARCH_URL = "https://lrclib.net/api/search"


class LrclibPlugin(Plugin):
    manifest = PluginManifest(
        id="com.lrclib.source",
        key="lrclib",
        name="Lrclib",
        version="0.2.0",
        author="MusicTag",
        description="Lrclib 公共歌词库：搜索歌曲与同步/纯文本歌词",
        capabilities=["searchSongs", "getLyrics"],
    )

    def search_songs(self, request: SongSearchRequest) -> List[Song]:
        try:
            items = self.net.get_json(SEARCH_URL, params={
                "q": request.keyword, "page_size": request.page_size,
            })
        except Exception:
            return []
        if not isinstance(items, list):
            return []
        out = []
        for it in items:
            artist = str(it.get("artistName", ""))
            fields = {
                "title": str(it.get("trackName", "")),
                "artist": artist,
                "album": str(it.get("albumName", "")),
                "cover_url": "",
            }
            out.append(Song(
                id=str(it.get("id", "")), title=fields["title"], artist=artist,
                album=fields["album"], duration=float(it.get("duration", 0) or 0),
                source=self.manifest.key, source_name=self.manifest.name,
                fields=fields,
                internal={"syncedLyrics": it.get("syncedLyrics", ""),
                          "plainLyrics": it.get("plainLyrics", "")},
            ))
        return out

    def get_lyrics(self, request: LyricsRequest) -> Optional[LyricsResult]:
        song = request.song
        if song is None:
            return None
        synced = (song.internal or {}).get("syncedLyrics", "")
        plain = (song.internal or {}).get("plainLyrics", "")
        original = parse_lrc_lines(synced)
        tags = {"ti": song.title, "ar": song.artist, "al": song.album}
        if not original:
            if not plain:
                return None
            return LyricsResult(type="structured", tags=tags, plain=plain,
                                format="plain", source=self.manifest.key,
                                title=song.title, artist=song.artist)
        return LyricsResult(type="structured", tags=tags, original=original,
                            format="lrc", source=self.manifest.key,
                            title=song.title, artist=song.artist)
