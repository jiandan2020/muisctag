# -*- coding: utf-8 -*-
"""QQ 音乐插件（c.y.qq.com 公开搜索接口 + 歌词接口）。"""
from __future__ import annotations
import base64
from typing import List, Optional
from .base import LyricResult, ScraperPlugin, TrackMatch

SEARCH_URL = "https://c.y.qq.com/soso/fcgi-bin/client_search_cp"
LYRIC_URL = "https://c.y.qq.com/lyric/fcgi-bin/fcg_query_lyric_new.fcg"

_HEADERS = {"Referer": "https://y.qq.com/portal/player.html"}


class QQPlugin(ScraperPlugin):
    name = "qq"
    display_name = "QQ音乐"

    def search(self, keyword: str, limit: int = 10) -> List[TrackMatch]:
        try:
            data = self.net.get_json(SEARCH_URL, params={
                "w": keyword, "format": "json", "p": 1, "n": limit,
                "cr": 1, "g_tk": 5381, "loginUin": 0, "hostUin": 0,
                "inCharset": "utf8", "outCharset": "utf-8", "notice": 0,
                "platform": "yqq.json", "needNewCode": 0,
            }, headers=_HEADERS)
        except Exception:
            return []
        song_list = (((data or {}).get("data") or {}).get("song") or {}).get("list") or []
        out = []
        for s in song_list:
            album = s.get("albumname") or s.get("album", {}).get("name", "") if isinstance(s.get("album"), dict) else s.get("albumname", "")
            albummid = s.get("albummid") or ""
            if not albummid and isinstance(s.get("album"), dict):
                albummid = s.get("album", {}).get("mid", "")
            cover = f"https://y.gtimg.cn/music/photo_new/T002R300x300M000{albummid}.jpg" if albummid else ""
            out.append(TrackMatch(
                title=s.get("songname", ""),
                artists=[sg.get("name", "") for sg in (s.get("singer") or []) if sg.get("name")],
                album=album,
                source=self.name, source_name=self.display_name,
                track_id=str(s.get("songmid", "")),
                album_id=albummid,
                duration=int(s.get("interval") or 0),
                cover_url=cover,
                raw=s,
            ))
        return out

    def get_lyrics(self, track: TrackMatch) -> Optional[LyricResult]:
        if not track.track_id:
            return None
        try:
            data = self.net.get_json(LYRIC_URL, params={
                "songmid": track.track_id, "format": "json", "nobase64": 1,
            }, headers=_HEADERS)
        except Exception:
            return None
        lyric_b64 = (data or {}).get("lyric") or ""
        trans_b64 = (data or {}).get("trans") or ""
        if not lyric_b64:
            return None
        try:
            lyric = base64.b64decode(lyric_b64).decode("utf-8", "replace")
            trans = base64.b64decode(trans_b64).decode("utf-8", "replace") if trans_b64 else ""
        except Exception:
            return None
        return LyricResult(
            synced=lyric.strip(), plain="", translation=trans.strip(),
            format="lrc", source=self.name,
            title=track.title, artist=track.artist_text,
        )

    def get_cover(self, track: TrackMatch) -> Optional[bytes]:
        return self._safe_get_bytes(track.cover_url)
