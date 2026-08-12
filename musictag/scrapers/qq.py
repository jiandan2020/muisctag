# -*- coding: utf-8 -*-
"""QQ 音乐插件 —— 对齐 Lyrico-Plugins 的 QQ 插件。

接口（公开接口，尽力而为）：
  * 搜索:  c.y.qq.com client_search_cp
  * 歌词:  fcg_query_lyric_new.fcg（返回 base64 的 LRC 原文 + trans 译文 + roma 罗马音）
歌词同样组织为 structured：original / translated / romanization。
"""
from __future__ import annotations
import base64
from typing import List, Optional

from .base import (LyricsRequest, LyricsResult, Plugin, PluginManifest,
                   Song, SongSearchRequest)
from .lyric_utils import merge_lyrics, parse_lrc_lines

SEARCH_URL = "https://c.y.qq.com/soso/fcgi-bin/client_search_cp"
LYRIC_URL = "https://c.y.qq.com/lyric/fcgi-bin/fcg_query_lyric_new.fcg"

_HEADERS = {"Referer": "https://y.qq.com/portal/player.html"}


class QQPlugin(Plugin):
    manifest = PluginManifest(
        id="com.qqmusic.source",
        key="qq",
        name="QQ音乐",
        version="0.3.0",
        author="MusicTag",
        description="QQ音乐搜索源插件：搜索歌曲、获取原文/译文/罗马音歌词与封面",
        capabilities=["searchSongs", "getLyrics", "searchCovers"],
    )

    def search_songs(self, request: SongSearchRequest) -> List[Song]:
        try:
            data = self.net.get_json(SEARCH_URL, params={
                "w": request.keyword, "format": "json",
                "p": request.page, "n": request.page_size,
                "cr": 1, "g_tk": 5381, "loginUin": 0, "hostUin": 0,
                "inCharset": "utf8", "outCharset": "utf-8", "notice": 0,
                "platform": "yqq.json", "needNewCode": 0,
            }, headers=_HEADERS)
        except Exception:
            return []
        song_list = (((data or {}).get("data") or {}).get("song") or {}).get("list") or []
        sep = request.separator or "/"
        out = []
        for s in song_list:
            album = s.get("albumname") or ""
            if isinstance(s.get("album"), dict):
                album = s.get("album", {}).get("name", album)
            albummid = s.get("albummid") or ""
            if not albummid and isinstance(s.get("album"), dict):
                albummid = s.get("album", {}).get("mid", "")
            cover = f"https://y.gtimg.cn/music/photo_new/T002R300x300M000{albummid}.jpg" if albummid else ""
            singers = [sg.get("name", "") for sg in (s.get("singer") or []) if sg.get("name")]
            artist_text = sep.join(singers)
            year = ""
            if isinstance(s.get("album"), dict) and s["album"].get("time_public"):
                year = str(s["album"]["time_public"])[:4]
            fields = {
                "title": str(s.get("songname", "")),
                "artist": artist_text,
                "album": album,
                "cover_url": cover,
                "language": "zh",
            }
            if year:
                fields["date"] = year
            out.append(Song(
                id=str(s.get("songmid", "")), title=fields["title"], artist=artist_text,
                album=album, duration=float(s.get("interval") or 0),
                date=year, cover_url=cover,
                source=self.manifest.key, source_name=self.manifest.name,
                fields=fields,
                internal={"songid": str(s.get("songid", "")), "albummid": albummid},
            ))
        return out

    def get_lyrics(self, request: LyricsRequest) -> Optional[LyricsResult]:
        song = request.song
        if song is None or not song.id:
            return None
        try:
            data = self.net.get_json(LYRIC_URL, params={
                "songmid": song.id, "format": "json", "nobase64": 1,
                "g_tk": 5381, "loginUin": 0, "hostUin": 0, "inCharset": "utf8",
                "outCharset": "utf-8", "notice": 0, "platform": "yqq.json",
            }, headers=_HEADERS)
        except Exception:
            return None
        if not (data or {}).get("lyric"):
            return None
        lyric = _b64(data.get("lyric"))
        trans = _b64(data.get("trans"))
        roma = _b64(data.get("roma"))
        tags = {"ti": song.title, "ar": song.artist, "al": song.album}
        if song.date:
            tags["date"] = song.date

        original = parse_lrc_lines(lyric)
        if not original:
            plain = lyric.strip()
            if not plain:
                return None
            return LyricsResult(type="structured", tags=tags, plain=plain,
                                format="plain", source=self.manifest.key,
                                title=song.title, artist=song.artist)

        return LyricsResult(
            type="structured", tags=tags, original=original,
            translated=merge_lyrics(original, parse_lrc_lines(trans)),
            romanization=merge_lyrics(original, parse_lrc_lines(roma)),
            format="lrc", source=self.manifest.key,
            title=song.title, artist=song.artist,
        )

    def get_cover(self, song: Song) -> Optional[bytes]:
        return self._safe_get_bytes(song.cover_url)


def _b64(value) -> str:
    if not value:
        return ""
    try:
        return base64.b64decode(str(value)).decode("utf-8", "replace")
    except Exception:
        return ""
