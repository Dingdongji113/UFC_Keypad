# -*- coding: utf-8 -*-
"""崩溃日志系统：未捕获异常写入 ufc_crash.log。

设计目标：
- 尽可能早写入启动标记。
- 即使 threading.excepthook 不存在，也不能阻止日志启动。
- 尽量启用 faulthandler 捕获 native crash / access violation 前的 Python 栈。
"""
import faulthandler
import os
import sys
import tempfile
import time
import traceback
import threading

from ufc.config import CRASH_LOG_FILE

_LOG_READY = False
_LAST_LOG_PATH = None
_FAULT_FILE = None


def _candidate_log_paths():
    """日志路径候选。首选程序目录；失败时回落到 cwd / temp，避免静默无日志。"""
    paths = [CRASH_LOG_FILE]

    try:
        paths.append(os.path.join(os.getcwd(), "ufc_crash.log"))
    except Exception:
        pass

    try:
        paths.append(os.path.join(tempfile.gettempdir(), "ufc_crash.log"))
    except Exception:
        pass

    seen = set()
    out = []
    for p in paths:
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return out


def _write_line_to_path(path, line):
    try:
        log_dir = os.path.dirname(path)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        with open(path, 'a', encoding='utf-8') as f:
            f.write(line)
        return True
    except Exception:
        return False


def _crash_log(msg):
    """写入崩溃日志（带时间戳）。写失败时尝试 fallback 路径。"""
    global _LAST_LOG_PATH
    ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    line = f"[{ts}] {msg}\n"

    for path in _candidate_log_paths():
        if _write_line_to_path(path, line):
            _LAST_LOG_PATH = path
            return True

    try:
        sys.stderr.write(line)
        sys.stderr.flush()
    except Exception:
        pass
    return False


def _setup_faulthandler():
    """启用 faulthandler，把 native crash 的 Python 栈也写入日志。"""
    global _FAULT_FILE
    if _LAST_LOG_PATH is None:
        return
    try:
        # 保持文件句柄存活，否则 faulthandler 写入目标会失效。
        _FAULT_FILE = open(_LAST_LOG_PATH, 'a', encoding='utf-8')
        faulthandler.enable(file=_FAULT_FILE, all_threads=True)
        _crash_log("faulthandler enabled")
    except Exception as exc:
        _crash_log(f"faulthandler unavailable: {type(exc).__name__}: {exc}")


def _setup_excepthook():
    """替换全局异常钩子，将所有未捕获异常写入崩溃日志。"""
    _original_excepthook = sys.excepthook

    def _global_excepthook(exc_type, exc_value, exc_tb):
        tb_lines = traceback.format_exception(exc_type, exc_value, exc_tb)
        _crash_log("=" * 60)
        _crash_log(f"UNHANDLED EXCEPTION: {exc_type.__name__}: {exc_value}")
        _crash_log("Traceback:")
        for line in tb_lines:
            _crash_log(line.rstrip())
        _crash_log("=" * 60)
        _original_excepthook(exc_type, exc_value, exc_tb)

    sys.excepthook = _global_excepthook

    # threading.excepthook 仅 Python 3.8+ 存在；没有时不能让日志初始化失败。
    _original_thread_excepthook = getattr(threading, "excepthook", None)
    if _original_thread_excepthook is None:
        _crash_log("threading.excepthook unavailable; thread crash hook skipped")
        return

    def _thread_excepthook(args):
        tb_lines = traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)
        _crash_log("=" * 60)
        _crash_log(f"THREAD EXCEPTION in '{args.thread.name}': {args.exc_type.__name__}: {args.exc_value}")
        _crash_log("Traceback:")
        for line in tb_lines:
            _crash_log(line.rstrip())
        _crash_log("=" * 60)
        if _original_thread_excepthook is not None:
            _original_thread_excepthook(args)

    threading.excepthook = _thread_excepthook


def setup_crash_log():
    """初始化崩溃日志系统。可重复调用，避免重复安装 hook。"""
    global _LOG_READY

    # 先写启动标记，再安装 hook。这样即使 hook 安装失败，也能留下日志。
    _crash_log("=" * 40)
    _crash_log("UFC Keypad STARTED")
    _crash_log(f"Python: {sys.version}")
    _crash_log(f"Executable: {sys.executable}")
    _crash_log(f"CWD: {os.getcwd()}")
    _crash_log(f"Log path: {_LAST_LOG_PATH or CRASH_LOG_FILE}")

    if not _LOG_READY:
        try:
            _setup_faulthandler()
            _setup_excepthook()
            _LOG_READY = True
            _crash_log("crash hooks installed")
        except Exception as exc:
            _crash_log(f"failed to install crash hooks: {type(exc).__name__}: {exc}")
