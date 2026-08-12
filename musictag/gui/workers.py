# -*- coding: utf-8 -*-
"""后台任务线程：批量读写、刮削、重命名、转换、报告等。

所有任务继承 TaskThread，通过 Qt 信号与主线程通信，避免界面卡顿。
"""
from __future__ import annotations
import json
import os
import shutil
import time
from typing import Any, Callable, Dict, List, Optional

from PySide6.QtCore import QThread, Signal

from ..core import metadata as md
from ..core.dedup import find_duplicates
from ..core.renamer import plan_rename
from ..core.report import scan_missing, write_report
from ..core.tag_cleaner import clean_fields
from ..lyrics.translator import translate_lyrics
from ..scrapers.manager import ScrapeManager


class TaskThread(QThread):
    """线程基类。"""
    progress = Signal(int)                      # 0-100
    message = Signal(str)                       # 状态/日志
    done = Signal(bool, str)                    # (是否成功, 说明)
    item = Signal(object)                       # 单文件结果

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cancelled = False

    def cancel(self):
        self._cancelled = True


# ---------------------------------------------------------------------------
# 读取文件标签
# ---------------------------------------------------------------------------

class LoadFilesTask(TaskThread):
    """后台批量读取文件标签。"""

    def __init__(self, paths: List[str], parent=None):
        super().__init__(parent)
        self.paths = paths

    def run(self):
        results: List[Dict[str, Any]] = []
        total = len(self.paths)
        for i, p in enumerate(self.paths, 1):
            if self._cancelled:
                break
            try:
                fields = md.AudioFile(p).read()
                results.append({"path": p, "fields": fields, "error": ""})
            except Exception as exc:
                results.append({"path": p, "fields": {}, "error": str(exc)})
            self.progress.emit(int(i / total * 100) if total else 100)
        self.item.emit(results)
        self.done.emit(True, f"已加载 {len(results)} 个文件")


# ---------------------------------------------------------------------------
# 批量写入标签（含自动备份）
# ---------------------------------------------------------------------------

def _backup_fields(path: str, fields: Dict[str, Any], backup_root: str) -> None:
    """将原始标签快照写入备份目录（JSON）。"""
    try:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        d = os.path.join(backup_root, stamp)
        os.makedirs(d, exist_ok=True)
        safe = path.replace(":", "_").replace("\\", "_").replace("/", "_")
        with open(os.path.join(d, safe + ".json"), "w", encoding="utf-8") as f:
            json.dump({"path": path, "fields": fields}, f, ensure_ascii=False)
    except Exception:
        pass


class BatchWriteTask(TaskThread):
    """批量写入标签；fields_list 与 paths 一一对应。"""

    def __init__(self, paths: List[str], fields_list: List[Dict[str, Any]],
                 id3_version: str = "v2.3", backup: bool = True, parent=None):
        super().__init__(parent)
        self.paths = paths
        self.fields_list = fields_list
        self.id3_version = id3_version
        self.backup = backup

    def run(self):
        from ..utils.config import config_dir
        errors = 0
        total = len(self.paths)
        for i, (path, fields) in enumerate(zip(self.paths, self.fields_list), 1):
            if self._cancelled:
                break
            try:
                if self.backup:
                    try:
                        _backup_fields(path, md.AudioFile(path).read(), os.path.join(config_dir(), "backups"))
                    except Exception:
                        pass
                af = md.AudioFile(path)
                af.write(fields)
                # 若为 ID3 格式，按设置转换版本
                if self.id3_version in ("v2.3", "v2.4") and af.ext in md.ID3_EXTENSIONS:
                    md.convert_id3_version(path, self.id3_version)
                self.message.emit(f"已保存: {os.path.basename(path)}")
            except Exception as exc:
                errors += 1
                self.message.emit(f"失败: {os.path.basename(path)} ({exc})")
            self.progress.emit(int(i / total * 100) if total else 100)
        self.done.emit(errors == 0, f"完成，成功 {total - errors} / 失败 {errors}")


# ---------------------------------------------------------------------------
# 批量刮削
# ---------------------------------------------------------------------------

class ScrapeBatchTask(TaskThread):
    """对每个文件自动刮削并补全歌词/封面/年份等字段。"""

    def __init__(self, paths: List[str], config: Dict[str, Any],
                 with_lyrics: bool = True, with_cover: bool = True,
                 with_meta: bool = True, prefer: str = "synced", parent=None):
        super().__init__(parent)
        self.paths = paths
        self.config = config
        self.with_lyrics = with_lyrics
        self.with_cover = with_cover
        self.with_meta = with_meta
        self.prefer = prefer

    def run(self):
        manager = ScrapeManager(self.config)
        ok = 0
        total = len(self.paths)
        for i, path in enumerate(self.paths, 1):
            if self._cancelled:
                break
            try:
                af = md.AudioFile(path)
                fields = af.read()
                keyword = self._keyword(path, fields)
                if not keyword:
                    self.message.emit(f"跳过（无关键词）: {os.path.basename(path)}")
                    continue
                self.message.emit(f"刮削中: {os.path.basename(path)} ({keyword})")
                best, lyric, cover = manager.scrape_file(
                    keyword, prefer=self.prefer,
                    with_cover=self.with_cover, with_lyrics=self.with_lyrics)
                changed = False
                if self.with_meta and best:
                    bf = best.to_fields() or {}
                    for key, tag_key in (("title", "title"), ("album", "album"),
                                         ("year", "year"), ("genre", "genre"),
                                         ("track", "track"), ("disc", "disc"),
                                         ("composer", "composer"), ("comment", "comment")):
                        if not fields.get(tag_key) and bf.get(key):
                            fields[tag_key] = bf[key]
                    if not fields.get("artists") and bf.get("artists"):
                        fields["artists"] = bf["artists"]
                    changed = True
                if self.with_lyrics and lyric:
                    text = lyric.best_text(self.prefer)
                    if text and not fields.get("lyrics"):
                        fields["lyrics"] = text
                        changed = True
                if self.with_cover and cover:
                    fields["cover"] = self._resize_cover(cover)
                    fields["cover_mime"] = md.AudioFile._guess_mime(fields["cover"])
                    changed = True
                if changed:
                    af.write(fields)
                    ok += 1
                    self.message.emit(f"已补全: {os.path.basename(path)}")
                else:
                    self.message.emit(f"无可用数据: {os.path.basename(path)}")
            except Exception as exc:
                self.message.emit(f"失败: {os.path.basename(path)} ({exc})")
            self.progress.emit(int(i / total * 100) if total else 100)
        self.done.emit(True, f"批量刮削完成，更新 {ok} 个文件")


    def _resize_cover(self, data: bytes) -> bytes:
        """按设置缩放封面（cover_size=0 表示原图）。"""
        size = int((self.config.get("scrape") or {}).get("cover_size", 300) or 0)
        if size <= 0:
            return data
        try:
            from PIL import Image
            import io
            img = Image.open(io.BytesIO(data))
            img.thumbnail((size, size), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            if img.mode in ("RGBA", "P", "LA"):
                img.convert("RGB").save(buf, "JPEG", quality=92)
            else:
                img.save(buf, "JPEG", quality=92)
            return buf.getvalue()
        except Exception:
            return data

    @staticmethod
    def _keyword(path: str, fields: Dict[str, Any]) -> str:
        title = str(fields.get("title") or "").strip()
        artists = ", ".join(fields.get("artists") or [])
        if title:
            return f"{title} {artists}".strip()
        stem = os.path.splitext(os.path.basename(path))[0]
        return stem


# ---------------------------------------------------------------------------
# 重命名 / 整理
# ---------------------------------------------------------------------------

class RenameTask(TaskThread):
    """按计划执行重命名/移动。plans: [(src, dst, changed)]。"""

    def __init__(self, plans: List[Any], parent=None):
        super().__init__(parent)
        self.plans = plans

    def run(self):
        ok = 0
        errors = 0
        total = len(self.plans)
        for i, (src, dst, changed) in enumerate(self.plans, 1):
            if self._cancelled:
                break
            if not changed:
                continue
            try:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                if os.path.exists(dst):
                    raise FileExistsError(f"目标已存在: {dst}")
                shutil.move(src, dst)
                ok += 1
                self.message.emit(f"已移动: {os.path.basename(src)} -> {os.path.basename(dst)}")
            except Exception as exc:
                errors += 1
                self.message.emit(f"失败: {src} ({exc})")
            self.progress.emit(int(i / total * 100) if total else 100)
        self.done.emit(errors == 0, f"重命名完成，成功 {ok} / 失败 {errors}")


# ---------------------------------------------------------------------------
# 标签清理 / ID3 版本转换
# ---------------------------------------------------------------------------

class CleanTagsTask(TaskThread):
    """批量清理并标准化标签。"""

    def __init__(self, paths: List[str], options: Dict[str, Any],
                 id3_version: str = "v2.3", backup: bool = True, parent=None):
        super().__init__(parent)
        self.paths = paths
        self.options = options
        self.id3_version = id3_version
        self.backup = backup

    def run(self):
        from ..utils.config import config_dir
        ok = 0
        total = len(self.paths)
        for i, path in enumerate(self.paths, 1):
            if self._cancelled:
                break
            try:
                af = md.AudioFile(path)
                if self.backup:
                    _backup_fields(path, af.read(), os.path.join(config_dir(), "backups"))
                cleaned = clean_fields(af.read(), self.options)
                af.write(cleaned)
                if self.id3_version in ("v2.3", "v2.4") and af.ext in md.ID3_EXTENSIONS:
                    md.convert_id3_version(path, self.id3_version)
                ok += 1
            except Exception as exc:
                self.message.emit(f"失败: {os.path.basename(path)} ({exc})")
            self.progress.emit(int(i / total * 100) if total else 100)
        self.done.emit(True, f"清理完成 {ok}/{total}")


class ConvertTagsTask(TaskThread):
    """批量转换 ID3 版本。"""

    def __init__(self, paths: List[str], version: str, parent=None):
        super().__init__(parent)
        self.paths = paths
        self.version = version

    def run(self):
        ok = 0
        total = len(self.paths)
        for i, path in enumerate(self.paths, 1):
            if self._cancelled:
                break
            success, msg = md.convert_id3_version(path, self.version)
            if success:
                ok += 1
            self.message.emit(f"{os.path.basename(path)}: {msg}")
            self.progress.emit(int(i / total * 100) if total else 100)
        self.done.emit(True, f"版本转换完成 {ok}/{total}")


# ---------------------------------------------------------------------------
# 去重 / 报告
# ---------------------------------------------------------------------------

class DedupTask(TaskThread):
    """重复文件检测。"""

    def __init__(self, paths: List[str], parent=None):
        super().__init__(parent)
        self.paths = paths

    def run(self):
        self.message.emit("正在计算指纹与元数据…")
        groups = find_duplicates(self.paths)
        self.item.emit(groups)
        self.done.emit(True, f"检测完成，发现 {len(groups)} 组重复")


class ReportTask(TaskThread):
    """缺失标签扫描与报告导出。"""

    def __init__(self, paths: List[str], out_path: str, parent=None):
        super().__init__(parent)
        self.paths = paths
        self.out_path = out_path

    def run(self):
        rows = scan_missing(self.paths)
        n = write_report(rows, self.out_path)
        self.done.emit(True, f"报告已生成: {self.out_path}（{n} 个文件缺失字段）")


class TranslateTask(TaskThread):
    """歌词翻译。"""

    def __init__(self, text: str, dst: str, engine: str, config: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.text = text
        self.dst = dst
        self.engine = engine
        self.config = config

    def run(self):
        try:
            self.message.emit("翻译中…")
            out = translate_lyrics(self.text, dst=self.dst, engine=self.engine, config=self.config)
            self.item.emit(out)
            self.done.emit(True, "翻译完成")
        except Exception as exc:
            self.done.emit(False, f"翻译失败: {exc}")
