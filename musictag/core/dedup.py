# -*- coding: utf-8 -*-
"""重复文件检测。

两级检测：
  1. 音频指纹：对每个文件取头部 64KB + 尾部 64KB 做 SHA-1（同曲不同码率基本同指纹）
  2. 元数据相似度：归一化后的 艺术家+标题 完全一致
两种命中任一即判定为重复，按组输出。
"""
from __future__ import annotations
import hashlib
import os
import re
import unicodedata
from typing import Dict, List, Tuple
from .metadata import AudioFile, MetadataError

_CHUNK = 64 * 1024
_PUNCT = re.compile(r"[\W_]+", re.UNICODE)


def _normalize(text: str) -> str:
    t = unicodedata.normalize("NFKC", (text or "").lower())
    return _PUNCT.sub("", t)


def _read_chunks(path: str, size: int = _CHUNK) -> bytes:
    """读取文件首尾各 size 字节用于指纹。"""
    with open(path, "rb") as f:
        head = f.read(size)
        try:
            f.seek(-size, os.SEEK_END)
            tail = f.read(size)
        except OSError:
            tail = b""
    return head + tail


def audio_fingerprint(path: str) -> str:
    return hashlib.sha1(_read_chunks(path)).hexdigest()


def find_duplicates(paths: List[str]) -> List[List[Dict[str, object]]]:
    """返回重复组列表；每组为 [{path, size, duration, artist, title, fingerprint}]。"""
    by_fp: Dict[str, List[Dict[str, object]]] = {}
    by_meta: Dict[str, List[Dict[str, object]]] = {}

    for path in paths:
        info: Dict[str, object] = {"path": path}
        try:
            info["size"] = os.path.getsize(path)
            info["fingerprint"] = audio_fingerprint(path)
            af = AudioFile(path)
            fields = af.read()
            info["duration"] = round(af.duration, 1)
            artist = ", ".join(fields.get("artists") or [])
            title = str(fields.get("title") or "")
            info["artist"] = artist
            info["title"] = title
            meta_key = f"{_normalize(artist)}|{_normalize(title)}"
            if artist or title:
                by_meta.setdefault(meta_key, []).append(info)
        except MetadataError:
            continue
        except OSError:
            continue

        fp = str(info.get("fingerprint", ""))
        if fp:
            by_fp.setdefault(fp, []).append(info)

    # 合并两组索引
    groups: Dict[str, List[Dict[str, object]]] = {}
    for fp, items in by_fp.items():
        groups.setdefault(fp, []).extend(items)
    for items in by_meta.values():
        if len(items) > 1:
            key = "meta:" + _normalize(str(items[0].get("artist", ""))) + "|" + _normalize(str(items[0].get("title", "")))
            groups.setdefault(key, []).extend(items)

    # 去重（同一文件可能同时命中指纹和元数据）
    seen = set()
    result = []
    for items in groups.values():
        uniq = []
        for it in items:
            p = it["path"]
            if p not in seen:
                seen.add(p)
                uniq.append(it)
        if len(uniq) > 1:
            result.append(uniq)
    return result
