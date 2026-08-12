# -*- coding: utf-8 -*-
"""网易云音乐插件 —— 对齐 Lyrico-Plugins 的网易插件。

接口（公开 Web 接口，尽力而为）：
  * 搜索:  /api/search/get/web
  * 歌词:  /api/song/lyric?id=..&lv=1&kv=1&tv=1&rv=1&yv=1
    返回 lrc / tlyric（译文）/ romalrc（罗马音）/ yrc（逐字，YRC 或富文本 JSON）
歌词按 Lyrico 语义组织为 structured：
  original     优先逐字 YRC，否则富文本 JSON，否则普通 LRC
  translated   原文行 + 译文行合并
  romanization 原文行 + 罗马音行合并
"""
from __future__ import annotations
from typing import List, Optional

from .base import (CoverSearchRequest, LyricsRequest, LyricsResult, Plugin,
                   PluginConfigField, PluginManifest, Song, SongSearchRequest)
from .lyric_utils import (merge_lyrics, parse_lrc_lines,
                          parse_netease_original, parse_rich_json_lines)

SEARCH_URL = "https://music.163.com/api/search/get/web"
LYRIC_URL = "https://music.163.com/api/song/lyric"

_HEADERS = {
    "Referer": "https://music.163.com",
    "Cookie": "os=pc; appver=8.0.0; osver=10",
}


class NeteasePlugin(Plugin):
    manifest = PluginManifest(
        id="com.neteasecloudmusic.source",
        key="netease",
        name="网易云音乐",
        version="0.3.0",
        author="MusicTag",
        description="网易云搜索源插件：搜索歌曲、获取三语歌词与封面",
        capabilities=["searchSongs", "getLyrics", "searchCovers"],
        config_fields=[
            PluginConfigField(
                key="comment_content", title="注释写入内容",
                summary="控制搜索结果写入注释字段的内容",
                group="元数据", type="dropdown", default="alias",
                options=[{"value": "none", "label": "不写入"},
                         {"value": "alias", "label": "歌曲别名"}]),
        ],
    )

    # ---------------- 搜索 ----------------
    def search_songs(self, request: SongSearchRequest) -> List[Song]:
        try:
            data = self.net.get_json(SEARCH_URL, params={
                "s": request.keyword, "type": 1,
                "offset": max(0, (request.page - 1) * request.page_size),
                "limit": request.page_size,
            }, headers=_HEADERS)
        except Exception:
            return []
        songs = ((data or {}).get("result") or {}).get("songs") or []
        sep = request.separator or "/"
        out = []
        for s in songs:
            artists = [a.get("name", "") for a in (s.get("artists") or []) if a.get("name")]
            album = s.get("album") or {}
            pic = str(album.get("picUrl") or "").replace("http:", "https:")
            if pic and "?" not in pic:
                pic += "?param=300y300"
            artist_text = sep.join(a for a in artists if a)
            publish = s.get("publishTime") or s.get("publishTimeMs") or album.get("publishTime") or 0
            date = _format_publish(publish)
            alias = [str(a) for a in (s.get("alias") or s.get("alia") or []) if a]
            comment = ""
            if self._plugin_config().get("comment_content", "alias") == "alias":
                comment = " / ".join(alias)
            fields = {
                "title": str(s.get("name", "")),
                "artist": artist_text,
                "album": str(album.get("name", "")),
                "date": date,
                "track_number": str(s.get("no") or ""),
                "disc_number": str(s.get("cd") or ""),
                "cover_url": pic,
                "language": "zh",
            }
            if comment:
                fields["comment"] = comment
            out.append(Song(
                id=str(s.get("id", "")), title=fields["title"], artist=artist_text,
                album=fields["album"], duration=float(s.get("duration") or 0) / 1000.0,
                date=date, track_number=fields["track_number"],
                disc_number=fields["disc_number"], cover_url=pic,
                source=self.manifest.key, source_name=self.manifest.name,
                fields=fields,
                internal={"albumId": str(album.get("id", ""))},
            ))
        return out

    # ---------------- 歌词 ----------------
    def get_lyrics(self, request: LyricsRequest) -> Optional[LyricsResult]:
        song = request.song
        if song is None or not song.id:
            return None
        try:
            data = self.net.get_json(LYRIC_URL, params={
                "id": song.id, "lv": 1, "kv": 1, "tv": 1, "rv": 1, "yv": 1,
            }, headers=_HEADERS)
        except Exception:
            return None
        lrc = ((data or {}).get("lrc") or {}).get("lyric") or ""
        tlyric = ((data or {}).get("tlyric") or {}).get("lyric") or ""
        romalrc = ((data or {}).get("romalrc") or {}).get("lyric") or ""
        yrc = ((data or {}).get("yrc") or {}).get("lyric") or ""

        tags = {"ti": song.title, "ar": song.artist, "al": song.album}
        if song.date:
            tags["date"] = song.date

        original = parse_netease_original(yrc, lrc)
        if not original:
            # 部分歌曲无时间轴，返回纯文本
            plain = (yrc or lrc or "").strip()
            if not plain:
                return None
            return LyricsResult(type="structured", tags=tags, plain=plain,
                                format="plain", source=self.manifest.key,
                                title=song.title, artist=song.artist)

        return LyricsResult(
            type="structured", tags=tags,
            original=original,
            translated=merge_lyrics(original, parse_lrc_lines(tlyric)),
            romanization=merge_lyrics(original, parse_lrc_lines(romalrc)),
            format="yrc" if yrc else "lrc",
            source=self.manifest.key, title=song.title, artist=song.artist,
        )

    # ---------------- 封面 ----------------
    def get_cover(self, song: Song) -> Optional[bytes]:
        return self._safe_get_bytes(song.cover_url)


def _format_publish(ms) -> str:
    import datetime
    try:
        ms = int(ms or 0)
        if ms <= 0:
            return ""
        return datetime.datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d")
    except Exception:
        return ""
