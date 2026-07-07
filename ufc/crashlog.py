# -*- coding: utf-8 -*-
"""崩溃日志系统：未捕获异常写入 ufc_crash.log"""
import sys
import time
import traceback
import threading

from ufc.config import CRASH_LOG_FILE

def _crash_log(msg):
    """写入崩溃日志（带时间戳）"""
    ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    try:
        with open(CRASH_LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(f"[{ts}] {msg}\n")
    except Exception:
        pass  # 写日志本身不能再崩溃

def _setup_excepthook():
    """替换全局异常钩子，将所有未捕获异常写入崩溃日志"""
    _original_excepthook = sys.excepthook

    def _global_excepthook(exc_type, exc_value, exc_tb):
        tb_lines = traceback.format_exception(exc_type, exc_value, exc_tb)
        _crash_log("=" * 60)
        _crash_log(f"UNHANDLED EXCEPTION: {exc_type.__name__}: {exc_value}")
        _crash_log("Traceback:")
        for line in tb_lines:
            _crash_log(line.rstrip())
        _crash_log("=" * 60)
        # 仍然调用原始 excepthook（打印到 stderr）
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
    """初始化崩溃日志系统"""
    # 写入启动标记
    _crash_log("=" * 40)
    _crash_log("UFC Keypad STARTED")
    _crash_log(f"Python: {sys.version}")
    _setup_excepthook()
