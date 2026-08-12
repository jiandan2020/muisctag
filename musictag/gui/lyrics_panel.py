# -*- coding: utf-8 -*-
"""右侧歌词面板：编辑、预览、保存、转换、时间调整、翻译。"""
from __future__ import annotations
from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QLineEdit,
                               QPlainTextEdit, QPushButton, QSpinBox,
                               QVBoxLayout, QWidget)

from ..lyrics.converter import convert_text, adjust_time
from ..lyrics.parser import parse_text

_OUT_FORMATS = [("LRC（时间轴）", "lrc"), ("SRT 字幕", "srt"),
                ("ASS 字幕", "ass"), ("TTML", "ttml"), ("纯文本", "plain")]


class LyricsPanel(QWidget):
    """歌词编辑与预览面板。"""

    save_requested = Signal(str)          # 保存到标签
    fetch_requested = Signal()
    translate_requested = Signal(str, str)  # (引擎, 目标语言)
    status_message = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText("歌词编辑区…\n支持 LRC / SRT / ASS / TTML / 纯文本，可直接粘贴")

        # 工具行 1
        btn_fetch = QPushButton("从网络获取")
        btn_save = QPushButton("保存到标签")
        btn_open = QPushButton("打开歌词文件")
        btn_fetch.clicked.connect(self.fetch_requested)
        btn_save.clicked.connect(lambda: self.save_requested.emit(self.editor.toPlainText()))
        btn_open.clicked.connect(self._open_file)

        row1 = QHBoxLayout()
        for b in (btn_fetch, btn_save, btn_open):
            row1.addWidget(b)

        # 工具行 2：格式转换 + 时间调整
        self.cmb_format = QComboBox()
        for label, _ in _OUT_FORMATS:
            self.cmb_format.addItem(label)
        btn_convert = QPushButton("转换格式")
        btn_convert.clicked.connect(self._convert)

        self.spin_delta = QSpinBox()
        self.spin_delta.setRange(-300000, 300000)
        self.spin_delta.setSuffix(" ms")
        self.spin_delta.setValue(0)
        btn_adjust = QPushButton("时间平移")
        btn_adjust.clicked.connect(self._adjust)

        self.cmb_engine = QComboBox()
        for e in ("google", "bing", "openai", "mymemory"):
            self.cmb_engine.addItem(e)
        self.cmb_lang = QComboBox()
        for code, name in (("zh", "简体中文"), ("zh-Hant", "繁体中文"), ("en", "英语"),
                           ("ja", "日语"), ("ko", "韩语"), ("fr", "法语"),
                           ("de", "德语"), ("es", "西班牙语")):
            self.cmb_lang.addItem(name, code)
        btn_translate = QPushButton("翻译歌词")
        btn_translate.clicked.connect(
            lambda: self.translate_requested.emit(self.cmb_engine.currentText(),
                                                  self.cmb_lang.currentData()))

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("转换:"))
        row2.addWidget(self.cmb_format)
        row2.addWidget(btn_convert)
        row2.addSpacing(8)
        row2.addWidget(QLabel("平移:"))
        row2.addWidget(self.spin_delta)
        row2.addWidget(btn_adjust)
        row2.addStretch(1)
        row2.addWidget(QLabel("翻译:"))
        row2.addWidget(self.cmb_engine)
        row2.addWidget(self.cmb_lang)
        row2.addWidget(btn_translate)

        self.lbl_info = QLabel("未加载歌词")
        self.lbl_info.setStyleSheet("color:#888;")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.addLayout(row1)
        lay.addLayout(row2)
        lay.addWidget(self.editor)
        lay.addWidget(self.lbl_info)

    # ---------------- 公共方法 ----------------
    def set_text(self, text: str) -> None:
        self.editor.setPlainText(text)
        self._update_info()

    def text(self) -> str:
        return self.editor.toPlainText()

    def set_engines(self, engines: list) -> None:
        cur = self.cmb_engine.currentText()
        self.cmb_engine.clear()
        for e in engines:
            self.cmb_engine.addItem(e)
        if cur:
            idx = self.cmb_engine.findText(cur)
            if idx >= 0:
                self.cmb_engine.setCurrentIndex(idx)

    def _update_info(self):
        text = self.editor.toPlainText()
        if not text.strip():
            self.lbl_info.setText("未加载歌词")
            return
        try:
            lyrics = parse_text(text)
            n = len(lyrics.lines)
            with_words = sum(1 for ln in lyrics.lines if ln.has_word_times)
            meta = lyrics.meta
            parts = [f"{n} 行"]
            if with_words:
                parts.append(f"逐字 {with_words} 行")
            if meta.get("ti"):
                parts.append(f"标题: {meta['ti']}")
            if meta.get("ar"):
                parts.append(f"艺术家: {meta['ar']}")
            self.lbl_info.setText(" · ".join(parts))
        except Exception:
            self.lbl_info.setText(f"{len(text.splitlines())} 行")

    def _convert(self):
        text = self.editor.toPlainText()
        if not text.strip():
            return
        target = _OUT_FORMATS[self.cmb_format.currentIndex()][1]
        try:
            out = convert_text(text, target, with_words=True)
            self.editor.setPlainText(out)
            self._update_info()
        except Exception as exc:
            self.status_message.emit(f"转换失败: {exc}")

    def _adjust(self):
        text = self.editor.toPlainText()
        if not text.strip():
            return
        delta = self.spin_delta.value()
        try:
            lyrics = parse_text(text)
            adjust_time(lyrics, delta)
            from ..lyrics.converter import to_lrc
            self.editor.setPlainText(to_lrc(lyrics, with_words=True))
            self._update_info()
        except Exception as exc:
            self.status_message.emit(f"时间调整失败: {exc}")

    def _open_file(self):
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self, "打开歌词文件", "",
            "歌词文件 (*.lrc *.srt *.ass *.ttml *.xml *.qrc *.krc *.yrc *.txt);;所有文件 (*.*)")
        if not path:
            return
        try:
            with open(path, "rb") as f:
                raw = f.read()
            ext = path.rsplit(".", 1)[-1].lower()
            if ext == "qrc":
                from ..lyrics.parser import decrypt_qrc_bytes
                lyrics = decrypt_qrc_bytes(raw)
                from ..lyrics.converter import to_lrc
                self.editor.setPlainText(to_lrc(lyrics, with_words=True))
            elif ext == "krc":
                from ..lyrics.parser import decrypt_krc_bytes
                lyrics = decrypt_krc_bytes(raw)
                from ..lyrics.converter import to_lrc
                self.editor.setPlainText(to_lrc(lyrics, with_words=True))
            else:
                self.editor.setPlainText(raw.decode("utf-8", "replace"))
            self._update_info()
        except Exception as exc:
            self.status_message.emit(f"打开失败: {exc}")
