# -*- coding: utf-8 -*-
"""网易云音乐插件（无需登录的公开接口）。

接口说明（均为公开 Web/移动端接口，做尽力而为的兼容）：
  * 搜索:   /api/search/get/web
  * 歌词:   /api/song/lyric
  * 封面:   搜索结果中的 album.picUrl + ?param=300y300
"""
from __future__ import annotations
from typing import List, Optional
from .base import LyricResult, ScraperPlugin, TrackMatch

SEARCH_URL = "https://music.163.com/api/search/get/web"
LYRIC_URL = "https://music.163.com/api/song/lyric"

_HEADERS = {
    "Referer": "https://music.163.com",
    "Cookie": "os=pc; appver=8.0.0; osver=10",
}


class NeteasePlugin(ScraperPlugin):
    name = "netease"
    display_name = "网易云音乐"

    def search(self, keyword: str, limit: int = 10) -> List[TrackMatch]:
        try:
            data = self.net.get_json(SEARCH_URL, params={
                "s": keyword, "type": 1, "offset": 0, "limit": limit,
            }, headers=_HEADERS)
        except Exception:
            return []
        songs = ((data or {}).get("result") or {}).get("songs") or []
        out = []
        for s in songs:
            artists = [a.get("name", "") for a in (s.get("artists") or []) if a.get("name")]
            album = s.get("album") or {}
            pic = album.get("picUrl") or ""
            if pic and "?" not in pic:
                pic = pic + "?param=300y300"
            out.append(TrackMatch(
                title=s.get("name", ""),
                artists=[a for a in artists if a],
                album=album.get("name", ""),
                source=self.name, source_name=self.display_name,
                track_id=str(s.get("id", "")),
                album_id=str(album.get("id", "")),
                duration=(s.get("duration") or 0) / 1000.0,
                cover_url=pic,
                raw=s,
            ))
        return out

    def get_lyrics(self, track: TrackMatch) -> Optional[LyricResult]:
        if not track.track_id:
            return None
        try:
            data = self.net.get_json(LYRIC_URL, params={
                "id": track.track_id, "lv": 1, "kv": 1, "tv": -1,
            }, headers=_HEADERS)
        except Exception:
            return None
        lrc = ((data or {}).get("lrc") or {}).get("lyric") or ""
        tlyric = ((data or {}).get("tlyric") or {}).get("lyric") or ""
        if not lrc and not tlyric:
            return None
        # 网易云返回的 "纯音乐，请欣赏" 视为无歌词
        if lrc.strip() == "[00:00.000] 纯音乐，请欣赏":
            lrc = ""
        return LyricResult(
            synced=lrc.strip(),
            plain="",
            translation=tlyric.strip(),
            format="lrc",
            source=self.name,
            title=track.title,
            artist=track.artist_text,
        )

    def get_cover(self, track: TrackMatch) -> Optional[bytes]:
        return self._safe_get_bytes(track.cover_url)
