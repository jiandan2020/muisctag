# -*- coding: utf-8 -*-
"""歌词翻译引擎。

支持：
  * google   —— translate.googleapis.com 免费接口（无需密钥）
  * bing     —— cn.bing.com ttranslatev3 网页接口（尽力而为，可能需 Cookie）
  * openai   —— OpenAI 兼容 Chat Completions API（需配置 base_url / key / model）
  * mymemory —— MyMemory 免费翻译 API（无需密钥，适合兜底）
"""
from __future__ import annotations
import html
import json
from typing import Any, Dict, List, Optional
from ..utils.network import Network, NetworkError

#: 语言代码提示（用于 OpenAI 提示词）
LANG_NAMES = {
    "zh": "简体中文", "zh-Hant": "繁体中文", "en": "英语", "ja": "日语",
    "ko": "韩语", "fr": "法语", "de": "德语", "es": "西班牙语",
    "ru": "俄语", "it": "意大利语", "pt": "葡萄牙语", "th": "泰语",
    "vi": "越南语", "id": "印尼语", "auto": "自动检测",
}

#: 单次请求最大字符数（避免 URL 过长 / 超时）
_MAX_CHARS = 1500


class TranslateError(Exception):
    """翻译异常。"""


def _chunk_text(text: str, max_chars: int = _MAX_CHARS) -> List[str]:
    """按行切分文本，保证每块不超过 max_chars。"""
    if len(text) <= max_chars:
        return [text] if text.strip() else []
    chunks: List[str] = []
    cur: List[str] = []
    cur_len = 0
    for line in text.split("\n"):
        line_len = len(line) + 1
        if cur and cur_len + line_len > max_chars:
            chunks.append("\n".join(cur))
            cur, cur_len = [], 0
        if line_len > max_chars:
            # 超长单行按字符硬切
            for i in range(0, len(line), max_chars):
                chunks.append(line[i:i + max_chars])
            continue
        cur.append(line)
        cur_len += line_len
    if cur:
        chunks.append("\n".join(cur))
    return chunks


def _translate_google(net: Network, text: str, src: str, dst: str) -> str:
    url = "https://translate.googleapis.com/translate_a/single"
    out: List[str] = []
    for chunk in _chunk_text(text):
        try:
            data = net.get_json(url, params={
                "client": "gtx", "sl": src, "tl": dst, "dt": "t", "q": chunk,
            })
        except NetworkError as exc:
            raise TranslateError(f"Google 翻译请求失败: {exc}") from exc
        try:
            for seg in data[0]:
                if seg and seg[0]:
                    out.append(seg[0])
        except Exception as exc:
            raise TranslateError(f"Google 翻译返回格式异常: {exc}") from exc
    return "".join(out)


def _translate_mymemory(net: Network, text: str, src: str, dst: str) -> str:
    url = "https://api.mymemory.translated.net/get"
    out: List[str] = []
    for chunk in _chunk_text(text):
        try:
            data = net.get_json(url, params={"q": chunk, "langpair": f"{src}|{dst}"})
        except NetworkError as exc:
            raise TranslateError(f"MyMemory 请求失败: {exc}") from exc
        match = (data or {}).get("responseData") or {}
        out.append(match.get("translatedText", ""))
    return "".join(out)


def _translate_bing(net: Network, text: str, src: str, dst: str) -> str:
    """Bing 网页翻译接口（免密钥，但依赖页面 Cookie，可能被限流）。"""
    url = "https://cn.bing.com/ttranslatev3"
    out: List[str] = []
    for chunk in _chunk_text(text):
        try:
            resp = net.post(url, data={
                "fromLang": "auto-detect" if src == "auto" else src,
                "toLang": dst, "text": chunk,
            }, headers={
                "Referer": "https://cn.bing.com/translator",
                "Content-Type": "application/x-www-form-urlencoded",
            })
            data = resp.json()
        except Exception as exc:
            raise TranslateError(f"Bing 翻译请求失败: {exc}") from exc
        try:
            trans = data[0]["translations"][0]["text"]
            out.append(trans)
        except Exception as exc:
            raise TranslateError(f"Bing 翻译返回格式异常: {exc}") from exc
    return "".join(out)


def _translate_openai(net: Network, text: str, src: str, dst: str, cfg: Dict[str, Any]) -> str:
    base = (cfg.get("base_url") or "https://api.openai.com/v1").rstrip("/")
    key = cfg.get("api_key") or ""
    model = cfg.get("model") or "gpt-4o-mini"
    if not key:
        raise TranslateError("未配置 OpenAI API Key（设置 -> 翻译）")
    url = f"{base}/chat/completions"
    src_name = LANG_NAMES.get(src, src)
    dst_name = LANG_NAMES.get(dst, dst)
    out: List[str] = []
    for chunk in _chunk_text(text):
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": (
                    f"你是专业歌词翻译。把输入文本从{src_name}翻译成{dst_name}，"
                    "只输出译文，不要解释、不要添加时间戳或标记。"
                )},
                {"role": "user", "content": chunk},
            ],
            "temperature": 0.3,
        }
        try:
            data = net.post(url, json=payload, headers={"Authorization": f"Bearer {key}"})
            content = (data.json().get("choices") or [{}])[0].get("message", {}).get("content", "")
            out.append(content.strip())
        except Exception as exc:
            raise TranslateError(f"OpenAI 翻译请求失败: {exc}") from exc
    return "\n".join(out)


def translate_text(text: str, dst: str = "zh", src: str = "auto",
                   engine: str = "google",
                   config: Optional[Dict[str, Any]] = None) -> str:
    """翻译一段文本。engine: google / bing / openai / mymemory。"""
    if not text.strip():
        return ""
    cfg = (config or {}).get("translate", {}) if config else {}
    net = Network(config)
    if engine == "google":
        return _translate_google(net, text, src, dst)
    if engine == "bing":
        return _translate_bing(net, text, src, dst)
    if engine == "mymemory":
        return _translate_mymemory(net, text, src, dst)
    if engine == "openai":
        return _translate_openai(net, text, src, dst, cfg)
    raise TranslateError(f"未知翻译引擎: {engine}")


def translate_lyrics(text: str, dst: str = "zh", src: str = "auto",
                     engine: str = "google",
                     config: Optional[Dict[str, Any]] = None) -> str:
    """翻译歌词文本：时间戳行 [mm:ss.xx] 保留，仅翻译歌词内容行。"""
    out: List[str] = []
    meta_lines: List[str] = []
    content_lines: List[str] = []
    for line in text.splitlines():
        if line.startswith("[") and ":" in line[:10]:
            out.append(line)  # 元数据/时间戳行原样保留
        else:
            content_lines.append(line)
    if not content_lines:
        return text
    translated = translate_text("\n".join(content_lines), dst=dst, src=src,
                                engine=engine, config=config)
    out.extend(translated.split("\n"))
    return "\n".join(out)
