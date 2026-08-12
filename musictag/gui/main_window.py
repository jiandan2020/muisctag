# -*- coding: utf-8 -*-
"""主窗口：菜单栏、工具栏、三栏布局、后台任务调度。"""
from __future__ import annotations
import os
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog,
                               QDockWidget, QFileDialog, QFormLayout,
                               QInputDialog, QLabel, QMainWindow, QMessageBox,
                               QPlainTextEdit, QProgressBar, QSplitter,
                               QVBoxLayout, QWidget)

from .. import APP_NAME, __version__
from ..core import metadata as md
from ..core.filename_parser import infer_from_path
from ..utils.config import load_config, save_config
from .file_panel import FileListPanel
from .lyrics_panel import LyricsPanel
from .metadata_panel import MetadataPanel
from .rename_dialog import RenameDialog
from .scrape_dialog import ScrapeDialog
from .settings_dialog import SettingsDialog
from .workers import (BatchWriteTask, CleanTagsTask, ConvertTagsTask,
                      DedupTask, LoadFilesTask, RenameTask, ReportTask,
                      ScrapeBatchTask, TaskThread, TranslateTask)

#: 单个文件标签读取上限（超过则提示）
_EDIT_LIMIT = 60


class MainWindow(QMainWindow):
    """MusicTag 主窗口。"""

    def __init__(self):
        super().__init__()
        self.config = load_config()
        self.fields_cache: Dict[str, Dict[str, Any]] = {}   # path -> 读取到的字段
        self._task: Optional[TaskThread] = None
        self._build_ui()
        self._build_menus()
        self._connect()
        self.setWindowTitle(f"{APP_NAME} v{__version__} — 全格式音频标签批量编辑与刮削工具")
        self.resize(1360, 800)

    # ---------------- UI ----------------
    def _build_ui(self):
        self.file_panel = FileListPanel()
        self.meta_panel = MetadataPanel()
        self.lyrics_panel = LyricsPanel()
        self.lyrics_panel.set_engines(["google", "bing", "openai", "mymemory"])

        split = QSplitter(Qt.Orientation.Horizontal)
        split.addWidget(self.file_panel)
        split.addWidget(self.meta_panel)
        split.addWidget(self.lyrics_panel)
        split.setStretchFactor(0, 2)
        split.setStretchFactor(1, 3)
        split.setStretchFactor(2, 2)
        split.setSizes([380, 560, 420])
        self.setCentralWidget(split)

        # 日志停靠窗
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(2000)
        self.log_dock = QDockWidget("日志", self)
        self.log_dock.setWidget(self.log_view)
        self.log_dock.hide()
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.log_dock)

        # 状态栏
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setMaximumWidth(240)
        self.progress.hide()
        self.statusBar().addPermanentWidget(self.progress)
        self.statusBar().showMessage("就绪")

    def _build_menus(self):
        mb = self.menuBar()

        # 文件
        m_file = mb.addMenu("文件(&F)")
        self._add(m_file, "添加音频文件…", self.file_panel.add_files_dialog, "Ctrl+O")
        self._add(m_file, "添加文件夹…", self.file_panel.add_folder_dialog, "Ctrl+Shift+O")
        m_file.addSeparator()
        self._add(m_file, "退出", self.close, "Ctrl+Q")

        # 编辑
        m_edit = mb.addMenu("编辑(&E)")
        self._add(m_edit, "从文件名推断标签（填充空字段）", self._infer_tags, "Ctrl+I")
        self._add(m_edit, "标签清理与标准化…", self._clean_tags, "Ctrl+L")
        self._add(m_edit, "ID3 版本转换…", self._convert_id3)
        self._add(m_edit, "重命名 / 整理目录…", self._rename_files, "Ctrl+R")

        # 工具
        m_tool = mb.addMenu("工具(&T)")
        self._add(m_tool, "刮削选中歌曲…", self._scrape_selected, "Ctrl+S")
        self._add(m_tool, "批量自动刮削（歌词/封面/补全）…", self._scrape_batch, "Ctrl+B")
        self._add(m_tool, "在线获取歌词…", self._fetch_lyrics, "Ctrl+G")
        m_tool.addSeparator()
        self._add(m_tool, "检测重复文件…", self._dedup_files)
        self._add(m_tool, "缺失标签报告…", self._missing_report)

        # 视图
        m_view = mb.addMenu("视图(&V)")
        act_log = QAction("显示/隐藏日志", self)
        act_log.setCheckable(True)
        act_log.setChecked(False)
        act_log.toggled.connect(lambda on: self.log_dock.setVisible(on))
        m_view.addAction(act_log)

        # 设置 / 帮助
        m_set = mb.addMenu("设置(&S)")
        self._add(m_set, "设置…", self._open_settings, "Ctrl+,")
        m_help = mb.addMenu("帮助(&H)")
        self._add(m_help, "关于", self._about)

        # 工具栏
        tb = self.addToolBar("主工具栏")
        tb.setMovable(False)
        for label, slot in (("添加文件", self.file_panel.add_files_dialog),
                            ("添加文件夹", self.file_panel.add_folder_dialog),
                            ("保存修改", self._save_tags),
                            ("自动刮削", self._scrape_selected),
                            ("在线歌词", self._fetch_lyrics),
                            ("设置", self._open_settings)):
            act = QAction(label, self)
            act.triggered.connect(slot)
            tb.addAction(act)

    @staticmethod
    def _add(menu, text, slot, shortcut=""):
        act = QAction(text, menu)
        if shortcut:
            act.setShortcut(shortcut)
        act.triggered.connect(slot)
        menu.addAction(act)
        return act

    def _connect(self):
        self.file_panel.selection_changed.connect(self._on_selection)
        self.file_panel.files_changed.connect(self._on_files_changed)
        self.meta_panel.save_requested.connect(self._save_tags)
        self.meta_panel.infer_requested.connect(self._infer_tags)
        self.meta_panel.scrape_requested.connect(self._scrape_selected)
        self.lyrics_panel.save_requested.connect(self._save_lyrics_to_tag)
        self.lyrics_panel.fetch_requested.connect(self._fetch_lyrics)
        self.lyrics_panel.translate_requested.connect(self._translate_lyrics)
        self.lyrics_panel.status_message.connect(lambda s: self.statusBar().showMessage(s, 5000))

    # ---------------- 日志 ----------------
    def log(self, text: str):
        self.log_view.appendPlainText(text)
        self.statusBar().showMessage(text, 5000)

    def _run_task(self, task: TaskThread, busy_text: str = "处理中…"):
        """启动后台任务并接管其信号。"""
        if self._task is not None and self._task.isRunning():
            QMessageBox.information(self, "提示", "已有任务正在运行，请稍候")
            return
        self._task = task
        self.progress.setValue(0)
        self.progress.show()
        self.statusBar().showMessage(busy_text)
        task.progress.connect(lambda v: self.progress.setValue(v))
        task.message.connect(self.log)
        task.done.connect(self._on_task_done)
        task.start()

    def _on_task_done(self, ok: bool, msg: str):
        task = self._task
        self.progress.hide()
        self.statusBar().showMessage(msg, 8000)
        self.log(msg)
        self._task = None
        # 结束后刷新
        if isinstance(task, RenameTask):
            new_paths = [dst for _, dst, ch in task.plans if ch]
            self.file_panel.clear_all()
            self.file_panel.add_paths(new_paths)
            self._on_files_changed()
        else:
            self._on_files_changed()
            if isinstance(task, (BatchWriteTask, CleanTagsTask)):
                # 重新加载选中文件的最新标签
                self._on_selection()

    # ---------------- 文件选择 ----------------
    def _active_paths(self) -> List[str]:
        sel = self.file_panel.selected_paths()
        if sel:
            return sel
        return self.file_panel.checked_paths()

    def _on_files_changed(self):
        self.fields_cache.clear()
        self.meta_panel.set_fields(md.empty_fields(), read_only=True)
        self.statusBar().showMessage(f"共 {len(self.file_panel.paths())} 个文件", 5000)

    def _on_selection(self):
        paths = self.file_panel.selected_paths()
        if not paths:
            self.meta_panel.set_fields(md.empty_fields(), read_only=True)
            return
        if len(paths) > _EDIT_LIMIT:
            self.meta_panel.set_fields(md.empty_fields(), read_only=True)
            self.statusBar().showMessage(f"选中文件过多（{len(paths)}），请分批编辑", 8000)
            return
        try:
            fields = self._load_fields(paths[0])
            if not fields:
                return
            common = dict(fields)
            for p in paths[1:]:
                f = self._load_fields(p)
                if f is None:
                    continue
                for k in list(common.keys()):
                    if common[k] != f.get(k):
                        common[k] = "" if not isinstance(common[k], list) else []
            self.meta_panel.set_fields(common, read_only=False)
            if len(paths) == 1:
                self.lyrics_panel.set_text(str(fields.get("lyrics") or ""))
        except Exception as exc:
            self.log(f"读取标签失败: {exc}")

    def _load_fields(self, path: str) -> Optional[Dict[str, Any]]:
        if path not in self.fields_cache:
            try:
                self.fields_cache[path] = md.AudioFile(path).read()
            except Exception as exc:
                self.log(f"读取失败 {os.path.basename(path)}: {exc}")
                return None
        return self.fields_cache.get(path)

    # ---------------- 保存 ----------------
    def _save_tags(self, _fields: Optional[Dict[str, Any]] = None):
        paths = self.file_panel.selected_paths()
        if not paths:
            QMessageBox.information(self, "提示", "请先在左侧选择文件")
            return
        panel_fields = self.meta_panel.get_fields()
        clear_empty = self.meta_panel.chk_clear_empty.isChecked()
        fields_list = []
        for p in paths:
            cur = self._load_fields(p) or md.empty_fields()
            merged = dict(cur)
            for k, v in panel_fields.items():
                if k in ("cover", "cover_mime"):
                    merged[k] = v
                    continue
                if clear_empty:
                    merged[k] = v
                elif isinstance(v, list):
                    if v:
                        merged[k] = v
                elif str(v or "").strip():
                    merged[k] = v
            fields_list.append(merged)
        version = self.config.get("scrape", {}).get("id3_version", "v2.3")
        backup = self.config.get("general", {}).get("backup", True)
        self._run_task(BatchWriteTask(paths, fields_list, id3_version=version, backup=backup),
                       "正在保存标签…")

    def _save_lyrics_to_tag(self, text: str):
        paths = self.file_panel.selected_paths()
        if not paths:
            QMessageBox.information(self, "提示", "请先选择文件")
            return
        fields_list = []
        for p in paths:
            cur = self._load_fields(p) or md.empty_fields()
            cur["lyrics"] = text
            fields_list.append(cur)
        version = self.config.get("scrape", {}).get("id3_version", "v2.3")
        backup = self.config.get("general", {}).get("backup", True)
        self._run_task(BatchWriteTask(paths, fields_list, id3_version=version, backup=backup),
                       "正在保存歌词…")

    # ---------------- 推断 ----------------
    def _infer_tags(self):
        paths = self._active_paths()
        if not paths:
            QMessageBox.information(self, "提示", "请先选择文件")
            return
        fields_list = []
        for p in paths:
            cur = self._load_fields(p) or md.empty_fields()
            inferred = infer_from_path(p)
            for k, v in inferred.items():
                if k == "artists":
                    if not cur.get("artists") and v:
                        cur["artists"] = v
                elif not str(cur.get(k) or "").strip() and v:
                    cur[k] = v
            fields_list.append(cur)
        version = self.config.get("scrape", {}).get("id3_version", "v2.3")
        backup = self.config.get("general", {}).get("backup", True)
        self._run_task(BatchWriteTask(paths, fields_list, id3_version=version, backup=backup),
                       "正在写入推断标签…")

    # ---------------- 刮削 ----------------
    def _scrape_selected(self):
        paths = self.file_panel.selected_paths()
        if not paths:
            QMessageBox.information(self, "提示", "请先选择文件")
            return
        fields = self._load_fields(paths[0]) or md.empty_fields()
        title = str(fields.get("title") or "")
        artists = ", ".join(fields.get("artists") or [])
        kw = f"{title} {artists}".strip() or os.path.splitext(os.path.basename(paths[0]))[0]
        dlg = ScrapeDialog(kw, self.config, self)
        dlg.applied.connect(lambda track: self._apply_track(track, paths))
        dlg.lyrics_ready.connect(lambda lyric: self._apply_lyrics(lyric, paths))
        dlg.cover_ready.connect(lambda data: self._apply_cover(data, paths))
        dlg.exec()

    def _apply_track(self, track, paths: List[str]):
        fields_list = []
        for p in paths:
            cur = self._load_fields(p) or md.empty_fields()
            if track.title and not str(cur.get("title") or "").strip():
                cur["title"] = track.title
            if track.artists and not cur.get("artists"):
                cur["artists"] = track.artists
            if track.album and not str(cur.get("album") or "").strip():
                cur["album"] = track.album
            year = (track.extra or {}).get("year", "")
            if year and not str(cur.get("year") or "").strip():
                cur["year"] = year
            fields_list.append(cur)
        version = self.config.get("scrape", {}).get("id3_version", "v2.3")
        backup = self.config.get("general", {}).get("backup", True)
        self._run_task(BatchWriteTask(paths, fields_list, id3_version=version, backup=backup),
                       "正在写入元数据…")

    def _apply_lyrics(self, lyric, paths: List[str]):
        text = lyric.synced or lyric.plain
        if lyric.translation:
            text = text + "\n\n" + lyric.translation
        self.lyrics_panel.set_text(text)
        self._save_lyrics_to_tag(text)

    def _apply_cover(self, data: bytes, paths: List[str]):
        fields_list = []
        for p in paths:
            cur = self._load_fields(p) or md.empty_fields()
            cur["cover"] = data
            cur["cover_mime"] = md.AudioFile._guess_mime(data)
            fields_list.append(cur)
        version = self.config.get("scrape", {}).get("id3_version", "v2.3")
        backup = self.config.get("general", {}).get("backup", True)
        self._run_task(BatchWriteTask(paths, fields_list, id3_version=version, backup=backup),
                       "正在写入封面…")

    def _scrape_batch(self):
        paths = self.file_panel.checked_paths()
        if not paths:
            QMessageBox.information(self, "提示", "请先在左侧勾选要处理的文件")
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("批量自动刮削")
        lay = QVBoxLayout(dlg)
        chk_lyric = QCheckBox("补全歌词")
        chk_lyric.setChecked(self.config.get("scrape", {}).get("save_lyrics", True))
        chk_cover = QCheckBox("补全封面")
        chk_cover.setChecked(self.config.get("scrape", {}).get("save_cover", True))
        chk_meta = QCheckBox("补全标题/专辑/艺术家/年份")
        chk_meta.setChecked(True)
        cmb_pref = QComboBox()
        cmb_pref.addItem("优先带时间轴歌词", "synced")
        cmb_pref.addItem("优先纯文本歌词", "plain")
        lay.addWidget(QLabel(f"将对 {len(paths)} 个勾选文件自动刮削："))
        lay.addWidget(chk_lyric)
        lay.addWidget(chk_cover)
        lay.addWidget(chk_meta)
        lay.addWidget(cmb_pref)
        from PySide6.QtWidgets import QDialogButtonBox
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self._run_task(ScrapeBatchTask(
            paths, self.config, with_lyrics=chk_lyric.isChecked(),
            with_cover=chk_cover.isChecked(), with_meta=chk_meta.isChecked(),
            prefer=cmb_pref.currentData()), "批量刮削中…")

    # ---------------- 歌词 ----------------
    def _fetch_lyrics(self):
        paths = self.file_panel.selected_paths()
        if not paths:
            QMessageBox.information(self, "提示", "请先选择文件")
            return
        fields = self._load_fields(paths[0]) or md.empty_fields()
        title = str(fields.get("title") or "")
        artists = ", ".join(fields.get("artists") or [])
        kw = f"{title} {artists}".strip() or os.path.splitext(os.path.basename(paths[0]))[0]
        dlg = ScrapeDialog(kw, self.config, self)
        dlg.lyrics_ready.connect(lambda lyric: self._apply_lyrics(lyric, paths[:1]))
        dlg.cover_ready.connect(lambda data: self._apply_cover(data, paths[:1]))
        dlg.exec()

    def _translate_lyrics(self, engine: str, target: str):
        text = self.lyrics_panel.text()
        if not text.strip():
            QMessageBox.information(self, "提示", "歌词区为空")
            return
        self._run_task(TranslateTask(text, target, engine, self.config), "翻译中…")
        task = self._task
        if task is not None:
            task.item.connect(lambda out: self.lyrics_panel.set_text(out))

    # ---------------- 清理 / 转换 ----------------
    def _clean_tags(self):
        paths = self.file_panel.checked_paths()
        if not paths:
            QMessageBox.information(self, "提示", "请先勾选文件")
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("标签清理与标准化")
        lay = QVBoxLayout(dlg)
        chk_trim = QCheckBox("去除多余空格")
        chk_trim.setChecked(True)
        chk_feat = QCheckBox("统一 Feat. 写法")
        chk_feat.setChecked(True)
        chk_case = QCheckBox("英文标题式大小写")
        cmb_zh = QComboBox()
        cmb_zh.addItem("繁简不变", "")
        cmb_zh.addItem("繁体 → 简体", "t2s")
        cmb_zh.addItem("简体 → 繁体", "s2t")
        lay.addWidget(QLabel(f"将对 {len(paths)} 个勾选文件执行："))
        lay.addWidget(chk_trim)
        lay.addWidget(chk_feat)
        lay.addWidget(chk_case)
        lay.addWidget(cmb_zh)
        btn_ok = QPushButton("开始清理")
        btn_ok.clicked.connect(dlg.accept)
        lay.addWidget(btn_ok)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        options = {"trim": chk_trim.isChecked(), "feat": chk_feat.isChecked(),
                   "title_case": chk_case.isChecked(),
                   "chinese": cmb_zh.currentData()}
        version = self.config.get("scrape", {}).get("id3_version", "v2.3")
        backup = self.config.get("general", {}).get("backup", True)
        self._run_task(CleanTagsTask(paths, options, id3_version=version, backup=backup),
                       "清理标签中…")

    def _convert_id3(self):
        paths = self.file_panel.checked_paths()
        if not paths:
            QMessageBox.information(self, "提示", "请先勾选文件")
            return
        version, ok = QInputDialog.getItem(self, "ID3 版本转换",
                                           "选择目标版本（仅影响 MP3/WAV/AIFF/DSF/TTA）:",
                                           ["v2.3", "v2.4", "v1"], 0, False)
        if not ok:
            return
        self._run_task(ConvertTagsTask(paths, version), "转换 ID3 版本中…")

    # ---------------- 重命名 ----------------
    def _rename_files(self):
        paths = self.file_panel.checked_paths()
        if not paths:
            QMessageBox.information(self, "提示", "请先勾选文件")
            return
        fields_map: Dict[str, dict] = {}
        for p in paths:
            f = self._load_fields(p)
            if f:
                fields_map[p] = f
        common_dir = os.path.commonpath([os.path.dirname(os.path.abspath(p)) for p in paths])
        root = common_dir if os.path.isdir(common_dir) else ""
        dlg = RenameDialog(paths, fields_map, root=root, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        plans = [pl for pl in dlg.plans if pl[2]]
        if not plans:
            return
        if QMessageBox.question(self, "确认", f"将移动/重命名 {len(plans)} 个文件，继续？") \
                != QMessageBox.StandardButton.Yes:
            return
        self._run_task(RenameTask(plans), "重命名中…")

    # ---------------- 去重 / 报告 ----------------
    def _dedup_files(self):
        paths = self.file_panel.checked_paths()
        if not paths:
            QMessageBox.information(self, "提示", "请先勾选文件")
            return
        task = DedupTask(paths, self)
        task.item.connect(self._show_dedup)
        self._run_task(task, "检测重复文件中…")

    def _show_dedup(self, groups):
        if not groups:
            QMessageBox.information(self, "重复检测", "未发现重复文件")
            return
        text = []
        for gi, group in enumerate(groups, 1):
            text.append(f"── 重复组 {gi}（{len(group)} 个文件）──")
            for it in group:
                size = it.get("size", 0)
                text.append(f"  {it['path']}  ({size / 1024 / 1024:.1f} MB)")
            text.append("")
        dlg = QDialog(self)
        dlg.setWindowTitle("重复文件检测结果")
        lay = QVBoxLayout(dlg)
        view = QPlainTextEdit()
        view.setReadOnly(True)
        view.setPlainText("\n".join(text))
        btn = QPushButton("关闭")
        btn.clicked.connect(dlg.accept)
        lay.addWidget(view)
        lay.addWidget(btn)
        dlg.resize(700, 500)
        dlg.exec()

    def _missing_report(self):
        paths = self.file_panel.checked_paths()
        if not paths:
            QMessageBox.information(self, "提示", "请先勾选文件")
            return
        out, _ = QFileDialog.getSaveFileName(self, "保存报告", "missing_tags_report.txt",
                                             "文本 (*.txt);;CSV (*.csv)")
        if not out:
            return
        self._run_task(ReportTask(paths, out), "扫描缺失标签中…")

    # ---------------- 设置 / 关于 ----------------
    def _open_settings(self):
        dlg = SettingsDialog(self.config, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            save_config(self.config)
            self.log("设置已保存")
            self.lyrics_panel.set_engines(["google", "bing", "openai", "mymemory"])

    def _about(self):
        QMessageBox.about(
            self, f"关于 {APP_NAME}",
            f"<h3>{APP_NAME} v{__version__}</h3>"
            "<p>全格式音频 ID3 标签批量编辑、刮削与修复整理工具</p>"
            "<p>支持的格式：MP3 / FLAC / APE / WAV / AIFF / WV / TTA / M4A / MP4 / "
            "OGG / MPC / OPUS / WMA / DSF</p>"
            "<p>数据源插件：网易云音乐、QQ音乐、酷狗音乐、Lrclib、Apple Music、Musixmatch</p>"
            "<p>基于 Python + PySide6 + mutagen 开发</p>")

    def closeEvent(self, event):
        if self._task is not None and self._task.isRunning():
            if QMessageBox.question(self, "退出", "任务仍在运行，确定退出？") \
                    != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self._task.cancel()
        event.accept()
