# -*- coding: utf-8 -*-
"""UFC Keypad 入口：创建 QApplication 与主窗口。

运行方式：
    python main.py
打包 (PyInstaller, 单文件无控制台)：
    pyinstaller UFC_Keypad_v5.spec
"""
import sys
import traceback

from ufc.crashlog import setup_crash_log, _crash_log


def main():
    # 必须在导入 PyQt / UI 模块前启动日志。
    # 否则 ufc.startup / ufc.ui 的 import-time 异常不会写入 ufc_crash.log。
    setup_crash_log()

    try:
        from PyQt6.QtWidgets import QApplication
        from ufc.startup import attach_startup_style_settings, install_startup_overlay
        from ufc.ui import UFCKeypadWindow, SettingsWindow

        app = QApplication(sys.argv)
        app.setStyle("Fusion")

        key_panel = UFCKeypadWindow()
        install_startup_overlay(key_panel)
        key_panel.hide()

        settings = SettingsWindow(key_panel)
        attach_startup_style_settings(settings)
        settings.show()

        sys.exit(app.exec())
    except Exception as exc:
        _crash_log("=" * 60)
        _crash_log(f"FATAL STARTUP EXCEPTION: {type(exc).__name__}: {exc}")
        _crash_log("Traceback:")
        for line in traceback.format_exc().splitlines():
            _crash_log(line)
        _crash_log("=" * 60)
        raise


if __name__ == "__main__":
    main()
