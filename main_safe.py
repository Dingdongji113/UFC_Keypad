# -*- coding: utf-8 -*-
"""UFC Keypad 安全模式入口。

用途：
    python main_safe.py

安全模式会尽量跳过容易导致原生崩溃的组件：
- 不安装启动动画 overlay
- 不启动 DCS-BIOS 接收线程
- 不启动 WH_MOUSE_LL 鼠标钩子
- 不启用原生触控隔离

用于判断 main.py 闪退是否来自 native hook / DCS-BIOS / startup overlay。
"""
import os
import sys
import tempfile
import time
import traceback


def _safe_log_path():
    candidates = []
    try:
        candidates.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ufc_safe.log"))
    except Exception:
        pass
    try:
        candidates.append(os.path.join(os.getcwd(), "ufc_safe.log"))
    except Exception:
        pass
    try:
        candidates.append(os.path.join(tempfile.gettempdir(), "ufc_safe.log"))
    except Exception:
        pass
    return candidates


def _safe_log(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    line = f"[{ts}] {msg}\n"
    for path in _safe_log_path():
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
    os.environ["UFC_SAFE_MODE"] = "1"
    _safe_log("=" * 60)
    _safe_log("main_safe.py entered")
    _safe_log(f"Python: {sys.version}")
    _safe_log(f"Executable: {sys.executable}")
    _safe_log(f"CWD: {os.getcwd()}")

    try:
        from _bootstrap_imports import ensure_ufc_package
        pkg_dir = ensure_ufc_package(os.path.dirname(os.path.abspath(__file__)))
        _safe_log(f"ufc package dir: {pkg_dir}")

        from ufc.crashlog import setup_crash_log, _crash_log
        setup_crash_log()
        _crash_log("main_safe.py formal crash log active")

        from PyQt6.QtWidgets import QApplication

        # 先导入底层模块并打补丁，再导入 ui。
        import ufc.input as input_mod
        import ufc.dcs_bios as dcs_mod
        from ufc.ifei_rpm import install_ifei_rpm_fallback
        install_ifei_rpm_fallback()

        def _noop(*args, **kwargs):
            return False

        input_mod._start_mouse_hook = lambda *args, **kwargs: None
        input_mod._stop_mouse_hook = lambda *args, **kwargs: None
        input_mod._register_native_touch = _noop
        input_mod._unregister_native_touch = _noop
        input_mod._find_dcs_window = lambda *args, **kwargs: None
        input_mod._find_dcs_monitor = lambda *args, **kwargs: None

        def _receiver_start_noop(self):
            print("[SAFE] DCS-BIOS receiver thread disabled")

        def _receiver_stop_noop(self):
            print("[SAFE] DCS-BIOS receiver stop skipped")

        dcs_mod.DCSBIOSReceiver.start = _receiver_start_noop
        dcs_mod.DCSBIOSReceiver.stop = _receiver_stop_noop

        from ufc.ui import UFCKeypadWindow, SettingsWindow
        from ufc.windowing import patch_settings_window_apply_screen
        from ufc.cold_start import patch_cold_start
        patch_settings_window_apply_screen(SettingsWindow)
        patch_cold_start(UFCKeypadWindow)

        app = QApplication(sys.argv)
        app.setStyle("Fusion")

        key_panel = UFCKeypadWindow()
        key_panel.hide()

        settings = SettingsWindow(key_panel)
        settings.setWindowTitle("UFC Keypad - Settings (SAFE MODE)")
        settings.show()

        _safe_log("safe mode entering Qt event loop")
        sys.exit(app.exec())
    except BaseException as exc:
        _safe_log("=" * 60)
        _safe_log(f"FATAL SAFE MODE EXCEPTION: {type(exc).__name__}: {exc}")
        _safe_log("Traceback:")
        for line in traceback.format_exc().splitlines():
            _safe_log(line)
        _safe_log("=" * 60)
        raise


if __name__ == "__main__":
    main()
