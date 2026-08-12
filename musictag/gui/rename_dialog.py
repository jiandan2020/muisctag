# -*- coding: utf-8 -*-
"""重命名/整理对话框：模板输入 + 实时预览。"""
from __future__ import annotations
from typing import Dict, List, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QDialog, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QMessageBox,
                               QPushButton, QVBoxLayout)

from ..core.renamer import PLACEHOLDERS, plan_rename


class RenameDialog(QDialog):
    """重命名对话框。"""

    def __init__(self, paths: List[str], fields_map: Dict[str, dict],
                 root: str = "", parent=None):
        super().__init__(parent)
        self.paths = paths
        self.fields_map = fields_map
        self.root = root
        self.plans: List[Tuple[str, str, bool]] = []
        self._build_ui()
        self.setWindowTitle("重命名 / 整理目录")
        self.resize(720, 480)

    def _build_ui(self):
        self.ed_template = QLineEdit("{artist}/{album}/{track2} {title}.{ext}")
        self.ed_template.textChanged.connect(self._refresh)
        self.chk_root = QCheckBox("在所选根目录下创建目录结构")
        if self.root:
            self.chk_root.setChecked(True)
            self.chk_root.setEnabled(True)
        else:
            self.chk_root.setText("（未选择根目录，将在文件所在目录内创建）")
        self.chk_root.toggled.connect(self._refresh)

        self.preview = QListWidget()
        self.preview.setAlternatingRowColors(True)

        btn_ok = QPushButton("执行重命名")
        btn_ok.setStyleSheet("font-weight:bold;")
        btn_ok.clicked.connect(self._apply)
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)

        hints = QLabel("可用占位符: " + " ".join(f"{{{k}}}" for k in
                        ("artist", "artists", "album", "title", "track", "track2",
                         "tracktotal", "disc", "disc2", "year", "genre", "ext")))
        hints.setWordWrap(True)
        hints.setStyleSheet("color:#888;")

        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("命名模板:"))
        lay.addWidget(self.ed_template)
        lay.addWidget(self.chk_root)
        lay.addWidget(hints)
        lay.addWidget(QLabel("预览:"))
        lay.addWidget(self.preview, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(btn_ok)
        row.addWidget(btn_cancel)
        lay.addLayout(row)
        self._refresh()

    def _refresh(self):
        self.preview.clear()
        self.plans = []
        root = self.root if self.chk_root.isChecked() else ""
        for p in self.paths:
            fields = self.fields_map.get(p, {})
            try:
                src, dst, changed = plan_rename(p, fields, self.ed_template.text(), root=root)
            except Exception as exc:
                self.preview.addItem(f"⚠ {p}  ->  {exc}")
                continue
            self.plans.append((src, dst, changed))
            if changed:
                self.preview.addItem(f"{src}\n  ->  {dst}")
            else:
                self.preview.addItem(f"＝ {src}（无变化）")

    def _apply(self):
        changed = [pl for pl in self.plans if pl[2]]
        if not changed:
            self.accept()
            return
        self.accept()
