# -*- coding: utf-8 -*-
"""崩溃日志系统：未捕获异常写入 ufc_crash.log"""
import os
import sys
import tempfile
import time
import traceback
import threading

from ufc.config import CRASH_LOG_FILE

_LOG_READY = False
_LAST_LOG_PATH = None


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

    # 去重并保序
    seen = set()
    out = []
    for p in paths:
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return out


def _crash_log(msg):
    """写入崩溃日志（带时间戳）。写失败时尝试 fallback 路径。"""
    global _LAST_LOG_PATH
    ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    line = f"[{ts}] {msg}\n"

    for path in _candidate_log_paths():
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'a', encoding='utf-8') as f:
                f.write(line)
            _LAST_LOG_PATH = path
            return True
        except Exception:
            continue

    # GUI/无控制台模式下这可能不可见，但至少不要再静默吞掉。
    try:
        sys.stderr.write(line)
        sys.stderr.flush()
    except Exception:
        pass
    return False


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

    # 线程内的未捕获异常
    _original_thread_excepthook = threading.excepthook

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

    sys.excepthook = _global_excepthook
    threading.excepthook = _thread_excepthook


def setup_crash_log():
    """初始化崩溃日志系统。可重复调用，避免重复安装 hook。"""
    global _LOG_READY
    if not _LOG_READY:
        _setup_excepthook()
        _LOG_READY = True

    _crash_log("=" * 40)
    _crash_log("UFC Keypad STARTED")
    _crash_log(f"Python: {sys.version}")
    _crash_log(f"Log path: {_LAST_LOG_PATH or CRASH_LOG_FILE}")
