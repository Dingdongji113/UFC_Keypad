# -*- coding: utf-8 -*-
"""UFC Keypad 入口：创建 QApplication 与主窗口。

运行方式：
    python main.py
打包 (PyInstaller, 单文件无控制台)：
    pyinstaller UFC_Keypad_v5.spec
"""
import os
import sys
import tempfile
import time
import traceback


def _bootstrap_log_path():
    """main.py 最早期日志路径：不依赖 ufc 包，避免 import 崩溃无日志。"""
    candidates = []
    try:
        candidates.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ufc_bootstrap.log"))
    except Exception:
        pass
    try:
        candidates.append(os.path.join(os.getcwd(), "ufc_bootstrap.log"))
    except Exception:
        pass
    try:
        candidates.append(os.path.join(tempfile.gettempdir(), "ufc_bootstrap.log"))
    except Exception:
        pass
    return candidates


def _bootstrap_log(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    line = f"[{ts}] {msg}\n"
    for path in _bootstrap_log_path():
        try:
            log_dir = os.path.dirname(path)
            if log_dir:
                os.makedirs(log_dir, exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(line)
            return
        except Exception:
            continue
    try:
        sys.stderr.write(line)
        sys.stderr.flush()
    except Exception:
        pass


def main():
    _bootstrap_log("=" * 60)
    _bootstrap_log("main.py entered")
    _bootstrap_log(f"Python: {sys.version}")
    _bootstrap_log(f"Executable: {sys.executable}")
    _bootstrap_log(f"argv: {sys.argv}")
    _bootstrap_log(f"CWD: {os.getcwd()}")

    try:
        _bootstrap_log("ensuring ufc package import compatibility")
        from _bootstrap_imports import ensure_ufc_package
        pkg_dir = ensure_ufc_package(os.path.dirname(os.path.abspath(__file__)))
        _bootstrap_log(f"ufc package dir: {pkg_dir}")

        _bootstrap_log("importing crashlog")
        from ufc.crashlog import setup_crash_log, _crash_log
        _bootstrap_log("crashlog imported")

        setup_crash_log()
        _crash_log("main.py formal crash log active")

        _bootstrap_log("importing PyQt6 QApplication")
        from PyQt6.QtWidgets import QApplication
        _bootstrap_log("PyQt6 QApplication imported")

        _bootstrap_log("importing startup/ui/windowing/cold_start modules")
        from ufc.ifei_rpm import install_ifei_rpm_fallback
        from ufc.realtime_rpm import install_realtime_rpm_callbacks
        from ufc.startup import attach_startup_style_settings
        from ufc.ui import UFCKeypadWindow, SettingsWindow
        from ufc.windowing import patch_settings_window_apply_screen
        from ufc.cold_start import patch_cold_start
        from ufc.cold_direct_entry import install_cold_direct_entry
        install_ifei_rpm_fallback()
        install_realtime_rpm_callbacks()
        patch_settings_window_apply_screen(SettingsWindow)
        patch_cold_start(UFCKeypadWindow)
        install_cold_direct_entry(UFCKeypadWindow)
        _bootstrap_log("startup/ui/windowing/cold_start modules imported")

        _bootstrap_log("creating QApplication")
        app = QApplication(sys.argv)
        app.setStyle("Fusion")

        _bootstrap_log("creating UFCKeypadWindow")
        key_panel = UFCKeypadWindow()
        _bootstrap_log("startup overlay deferred until DCS-BIOS state is known")
        key_panel.hide()

        _bootstrap_log("creating SettingsWindow")
        settings = SettingsWindow(key_panel)
        attach_startup_style_settings(settings)
        settings.show()

        _bootstrap_log("entering Qt event loop")
        sys.exit(app.exec())
    except BaseException as exc:
        _bootstrap_log("=" * 60)
        _bootstrap_log(f"FATAL BOOTSTRAP EXCEPTION: {type(exc).__name__}: {exc}")
        _bootstrap_log("Traceback:")
        for line in traceback.format_exc().splitlines():
            _bootstrap_log(line)
        _bootstrap_log("=" * 60)

        try:
            _crash_log("=" * 60)  # noqa: F821
            _crash_log(f"FATAL STARTUP EXCEPTION: {type(exc).__name__}: {exc}")  # noqa: F821
            _crash_log("Traceback:")  # noqa: F821
            for line in traceback.format_exc().splitlines():
                _crash_log(line)  # noqa: F821
            _crash_log("=" * 60)  # noqa: F821
        except Exception:
            pass
        raise


if __name__ == "__main__":
    main()
