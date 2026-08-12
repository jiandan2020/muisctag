# -*- coding: utf-8 -*-
"""应用配置：JSON 持久化到用户目录，带默认值合并。"""
from __future__ import annotations
import json
import os
from typing import Any, Dict
from .. import APP_NAME

_DEFAULTS: Dict[str, Any] = {
    "network": {
        "timeout": 15,
        "retries": 2,
        "delay": 0.4,          # 每次请求间隔（秒），用于缓解反爬
        "proxy": "",           # 例如 http://127.0.0.1:7890
        "rotate_ua": True,
    },
    "scrape": {
        "id3_version": "v2.3",      # 写入 MP3 时使用的 ID3 版本
        "save_cover": True,         # 刮削时同时写入封面
        "save_lyrics": True,        # 刮削时同时写入歌词
        "cover_size": 300,          # 封面尺寸（px，0 表示原图）
        "lyric_pref": "synced",     # synced / plain
        "max_results": 10,          # 每平台搜索条数
    },
    "translate": {
        "engine": "google",         # google / bing / openai / mymemory
        "openai_base_url": "https://api.openai.com/v1",
        "openai_api_key": "",
        "openai_model": "gpt-4o-mini",
        "openai_timeout": 60,
    },
    "general": {
        "threads": 4,               # 批处理线程数
        "backup": True,             # 修改前自动备份标签
        "language": "zh-CN",
    },
}


def config_dir() -> str:
    """配置目录（%APPDATA%/MusicTag）。"""
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "MusicTag")
    os.makedirs(d, exist_ok=True)
    return d


def config_path() -> str:
    return os.path.join(config_dir(), "config.json")


def load_config() -> Dict[str, Any]:
    """读取配置，与默认值深度合并。"""
    def deep_merge(base: Dict, override: Dict) -> Dict:
        out = dict(base)
        for k, v in override.items():
            if isinstance(v, dict) and isinstance(out.get(k), dict):
                out[k] = deep_merge(out[k], v)
            else:
                out[k] = v
        return out

    cfg = deep_merge(_DEFAULTS, {})
    try:
        with open(config_path(), "r", encoding="utf-8") as f:
            saved = json.load(f)
        cfg = deep_merge(cfg, saved)
    except FileNotFoundError:
        pass
    except Exception:
        pass
    return cfg


def save_config(cfg: Dict[str, Any]) -> None:
    with open(config_path(), "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def default_config() -> Dict[str, Any]:
    import copy
    return copy.deepcopy(_DEFAULTS)
