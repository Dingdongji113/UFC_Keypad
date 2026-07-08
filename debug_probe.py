# -*- coding: utf-8 -*-
"""启动诊断探针。

用途：
    python debug_probe.py

它不依赖项目日志系统，使用标准库先写 startup_probe.log，逐步测试：
- Python / cwd / sys.path
- ufc.config
- ufc.crashlog
- PyQt6
- ufc.startup
- ufc.ui
- QApplication
- UFCKeypadWindow
- SettingsWindow

如果 main.py 直接闪退且无 ufc_crash.log，请先运行本脚本。
"""
import os
import sys
import tempfile
import time
import traceback

_LOG_PATHS = []
try:
    _LOG_PATHS.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "startup_probe.log"))
except Exception:
    pass
try:
    _LOG_PATHS.append(os.path.join(os.getcwd(), "startup_probe.log"))
except Exception:
    pass
try:
    _LOG_PATHS.append(os.path.join(tempfile.gettempdir(), "startup_probe.log"))
except Exception:
    pass


def log(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    line = f"[{ts}] {msg}\n"
    wrote = False
    for path in _LOG_PATHS:
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(line)
            wrote = True
            break
        except Exception:
            continue
    print(line, end="")
    if not wrote:
        print("[probe] failed to write log file")


def step(name, fn):
    log("-" * 60)
    log(f"STEP START: {name}")
    try:
        result = fn()
        log(f"STEP OK: {name}")
        return result
    except BaseException as exc:
        log(f"STEP FAIL: {name}: {type(exc).__name__}: {exc}")
        log("Traceback:")
        for line in traceback.format_exc().splitlines():
            log(line)
        raise


def main():
    log("=" * 60)
    log("startup probe entered")
    log(f"Python: {sys.version}")
    log(f"Executable: {sys.executable}")
    log(f"argv: {sys.argv}")
    log(f"CWD: {os.getcwd()}")
    log(f"__file__: {__file__}")
    log(f"sys.path[0]: {sys.path[0] if sys.path else ''}")

    cfg_mod = step("import ufc.config", lambda: __import__("ufc.config", fromlist=["*"]))
    log(f"CONFIG_FILE: {getattr(cfg_mod, 'CONFIG_FILE', None)}")
    log(f"CRASH_LOG_FILE: {getattr(cfg_mod, 'CRASH_LOG_FILE', None)}")

    crashlog = step("import ufc.crashlog", lambda: __import__("ufc.crashlog", fromlist=["*"]))
    step("setup_crash_log", crashlog.setup_crash_log)

    qtwidgets = step("import PyQt6.QtWidgets", lambda: __import__("PyQt6.QtWidgets", fromlist=["QApplication"]))
    QApplication = qtwidgets.QApplication

    step("import ufc.startup", lambda: __import__("ufc.startup", fromlist=["*"]))
    ui_mod = step("import ufc.ui", lambda: __import__("ufc.ui", fromlist=["UFCKeypadWindow", "SettingsWindow"]))

    app = step("create QApplication", lambda: QApplication.instance() or QApplication(sys.argv))
    app.setStyle("Fusion")

    key_panel = step("construct UFCKeypadWindow", ui_mod.UFCKeypadWindow)
    settings = step("construct SettingsWindow", lambda: ui_mod.SettingsWindow(key_panel))
    log(f"constructed objects: key_panel={key_panel}, settings={settings}")
    log("probe completed without entering app.exec()")


if __name__ == "__main__":
    try:
        main()
    except BaseException:
        log("probe failed")
        raise
    finally:
        try:
            input("\nProbe finished. Press Enter to close...")
        except Exception:
            pass
