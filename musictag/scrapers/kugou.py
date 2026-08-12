# -*- coding: utf-8 -*-
"""酷狗音乐插件 —— 对齐 Lyrico-Plugins 的酷狗插件。

  * 搜索:  mobilecdn.kugou.com /api/v3/search/song
  * 歌词:  m.kugou.com /app/i/krc.php（base64 加密 KRC -> XOR+zlib 解密）
  * 封面:  kugou.com yy getdata（尽力而为）
KRC 按词级解析，[language] 标签（base64 JSON）解析为罗马音行。
"""
from __future__ import annotations
import base64
from typing import List, Optional

from ..lyrics.parser import decrypt_krc
from .base import (LyricsRequest, LyricsResult, Plugin, PluginManifest,
                   Song, SongSearchRequest)
from .lyric_utils import (merge_lyrics, parse_krc_lines, parse_lrc_lines)

SEARCH_URL = "https://mobilecdn.kugou.com/api/v3/search/song"
KRC_URL = "https://m.kugou.com/app/i/krc.php"
GETDATA_URL = "https://www.kugou.com/yy/index.php"

_HEADERS = {"Referer": "https://www.kugou.com"}


class KugouPlugin(Plugin):
    manifest = PluginManifest(
        id="com.kugou.source",
        key="kugou",
        name="酷狗音乐",
        version="0.3.0",
        author="MusicTag",
        description="酷狗搜索源插件：搜索歌曲、获取词级 KRC 歌词（含罗马音）与封面",
        capabilities=["searchSongs", "getLyrics", "searchCovers"],
    )

    def search_songs(self, request: SongSearchRequest) -> List[Song]:
        try:
            data = self.net.get_json(SEARCH_URL, params={
                "format": "json", "keyword": request.keyword,
                "page": request.page, "pagesize": request.page_size, "showtype": 1,
            })
        except Exception:
            return []
        info = ((data or {}).get("data") or {}).get("info") or []
        out = []
        for s in info:
            name = str(s.get("singername", ""))
            fields = {
                "title": str(s.get("songname", "")),
                "artist": name,
                "album": str(s.get("album_name", "")),
                "language": "zh",
            }
            out.append(Song(
                id=str(s.get("hash", "")), title=fields["title"], artist=name,
                album=fields["album"], duration=float(s.get("duration") or 0),
                source=self.manifest.key, source_name=self.manifest.name,
                fields=fields,
                internal={"album_id": str(s.get("album_id", "")),
                          "album_audio_id": str(s.get("album_audio_id", ""))},
            ))
        return out

    def get_lyrics(self, request: LyricsRequest) -> Optional[LyricsResult]:
        song = request.song
        if song is None or not song.id:
            return None
        try:
            resp = self.net.get(KRC_URL, params={
                "cmd": 100, "keyword": song.keyword(),
                "hash": song.id, "timelength": int(song.duration * 1000),
            }, headers=_HEADERS)
        except Exception:
            return None
        body = resp.text.strip()
        if not body:
            return None
        try:
            krc_text = decrypt_krc(base64.b64decode(body))
        except Exception:
            return None
        original = parse_krc_lines(krc_text)
        if not original:
            return None
        romanization = parse_krc_lines(krc_text, language=True)
        tags = {"ti": song.title, "ar": song.artist, "al": song.album}
        return LyricsResult(
            type="structured", tags=tags, original=original,
            romanization=merge_lyrics(original, romanization),
            format="krc", source=self.manifest.key,
            title=song.title, artist=song.artist,
        )

    def get_cover(self, song: Song) -> Optional[bytes]:
        if not song.id:
            return None
        try:
            data = self.net.get_json(GETDATA_URL, params={
                "r": "play/getdata", "hash": song.id,
            }, headers=_HEADERS)
            img = (((data or {}).get("data") or {}).get("img") or "")
            if not img:
                return None
            return self.net.get_bytes(img, headers=_HEADERS)
        except Exception:
            return None
