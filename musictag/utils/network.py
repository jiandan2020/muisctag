# -*- coding: utf-8 -*-
"""网络请求封装：User-Agent 轮换、代理、超时与重试。"""
from __future__ import annotations
import random
import time
from typing import Any, Dict, Optional

import requests

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)

UA_POOL = [
    DEFAULT_UA,
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 OPR/106.0.0.0",
]


class NetworkError(Exception):
    """网络请求异常。"""


class Network:
    """带 UA 轮换 / 代理 / 重试的请求器。"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        cfg = config or {}
        net = cfg.get("network", {}) if isinstance(cfg, dict) else {}
        self.timeout = float(net.get("timeout", 15))
        self.retries = int(net.get("retries", 2))
        self.delay = float(net.get("delay", 0.4))
        self.proxy = net.get("proxy", "") or None
        self.rotate_ua = bool(net.get("rotate_ua", True))
        self.session = requests.Session()
        if self.proxy:
            self.session.proxies = {"http": self.proxy, "https": self.proxy}

    # -- 内部 --
    def _headers(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        ua = random.choice(UA_POOL) if self.rotate_ua else DEFAULT_UA
        headers = {"User-Agent": ua, "Accept": "*/*",
                   "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"}
        if extra:
            headers.update(extra)
        return headers

    def _sleep(self) -> None:
        if self.delay > 0:
            time.sleep(self.delay * random.uniform(0.8, 1.2))

    # -- 请求方法 --
    def get(self, url: str, params: Optional[Dict] = None,
            headers: Optional[Dict[str, str]] = None, **kwargs) -> requests.Response:
        last_exc: Optional[Exception] = None
        for attempt in range(self.retries + 1):
            try:
                self._sleep()
                resp = self.session.get(url, params=params, timeout=self.timeout,
                                        headers=self._headers(headers), **kwargs)
                resp.raise_for_status()
                return resp
            except Exception as exc:
                last_exc = exc
                time.sleep(0.5 * (attempt + 1))
        raise NetworkError(f"请求失败: {url} ({last_exc})") from last_exc

    def post(self, url: str, data=None, json=None,
             headers: Optional[Dict[str, str]] = None, **kwargs) -> requests.Response:
        last_exc: Optional[Exception] = None
        for attempt in range(self.retries + 1):
            try:
                self._sleep()
                resp = self.session.post(url, data=data, json=json, timeout=self.timeout,
                                         headers=self._headers(headers), **kwargs)
                resp.raise_for_status()
                return resp
            except Exception as exc:
                last_exc = exc
                time.sleep(0.5 * (attempt + 1))
        raise NetworkError(f"请求失败: {url} ({last_exc})") from last_exc

    def get_json(self, url: str, params: Optional[Dict] = None,
                 headers: Optional[Dict[str, str]] = None) -> Any:
        return self.get(url, params=params, headers=headers).json()

    def get_bytes(self, url: str, headers: Optional[Dict[str, str]] = None) -> bytes:
        return self.get(url, headers=headers).content
