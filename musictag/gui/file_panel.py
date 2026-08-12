# -*- coding: utf-8 -*-
"""左侧文件列表：拖拽添加、多选、勾选、右键菜单。"""
from __future__ import annotations
import os
from typing import List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QListWidget,
                               QListWidgetItem, QMenu, QPushButton,
                               QVBoxLayout, QWidget)

from ..core.metadata import SUPPORTED_EXTENSIONS, is_supported


def _fmt_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024
    return f"{n:.1f} GB"


class FileListPanel(QWidget):
    """文件列表面板。"""

    selection_changed = Signal()          # 多选/单选变化
    files_changed = Signal()              # 文件集合变化

    def __init__(self, parent=None):
        super().__init__(parent)
        self._paths: List[str] = []
        self._build_ui()

    # ---------------- UI ----------------
    def _build_ui(self):
        self.list = QListWidget()
        self.list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.list.setAcceptDrops(True)
        self.list.setDragDropMode(QListWidget.DragDropMode.DropOnly)
        self.list.setAlternatingRowColors(True)
        self.list.itemSelectionChanged.connect(self.selection_changed)
        self.list.itemChanged.connect(lambda _: None)

        btn_add = QPushButton("添加文件")
        btn_dir = QPushButton("添加文件夹")
        btn_remove = QPushButton("移除选中")
        btn_clear = QPushButton("清空")
        btn_add.clicked.connect(self.add_files_dialog)
        btn_dir.clicked.connect(self.add_folder_dialog)
        btn_remove.clicked.connect(self.remove_selected)
        btn_clear.clicked.connect(self.clear_all)

        btns = QHBoxLayout()
        for b in (btn_add, btn_dir, btn_remove, btn_clear):
            btns.addWidget(b)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.addLayout(btns)
        lay.addWidget(self.list)

    # ---------------- 拖拽 ----------------
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        paths = []
        for url in event.mimeData().urls():
            p = url.toLocalFile()
            if p and os.path.exists(p):
                paths.append(p)
        self.add_paths(paths)

    # ---------------- 文件操作 ----------------
    def add_paths(self, paths: List[str]) -> int:
        """添加文件/目录（目录递归扫描），返回新增数量。"""
        from ..core.metadata import find_audio_files
        added = 0
        for p in paths:
            if os.path.isdir(p):
                for f in find_audio_files(p):
                    if f not in self._paths:
                        self._append(f)
                        added += 1
            elif os.path.isfile(p) and is_supported(p) and p not in self._paths:
                self._append(p)
                added += 1
        if added:
            self.files_changed.emit()
        return added

    def _append(self, path: str):
        self._paths.append(path)
        size = os.path.getsize(path) if os.path.isfile(path) else 0
        ext = os.path.splitext(path)[1].lstrip(".").upper()
        name = os.path.basename(path)
        item = QListWidgetItem(f"{name}   [{ext} · {_fmt_size(size)}]")
        item.setData(Qt.ItemDataRole.UserRole, path)
        item.setToolTip(path)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(Qt.CheckState.Checked)
        self.list.addItem(item)

    def add_files_dialog(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择音频文件", "",
            "音频文件 (*.mp3 *.flac *.ape *.wav *.aiff *.aif *.wv *.tta *.m4a *.mp4 *.ogg *.mpc *.opus *.wma *.dsf);;所有文件 (*.*)")
        self.add_paths(list(files))

    def add_folder_dialog(self):
        folder = QFileDialog.getExistingDirectory(self, "选择文件夹")
        if folder:
            self.add_paths([folder])

    def remove_selected(self):
        rows = sorted({self.list.row(i) for i in self.list.selectedItems()}, reverse=True)
        for r in rows:
            it = self.list.takeItem(r)
            self._paths.pop(r)
        self.files_changed.emit()

    def clear_all(self):
        self.list.clear()
        self._paths.clear()
        self.files_changed.emit()

    # ---------------- 查询 ----------------
    def paths(self) -> List[str]:
        return list(self._paths)

    def selected_paths(self) -> List[str]:
        return [self.list.item(self.list.row(i)).data(Qt.ItemDataRole.UserRole)
                for i in self.list.selectedItems()]

    def checked_paths(self) -> List[str]:
        out = []
        for i in range(self.list.count()):
            it = self.list.item(i)
            if it.checkState() == Qt.CheckState.Checked:
                out.append(it.data(Qt.ItemDataRole.UserRole))
        return out

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        act_reveal = QAction("在资源管理器中显示", self)
        act_copy = QAction("复制路径", self)
        act_remove = QAction("移除选中", self)
        act_clear = QAction("清空列表", self)
        act_reveal.triggered.connect(self._reveal_selected)
        act_copy.triggered.connect(self._copy_paths)
        act_remove.triggered.connect(self.remove_selected)
        act_clear.triggered.connect(self.clear_all)
        menu.addAction(act_reveal)
        menu.addAction(act_copy)
        menu.addSeparator()
        menu.addAction(act_remove)
        menu.addAction(act_clear)
        menu.exec(event.globalPos())

    def _reveal_selected(self):
        paths = self.selected_paths()
        if paths:
            os.startfile(os.path.dirname(paths[0]))  # noqa: S606

    def _copy_paths(self):
        from PySide6.QtWidgets import QApplication
        paths = "\n".join(self.selected_paths())
        if paths:
            QApplication.clipboard().setText(paths)
