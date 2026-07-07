# -*- coding: utf-8 -*-
"""UFC Keypad 入口：创建 QApplication 与主窗口。

运行方式：
    python main.py
打包 (PyInstaller, 单文件无控制台)：
    pyinstaller UFC_Keypad_v5.spec
"""
import sys

from PyQt6.QtWidgets import QApplication

from ufc.crashlog import setup_crash_log
from ufc.ui import UFCKeypadWindow, SettingsWindow


def main():
    setup_crash_log()
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    key_panel = UFCKeypadWindow()
    key_panel.hide()

    settings = SettingsWindow(key_panel)
    settings.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
