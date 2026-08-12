# -*- coding: utf-8 -*-
"""中间元数据编辑面板：字段按类别分组，支持多文件批量编辑。"""
from __future__ import annotations
from typing import Any, Dict, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QCheckBox, QFileDialog, QFormLayout, QHBoxLayout,
                               QLabel, QLineEdit, QPushButton, QSpinBox,
                               QTabWidget, QTextEdit, QVBoxLayout, QWidget)

from ..core.metadata import empty_fields


class MetadataPanel(QWidget):
    """元数据编辑面板。"""

    save_requested = Signal(dict)          # get_fields() 结果
    infer_requested = Signal()
    scrape_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._fields: Dict[str, Any] = empty_fields()
        self._cover_bytes = b""
        self._cover_mime = ""
        self._build_ui()

    # ---------------- UI ----------------
    def _build_ui(self):
        self.tabs = QTabWidget()

        # 基本信息
        self.ed = {k: QLineEdit() for k in
                   ("title", "album", "artists", "albumartist", "composer",
                    "arranger", "lyricist")}
        basic = QWidget()
        form = QFormLayout(basic)
        labels = {"title": "标题", "album": "专辑", "artists": "艺术家（多个用 / 分隔）",
                  "albumartist": "专辑艺术家", "composer": "作曲者",
                  "arranger": "编曲者", "lyricist": "作词者"}
        for k, line in self.ed.items():
            form.addRow(labels[k], line)
        self.tabs.addTab(basic, "基本信息")

        # 详细信息
        self.num_ed = {k: QLineEdit() for k in
                       ("track", "tracktotal", "disc", "disctotal", "year",
                        "genre", "bpm")}
        self.lbl_duration = QLabel("—")
        detail = QWidget()
        form2 = QFormLayout(detail)
        labels2 = {"track": "曲目编号", "tracktotal": "总曲数", "disc": "碟片编号",
                   "disctotal": "总碟数", "year": "发行年份", "genre": "流派", "bpm": "BPM"}
        for k, line in self.num_ed.items():
            form2.addRow(labels2[k], line)
        form2.addRow("时长", self.lbl_duration)
        self.tabs.addTab(detail, "详细信息")

        # 扩展信息
        self.lyrics_edit = QTextEdit()
        self.lyrics_edit.setPlaceholderText("在此粘贴歌词（支持 LRC / SRT / ASS / TTML 等格式）…")
        self.long_ed = {k: QLineEdit() for k in
                        ("isrc", "copyright", "publisher", "comment", "encoder")}
        extra = QWidget()
        form3 = QFormLayout(extra)
        form3.addRow("歌词", self.lyrics_edit)
        labels3 = {"isrc": "ISRC", "copyright": "版权", "publisher": "出版商",
                   "comment": "注释", "encoder": "编码者"}
        for k, line in self.long_ed.items():
            form3.addRow(labels3[k], line)
        self.tabs.addTab(extra, "扩展信息")

        # 封面
        cover = QWidget()
        cover_lay = QVBoxLayout(cover)
        self.cover_preview = QLabel("无封面")
        self.cover_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover_preview.setMinimumHeight(220)
        self.cover_preview.setStyleSheet("border:1px dashed #aaa; border-radius:6px; color:#888;")
        btn_set_cover = QPushButton("选择封面图片…")
        btn_clear_cover = QPushButton("清除封面")
        btn_set_cover.clicked.connect(self._pick_cover)
        btn_clear_cover.clicked.connect(self._clear_cover)
        row = QHBoxLayout()
        row.addWidget(btn_set_cover)
        row.addWidget(btn_clear_cover)
        cover_lay.addWidget(self.cover_preview)
        cover_lay.addLayout(row)
        self.tabs.addTab(cover, "封面")

        # 底部操作
        self.chk_clear_empty = QCheckBox("清空未填写的字段（默认保留原值）")
        btn_save = QPushButton("保存修改")
        btn_infer = QPushButton("从文件名推断")
        btn_scrape = QPushButton("自动刮削…")
        btn_save.setStyleSheet("font-weight:bold;")
        btn_save.clicked.connect(lambda: self.save_requested.emit(self.get_fields()))
        btn_infer.clicked.connect(self.infer_requested)
        btn_scrape.clicked.connect(self.scrape_requested)

        bottom = QHBoxLayout()
        bottom.addWidget(self.chk_clear_empty)
        bottom.addStretch(1)
        bottom.addWidget(btn_infer)
        bottom.addWidget(btn_scrape)
        bottom.addWidget(btn_save)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.addWidget(self.tabs)
        lay.addLayout(bottom)

    # ---------------- 数据填充 ----------------
    def set_fields(self, fields: Dict[str, Any], read_only: bool = False) -> None:
        """用字段字典填充面板。多选时相同字段显示公共值。"""
        self._fields = dict(fields)
        for k, line in self.ed.items():
            line.setText(_to_text(fields.get(k)))
        for k, line in self.num_ed.items():
            line.setText(str(fields.get(k) or ""))
        self.lyrics_edit.setPlainText(str(fields.get("lyrics") or ""))
        for k, line in self.long_ed.items():
            line.setText(str(fields.get(k) or ""))
        dur = float(fields.get("duration") or 0)
        self.lbl_duration.setText(f"{int(dur // 60)}:{int(dur % 60):02d}" if dur else "—")
        cover = fields.get("cover") or b""
        self._cover_bytes = cover if isinstance(cover, bytes) else b""
        self._cover_mime = str(fields.get("cover_mime") or "")
        self._show_cover()
        self.set_read_only(read_only)

    def set_read_only(self, ro: bool) -> None:
        for w in list(self.ed.values()) + list(self.num_ed.values()) + list(self.long_ed.values()):
            w.setReadOnly(ro)
        self.lyrics_edit.setReadOnly(ro)

    def get_fields(self) -> Dict[str, Any]:
        """收集面板当前值（保留 cover 二进制）。"""
        f = empty_fields()
        for k, line in self.ed.items():
            f[k] = line.text().strip()
        f["artists"] = _split_artists(self.ed["artists"].text())
        f["composer"] = _split_artists(self.ed["composer"].text())
        f["arranger"] = _split_artists(self.ed["arranger"].text())
        f["lyricist"] = _split_artists(self.ed["lyricist"].text())
        for k, line in self.num_ed.items():
            f[k] = line.text().strip()
        f["lyrics"] = self.lyrics_edit.toPlainText()
        for k, line in self.long_ed.items():
            f[k] = line.text().strip()
        f["cover"] = self._cover_bytes
        f["cover_mime"] = self._cover_mime
        return f

    # ---------------- 封面 ----------------
    def _show_cover(self):
        if self._cover_bytes:
            pm = QPixmap()
            if pm.loadFromData(self._cover_bytes):
                self.cover_preview.setPixmap(pm.scaled(
                    280, 220, Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation))
                self.cover_preview.setText("")
                return
        self.cover_preview.setPixmap(QPixmap())
        self.cover_preview.setText("无封面")

    def _pick_cover(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择封面图片", "", "图片 (*.jpg *.jpeg *.png *.webp *.bmp)")
        if not path:
            return
        with open(path, "rb") as f:
            data = f.read()
        if data[:3] == b"\xff\xd8\xff":
            mime = "image/jpeg"
        elif data[:8] == b"\x89PNG\r\n\x1a\n":
            mime = "image/png"
        else:
            # 尝试用 Pillow 转成 JPEG/PNG
            try:
                from PIL import Image
                import io
                img = Image.open(io.BytesIO(data))
                buf = io.BytesIO()
                img.convert("RGB").save(buf, "JPEG", quality=92)
                data = buf.getvalue()
                mime = "image/jpeg"
            except Exception:
                mime = "image/jpeg"
        self._cover_bytes = data
        self._cover_mime = mime
        self._show_cover()

    def _clear_cover(self):
        self._cover_bytes = b""
        self._cover_mime = ""
        self._show_cover()


def _to_text(v) -> str:
    if isinstance(v, list):
        return " / ".join(str(x) for x in v)
    return str(v or "")


def _split_artists(text: str):
    return [x.strip() for x in text.replace("；", ";").split("/") if x.strip()]
