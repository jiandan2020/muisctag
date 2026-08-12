# -*- coding: utf-8 -*-
"""缺失标签扫描与报告生成。"""
from __future__ import annotations
import csv
import os
from typing import Dict, List, Optional, Tuple
from .metadata import AudioFile, MetadataError

#: 关键字段（缺失即报缺）
KEY_FIELDS = ["title", "artists", "album", "track", "year", "genre"]


def scan_missing(paths: List[str], required: Optional[List[str]] = None) -> List[Dict[str, object]]:
    """扫描文件，返回 [{path, missing: [字段], fields: {...}}]。"""
    req = required or KEY_FIELDS
    rows: List[Dict[str, object]] = []
    for path in paths:
        try:
            fields = AudioFile(path).read()
        except MetadataError:
            rows.append({"path": path, "missing": ["<读取失败>"], "fields": {}})
            continue
        missing = []
        for k in req:
            v = fields.get(k)
            if isinstance(v, list):
                if not v:
                    missing.append(k)
            elif not str(v or "").strip():
                missing.append(k)
        if missing:
            rows.append({"path": path, "missing": missing, "fields": fields})
    return rows


def write_report(rows: List[Dict[str, object]], out_path: str) -> int:
    """写出报告（.csv 或 .txt），返回写入行数。"""
    if out_path.lower().endswith(".csv"):
        with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["文件路径", "缺失字段"])
            for r in rows:
                writer.writerow([r["path"], ", ".join(r["missing"])])
    else:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("MusicTag 缺失标签报告\n")
            f.write("=" * 60 + "\n")
            for i, r in enumerate(rows, 1):
                f.write(f"{i}. {r['path']}\n")
                f.write(f"   缺失: {', '.join(r['missing'])}\n")
    return len(rows)
