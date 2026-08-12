# -*- coding: utf-8 -*-
"""MusicTag 程序入口。

运行方式：
    python main.py

首次运行会自动在 %APPDATA%/MusicTag 生成配置文件。
"""
from __future__ import annotations
import sys


def main() -> int:
    from PySide6.QtWidgets import QApplication
    from musictag.gui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("MusicTag")
    app.setOrganizationName("MusicTag")

    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
