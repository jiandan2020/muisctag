# -*- coding: utf-8 -*-
"""设置对话框：网络 / 刮削 / 翻译 / 通用。"""
from __future__ import annotations
from typing import Dict

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDoubleSpinBox,
                               QFormLayout, QGroupBox, QLineEdit, QSpinBox,
                               QTabWidget, QVBoxLayout, QPushButton,
                               QHBoxLayout, QWidget)


class SettingsDialog(QDialog):
    """应用设置。"""

    def __init__(self, config: Dict, parent=None):
        super().__init__(parent)
        self.config = config
        self._build_ui()
        self.setWindowTitle("设置")
        self.resize(520, 460)

    def _build_ui(self):
        net = self.config.get("network", {})
        scr = self.config.get("scrape", {})
        tr = self.config.get("translate", {})
        gen = self.config.get("general", {})

        tabs = QTabWidget()

        # ---- 网络 ----
        net_w = QWidget()
        f = QFormLayout(net_w)
        self.ed_proxy = QLineEdit(net.get("proxy", ""))
        self.ed_timeout = QDoubleSpinBox()
        self.ed_timeout.setRange(3, 120)
        self.ed_timeout.setValue(float(net.get("timeout", 15)))
        self.ed_delay = QDoubleSpinBox()
        self.ed_delay.setRange(0, 10)
        self.ed_delay.setSingleStep(0.1)
        self.ed_delay.setValue(float(net.get("delay", 0.4)))
        self.ed_retries = QSpinBox()
        self.ed_retries.setRange(0, 10)
        self.ed_retries.setValue(int(net.get("retries", 2)))
        self.chk_ua = QCheckBox("轮换 User-Agent")
        self.chk_ua.setChecked(bool(net.get("rotate_ua", True)))
        f.addRow("代理（http://host:port）", self.ed_proxy)
        f.addRow("超时（秒）", self.ed_timeout)
        f.addRow("请求间隔（秒）", self.ed_delay)
        f.addRow("重试次数", self.ed_retries)
        f.addRow("", self.chk_ua)
        tabs.addTab(net_w, "网络")

        # ---- 刮削 ----
        scr_w = QWidget()
        f = QFormLayout(scr_w)
        self.cmb_id3 = QComboBox()
        self.cmb_id3.addItems(["v2.3", "v2.4", "v1"])
        idx = self.cmb_id3.findText(scr.get("id3_version", "v2.3"))
        self.cmb_id3.setCurrentIndex(max(0, idx))
        self.chk_cover = QCheckBox("刮削时写入封面")
        self.chk_cover.setChecked(bool(scr.get("save_cover", True)))
        self.chk_lyric = QCheckBox("刮削时写入歌词")
        self.chk_lyric.setChecked(bool(scr.get("save_lyrics", True)))
        self.cmb_pref = QComboBox()
        self.cmb_pref.addItem("优先带时间轴", "synced")
        self.cmb_pref.addItem("优先纯文本", "plain")
        idx = self.cmb_pref.findData(scr.get("lyric_pref", "synced"))
        self.cmb_pref.setCurrentIndex(max(0, idx))
        self.ed_size = QSpinBox()
        self.ed_size.setRange(0, 2000)
        self.ed_size.setValue(int(scr.get("cover_size", 300)))
        f.addRow("MP3 ID3 版本", self.cmb_id3)
        f.addRow("", self.chk_cover)
        f.addRow("", self.chk_lyric)
        f.addRow("歌词偏好", self.cmb_pref)
        f.addRow("封面尺寸(px, 0=原图)", self.ed_size)
        tabs.addTab(scr_w, "刮削")

        # ---- 翻译 ----
        tr_w = QWidget()
        f = QFormLayout(tr_w)
        self.cmb_engine = QComboBox()
        self.cmb_engine.addItems(["google", "bing", "openai", "mymemory"])
        idx = self.cmb_engine.findText(tr.get("engine", "google"))
        self.cmb_engine.setCurrentIndex(max(0, idx))
        self.ed_oa_base = QLineEdit(tr.get("openai_base_url", "https://api.openai.com/v1"))
        self.ed_oa_key = QLineEdit(tr.get("openai_api_key", ""))
        self.ed_oa_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.ed_oa_model = QLineEdit(tr.get("openai_model", "gpt-4o-mini"))
        self.ed_mx_key = QLineEdit(tr.get("musixmatch_api_key", ""))
        self.ed_mx_key.setEchoMode(QLineEdit.EchoMode.Password)
        f.addRow("翻译引擎", self.cmb_engine)
        f.addRow("OpenAI Base URL", self.ed_oa_base)
        f.addRow("OpenAI API Key", self.ed_oa_key)
        f.addRow("OpenAI 模型", self.ed_oa_model)
        f.addRow("Musixmatch API Key", self.ed_mx_key)
        tabs.addTab(tr_w, "翻译")

        # ---- 通用 ----
        gen_w = QWidget()
        f = QFormLayout(gen_w)
        self.ed_threads = QSpinBox()
        self.ed_threads.setRange(1, 16)
        self.ed_threads.setValue(int(gen.get("threads", 4)))
        self.chk_backup = QCheckBox("修改前自动备份原始标签")
        self.chk_backup.setChecked(bool(gen.get("backup", True)))
        f.addRow("批处理线程数", self.ed_threads)
        f.addRow("", self.chk_backup)
        tabs.addTab(gen_w, "通用")

        btn_save = QPushButton("保存")
        btn_save.setStyleSheet("font-weight:bold;")
        btn_save.clicked.connect(self._save)
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(btn_save)
        row.addWidget(btn_cancel)

        lay = QVBoxLayout(self)
        lay.addWidget(tabs, 1)
        lay.addLayout(row)

    def _save(self):
        self.config["network"]["proxy"] = self.ed_proxy.text().strip()
        self.config["network"]["timeout"] = self.ed_timeout.value()
        self.config["network"]["delay"] = self.ed_delay.value()
        self.config["network"]["retries"] = self.ed_retries.value()
        self.config["network"]["rotate_ua"] = self.chk_ua.isChecked()

        self.config["scrape"]["id3_version"] = self.cmb_id3.currentText()
        self.config["scrape"]["save_cover"] = self.chk_cover.isChecked()
        self.config["scrape"]["save_lyrics"] = self.chk_lyric.isChecked()
        self.config["scrape"]["lyric_pref"] = self.cmb_pref.currentData()
        self.config["scrape"]["cover_size"] = self.ed_size.value()

        self.config["translate"]["engine"] = self.cmb_engine.currentText()
        self.config["translate"]["openai_base_url"] = self.ed_oa_base.text().strip()
        self.config["translate"]["openai_api_key"] = self.ed_oa_key.text().strip()
        self.config["translate"]["openai_model"] = self.ed_oa_model.text().strip()
        self.config["translate"]["musixmatch_api_key"] = self.ed_mx_key.text().strip()

        self.config["general"]["threads"] = self.ed_threads.value()
        self.config["general"]["backup"] = self.chk_backup.isChecked()
        self.accept()
