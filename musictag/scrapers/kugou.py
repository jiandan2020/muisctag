# -*- coding: utf-8 -*-
"""酷狗音乐插件。

  * 搜索: mobilecdn.kugou.com /api/v3/search/song
  * 歌词: m.kugou.com /app/i/krc.php（返回 base64 加密 KRC，需解密）
  * 封面: kugou.com yy getdata 接口（尽力而为）
"""
from __future__ import annotations
import base64
import re
from typing import List, Optional
from ..lyrics.parser import decrypt_krc, parse_krc
from .base import LyricResult, ScraperPlugin, TrackMatch

SEARCH_URL = "https://mobilecdn.kugou.com/api/v3/search/song"
KRC_URL = "https://m.kugou.com/app/i/krc.php"
GETDATA_URL = "https://www.kugou.com/yy/index.php"

_HEADERS = {"Referer": "https://www.kugou.com"}


class KugouPlugin(ScraperPlugin):
    name = "kugou"
    display_name = "酷狗音乐"

    def search(self, keyword: str, limit: int = 10) -> List[TrackMatch]:
        try:
            data = self.net.get_json(SEARCH_URL, params={
                "format": "json", "keyword": keyword, "page": 1,
                "pagesize": limit, "showtype": 1,
            })
        except Exception:
            return []
        info = ((data or {}).get("data") or {}).get("info") or []
        out = []
        for s in info:
            out.append(TrackMatch(
                title=s.get("songname", ""),
                artists=[s.get("singername", "")] if s.get("singername") else [],
                album=s.get("album_name", ""),
                source=self.name, source_name=self.display_name,
                track_id=s.get("hash", ""),
                album_id=str(s.get("album_id", "")),
                duration=int(s.get("duration") or 0),
                cover_url="",
                extra={"album_audio_id": s.get("album_audio_id", "")},
                raw=s,
            ))
        return out

    def get_lyrics(self, track: TrackMatch) -> Optional[LyricResult]:
        if not track.track_id:
            return None
        try:
            resp = self.net.get(KRC_URL, params={
                "cmd": 100, "keyword": f"{track.title} {track.artist_text}",
                "hash": track.track_id, "timelength": int(track.duration * 1000),
            }, headers=_HEADERS)
        except Exception:
            return None
        body = resp.text.strip()
        if not body:
            return None
        raw = b""
        try:
            raw = base64.b64decode(body)
        except Exception:
            return None
        lyrics = parse_krc(decrypt_krc(raw))
        synced = ""
        try:
            from ..lyrics.converter import to_lrc
            synced = to_lrc(lyrics)
        except Exception:
            synced = lyrics.plain_text()
        if not synced:
            return None
        return LyricResult(
            synced=synced, plain=lyrics.plain_text(), format="lrc",
            source=self.name, title=track.title, artist=track.artist_text,
        )

    def get_cover(self, track: TrackMatch) -> Optional[bytes]:
        if not track.track_id:
            return None
        try:
            data = self.net.get_json(GETDATA_URL, params={
                "r": "play/getdata", "hash": track.track_id,
            }, headers=_HEADERS)
            img = (((data or {}).get("data") or {}).get("img") or "")
            if not img:
                return None
            return self.net.get_bytes(img, headers=_HEADERS)
        except Exception:
            return None
