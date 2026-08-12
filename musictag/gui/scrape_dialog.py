# -*- coding: utf-8 -*-
"""刮削对话框：搜索多平台、选择结果、预览歌词/封面、应用到文件。"""
from __future__ import annotations
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QMessageBox,
                               QPushButton, QSplitter, QTableWidget,
                               QTableWidgetItem, QTextEdit, QVBoxLayout,
                               QWidget)

from ..scrapers.base import LyricsResult, Song
from ..scrapers.manager import ScrapeManager, PLUGIN_REGISTRY

_PLATFORM_NAMES = {"netease": "网易云", "qq": "QQ", "kugou": "酷狗",
                   "lrclib": "Lrclib", "apple": "Apple", "musixmatch": "Musixmatch"}


class _SearchThread(QThread):
    """后台搜索线程。"""
    results = Signal(list)
    failed = Signal(str)
    finished_ok = Signal()

    def __init__(self, manager: ScrapeManager, keyword: str, limit: int, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.keyword = keyword
        self.limit = limit

    def run(self):
        try:
            items = self.manager.search_all(self.keyword, limit=self.limit)
            self.results.emit(items)
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            self.finished_ok.emit()


class _FetchThread(QThread):
    """后台获取歌词/封面线程。"""
    lyric = Signal(object)
    cover = Signal(bytes)
    failed = Signal(str)
    finished_ok = Signal()

    def __init__(self, manager: ScrapeManager, track: Song, with_lyric: bool,
                 with_cover: bool, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.track = track
        self.with_lyric = with_lyric
        self.with_cover = with_cover

    def run(self):
        try:
            if self.with_lyric:
                self.lyric.emit(self.manager.get_lyrics(self.track))
            if self.with_cover:
                self.cover.emit(self.manager.get_cover(self.track))
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            self.finished_ok.emit()


class ScrapeDialog(QDialog):
    """刮削对话框。apply 时通过 signals 返回所选结果。"""

    applied = Signal(object)          # Song
    lyrics_ready = Signal(object)     # LyricsResult
    cover_ready = Signal(bytes)

    def __init__(self, keyword: str, config: Dict, parent=None):
        super().__init__(parent)
        self.config = config
        self.manager = ScrapeManager(config)
        self.track: Optional[Song] = None
        self._lyric: Optional[LyricsResult] = None
        self._cover = b""
        self._build_ui(keyword)
        self.setWindowTitle("在线刮削")
        self.resize(860, 560)

    def _build_ui(self, keyword: str):
        # 搜索行
        self.ed_keyword = QLineEdit(keyword)
        self.spin_limit = QComboBox()
        for n in (5, 10, 20):
            self.spin_limit.addItem(str(n), n)
        self.spin_limit.setCurrentIndex(1)
        btn_search = QPushButton("搜索")
        btn_search.clicked.connect(self._search)

        row = QHBoxLayout()
        row.addWidget(QLabel("关键词:"))
        row.addWidget(self.ed_keyword, 1)
        row.addWidget(QLabel("每平台:"))
        row.addWidget(self.spin_limit)
        row.addWidget(btn_search)

        # 结果表
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["平台", "标题", "艺术家", "专辑", "时长"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._on_select)

        # 预览区
        self.preview_lyric = QTextEdit()
        self.preview_lyric.setPlaceholderText("歌词预览…")
        self.preview_cover = QLabel("封面预览")
        self.preview_cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_cover.setMinimumSize(200, 200)
        self.preview_cover.setStyleSheet("border:1px dashed #aaa; color:#888;")

        split = QSplitter(Qt.Orientation.Vertical)
        split.addWidget(self.table)
        preview = QWidget()
        pv = QHBoxLayout(preview)
        pv.addWidget(self.preview_lyric, 3)
        pv.addWidget(self.preview_cover, 2)
        split.addWidget(preview)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)

        # 选项 + 按钮
        self.chk_lyric = QCheckBox("获取歌词")
        self.chk_lyric.setChecked(True)
        self.chk_cover = QCheckBox("获取封面")
        self.chk_cover.setChecked(True)
        btn_fetch = QPushButton("获取歌词/封面")
        btn_fetch.clicked.connect(self._fetch)
        btn_apply = QPushButton("应用到选中文件")
        btn_apply.setStyleSheet("font-weight:bold;")
        btn_apply.clicked.connect(self._apply)
        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(self.reject)

        opt = QHBoxLayout()
        opt.addWidget(self.chk_lyric)
        opt.addWidget(self.chk_cover)
        opt.addWidget(btn_fetch)
        opt.addStretch(1)
        opt.addWidget(btn_apply)
        opt.addWidget(btn_close)

        lay = QVBoxLayout(self)
        lay.addLayout(row)
        lay.addWidget(split, 1)
        lay.addLayout(opt)

    # ---------------- 动作 ----------------
    def _search(self):
        self.table.setRowCount(0)
        kw = self.ed_keyword.text().strip()
        if not kw:
            return
        limit = self.spin_limit.currentData()
        self._thread = _SearchThread(self.manager, kw, limit, self)
        self._thread.results.connect(self._show_results)
        self._thread.failed.connect(lambda e: QMessageBox.warning(self, "搜索失败", e))
        self._thread.finished_ok.connect(self._thread.deleteLater)
        self._thread.start()

    def _show_results(self, items: List[Song]):
        self._items = items
        self.table.setRowCount(len(items))
        for r, it in enumerate(items):
            self.table.setItem(r, 0, QTableWidgetItem(_PLATFORM_NAMES.get(it.source, it.source)))
            self.table.setItem(r, 1, QTableWidgetItem(it.title))
            self.table.setItem(r, 2, QTableWidgetItem(it.artist_text))
            self.table.setItem(r, 3, QTableWidgetItem(it.album))
            dur = it.duration
            self.table.setItem(r, 4, QTableWidgetItem(
                f"{int(dur // 60)}:{int(dur % 60):02d}" if dur else ""))

    def _on_select(self):
        rows = self.table.selectionModel().selectedRows()
        if rows and hasattr(self, "_items"):
            self.track = self._items[rows[0].row()]
            self.preview_lyric.clear()
            self.preview_cover.setText("封面预览")
            self.preview_cover.setPixmap(QPixmap())
            self._lyric = None
            self._cover = b""

    def _fetch(self):
        if self.track is None:
            QMessageBox.information(self, "提示", "请先在结果列表中选择一首歌曲")
            return
        self._fetch_thread = _FetchThread(self.manager, self.track,
                                          self.chk_lyric.isChecked(),
                                          self.chk_cover.isChecked(), self)
        self._fetch_thread.lyric.connect(self._show_lyric)
        self._fetch_thread.cover.connect(self._show_cover)
        self._fetch_thread.failed.connect(lambda e: QMessageBox.warning(self, "获取失败", e))
        self._fetch_thread.finished_ok.connect(self._fetch_thread.deleteLater)
        self._fetch_thread.start()

    def _show_lyric(self, lyric: Optional[LyricsResult]):
        self._lyric = lyric
        if lyric:
            text = lyric.synced or lyric.plain
            if lyric.translation:
                text += "\n\n--- 译文 ---\n" + lyric.translation
            self.preview_lyric.setPlainText(text)
        else:
            self.preview_lyric.setPlainText("（该平台无歌词或获取失败）")

    def _show_cover(self, data: Optional[bytes]):
        if data:
            self._cover = data
            pm = QPixmap()
            if pm.loadFromData(data):
                self.preview_cover.setPixmap(pm.scaled(
                    200, 200, Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation))
        else:
            self.preview_cover.setText("（无封面）")

    def _apply(self):
        """把当前选中结果发回主窗口（歌词/封面一并携带）。"""
        if self.track is None:
            QMessageBox.information(self, "提示", "请先选择搜索结果")
            return
        self.applied.emit(self.track)
        if self._lyric:
            self.lyrics_ready.emit(self._lyric)
        if self._cover:
            self.cover_ready.emit(self._cover)
        self.accept()
