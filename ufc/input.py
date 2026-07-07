# -*- coding: utf-8 -*-
"""Windows 原生触控钩子 (WH_MOUSE_LL) 与键位注入 (SendInput / PostMessage)"""
import ctypes
import ctypes.wintypes
import threading
import time

from ufc.crashlog import _crash_log
from ufc.constants import MONITOR_DEFAULTTONEAREST

# ============ Windows 原生触控 + WH_MOUSE_LL 光标锁定 ============
# RegisterTouchWindow: 阻止 Windows 将触摸合成为鼠标点击
# WH_MOUSE_LL: 在 OS 层面拦截触摸驱动注入的鼠标移动事件
_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32
TWF_FINETOUCH    = 0x00000001
WM_TOUCH         = 0x0240

# --- 结构体 ---
class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt",          _POINT),
        ("mouseData",   ctypes.wintypes.DWORD),
        ("flags",       ctypes.wintypes.DWORD),
        ("time",        ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]

class _RECT(ctypes.Structure):
    _fields_ = [
        ("left",   ctypes.wintypes.LONG),
        ("top",    ctypes.wintypes.LONG),
        ("right",  ctypes.wintypes.LONG),
        ("bottom", ctypes.wintypes.LONG),
    ]

class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize",    ctypes.wintypes.DWORD),
        ("rcMonitor", _RECT),
        ("rcWork",    _RECT),
        ("dwFlags",   ctypes.wintypes.DWORD),
    ]

# --- WH_MOUSE_LL 常量 ---
WH_MOUSE_LL      = 14
LLMHF_INJECTED   = 0x00000001    # 事件由触摸/笔驱动注入（非真实鼠标）
WM_MOUSEMOVE     = 0x0200
WM_QUIT_HOOK     = 0x0012        # WM_QUIT
WM_MOUSEACTIVATE = 0x0021        # 鼠标点击激活窗口前发送
MA_NOACTIVATE    = 3              # 不激活、不设置鼠标在窗口内
WM_ACTIVATE      = 0x0006         # 窗口激活/失活通知
# --- 钩子状态 ---
_hook_handle       = None
_hook_thread       = None
_hook_running      = False
_hook_thread_id    = 0
_dcs_monitor_rect  = None         # (left, top, right, bottom) DCS 所在显示器的屏幕坐标

# --- Win32 API 声明 ---
HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_longlong,
                               ctypes.c_int,
                               ctypes.wintypes.WPARAM,
                               ctypes.wintypes.LPARAM)

_user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC,
                                       ctypes.wintypes.HINSTANCE, ctypes.wintypes.DWORD]
_user32.SetWindowsHookExW.restype  = ctypes.wintypes.HHOOK
_user32.UnhookWindowsHookEx.argtypes = [ctypes.wintypes.HHOOK]
_user32.UnhookWindowsHookEx.restype  = ctypes.wintypes.BOOL
_user32.CallNextHookEx.argtypes = [ctypes.wintypes.HHOOK, ctypes.c_int,
                                    ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM]
_user32.CallNextHookEx.restype  = ctypes.c_longlong
_user32.GetMessageW.argtypes = [ctypes.wintypes.LPMSG, ctypes.wintypes.HWND,
                                 ctypes.wintypes.UINT, ctypes.wintypes.UINT]
_user32.GetMessageW.restype  = ctypes.wintypes.BOOL
_user32.PostThreadMessageW.argtypes = [ctypes.wintypes.DWORD, ctypes.wintypes.UINT,
                                        ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM]
_user32.PostThreadMessageW.restype  = ctypes.wintypes.BOOL
_user32.GetWindowRect.argtypes = [ctypes.wintypes.HWND, ctypes.POINTER(_RECT)]
_user32.GetWindowRect.restype  = ctypes.wintypes.BOOL
_user32.MonitorFromPoint.argtypes = [_POINT, ctypes.wintypes.DWORD]
_user32.MonitorFromPoint.restype  = ctypes.wintypes.HMONITOR
_user32.GetMonitorInfoW.argtypes = [ctypes.wintypes.HMONITOR, ctypes.POINTER(MONITORINFO)]
_user32.GetMonitorInfoW.restype  = ctypes.wintypes.BOOL
_kernel32.GetCurrentThreadId.argtypes = []
_kernel32.GetCurrentThreadId.restype  = ctypes.wintypes.DWORD
_user32.GetWindowLongPtrW.argtypes = [ctypes.wintypes.HWND, ctypes.c_int]
_user32.GetWindowLongPtrW.restype  = ctypes.c_longlong
_user32.SetWindowLongPtrW.argtypes = [ctypes.wintypes.HWND, ctypes.c_int, ctypes.c_longlong]
_user32.SetWindowLongPtrW.restype  = ctypes.c_longlong
_user32.SetLayeredWindowAttributes.argtypes = [ctypes.wintypes.HWND,
                                             ctypes.wintypes.COLORREF,
                                             ctypes.wintypes.BYTE,
                                             ctypes.wintypes.DWORD]
_user32.SetLayeredWindowAttributes.restype  = ctypes.wintypes.BOOL
_user32.SetWindowPos.argtypes = [ctypes.wintypes.HWND, ctypes.wintypes.HWND,
                                  ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                  ctypes.wintypes.UINT]
_user32.SetWindowPos.restype  = ctypes.wintypes.BOOL


# --- WH_MOUSE_LL 钩子回调（模块级函数，由 Windows 在独立线程中调用） ---
def _point_in_rect(pt, rect):
    """判断 POINT 是否在矩形 (left, top, right, bottom) 内"""
    return rect[0] <= pt.x <= rect[2] and rect[1] <= pt.y <= rect[3]


@HOOKPROC
def _mouse_hook_proc(nCode, wParam, lParam):
    """每一条鼠标消息到达窗口前都会经过此回调。
    拦截策略：如果移动事件来自触摸驱动(LLMHF_INJECTED) 且目标不在 DCS 显示器 → 返回 1 吞掉"""
    if nCode >= 0 and wParam == WM_MOUSEMOVE:
        ms = ctypes.cast(lParam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
        if ms.flags & LLMHF_INJECTED:
            safe = _dcs_monitor_rect
            if safe and not _point_in_rect(ms.pt, safe):
                return 1   # 拦截：光标要逃离 DCS 显示器
    return _user32.CallNextHookEx(_hook_handle, nCode, wParam, lParam)


# --- 查找 DCS 窗口所在显示器 ---
def _find_dcs_monitor():
    """更新 _dcs_monitor_rect 为 DCS 窗口所在的显示器屏幕坐标。
    DCS 未运行时不做任何事，钩子此时为完全透明（所有事件放行）。"""
    global _dcs_monitor_rect
    hwnd = _find_dcs_window()
    if not hwnd:
        return False
    wr = _RECT()
    if not _user32.GetWindowRect(hwnd, ctypes.byref(wr)):
        return False
    # 用窗口中心找显示器
    cx, cy = (wr.left + wr.right) // 2, (wr.top + wr.bottom) // 2
    hmon = _user32.MonitorFromPoint(_POINT(cx, cy), MONITOR_DEFAULTTONEAREST)
    mi = MONITORINFO()
    mi.cbSize = ctypes.sizeof(mi)
    if not _user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
        return False
    _dcs_monitor_rect = (mi.rcMonitor.left, mi.rcMonitor.top, mi.rcMonitor.right, mi.rcMonitor.bottom)
    return True


# --- 钩子线程：安装钩子 + Windows 消息泵 ---
def _hook_thread_proc():
    """WH_MOUSE_LL 要求所在线程运行消息泵。此函数在 daemon 线程中运行。"""
    global _hook_handle, _hook_thread_id
    _hook_thread_id = _kernel32.GetCurrentThreadId()
    _hook_handle = _user32.SetWindowsHookExW(WH_MOUSE_LL, _mouse_hook_proc, None, 0)
    if not _hook_handle:
        return
    msg = ctypes.wintypes.MSG()
    while _hook_running:
        ret = _user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
        if ret in (0, -1):
            break
    # 退出：卸载钩子
    if _hook_handle:
        _user32.UnhookWindowsHookEx(_hook_handle)
        _hook_handle = None


def _start_mouse_hook():
    """启动 WH_MOUSE_LL 钩子线程"""
    global _hook_thread, _hook_running
    if _hook_running:
        return
    _find_dcs_monitor()
    _hook_running = True
    _hook_thread = threading.Thread(target=_hook_thread_proc, daemon=True, name="MouseHook")
    _hook_thread.start()


def _stop_mouse_hook():
    """停止 WH_MOUSE_LL 钩子"""
    global _hook_running
    _hook_running = False
    if _hook_thread_id:
        _user32.PostThreadMessageW(_hook_thread_id, WM_QUIT_HOOK, 0, 0)


# --- RegisterTouchWindow：阻止触摸→鼠标点击合成 ---

def _register_native_touch(hwnd_int):
    """注册原生触控：Windows 不再合成鼠标点击/滚轮事件"""
    return bool(_user32.RegisterTouchWindow(ctypes.wintypes.HWND(hwnd_int), TWF_FINETOUCH))

def _unregister_native_touch(hwnd_int):
    """注销原生触控"""
    return bool(_user32.UnregisterTouchWindow(ctypes.wintypes.HWND(hwnd_int)))

# ============ Windows SendInput API — 系统级按键注入 ============
# 用 SendInput 替代 QApplication.sendEvent，按键直达 Windows 输入队列，
# 由系统投递给前台窗口（配合 MonMouse 确保 DCS 保持前台）
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP   = 0x0002

class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk",         ctypes.wintypes.WORD),
        ("wScan",       ctypes.wintypes.WORD),
        ("dwFlags",     ctypes.wintypes.DWORD),
        ("time",        ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]

class _INPUT(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.wintypes.DWORD),
        ("ki",   _KEYBDINPUT),
    ]

def _send_input_key(vk_code, key_up=False):
    """通过 SendInput 发送单个按键事件（按下或释放），使用虚拟键码"""
    flags = KEYEVENTF_KEYUP if key_up else 0
    inp = _INPUT(
        type=INPUT_KEYBOARD,
        ki=_KEYBDINPUT(
            wVk=vk_code,
            wScan=0,
            dwFlags=flags,
            time=0,
            dwExtraInfo=None,
        ),
    )
    _user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))

# 按键名 → (VK码, 扫描码) 映射
# 字符串键 → Windows VK
_VK_MAP = {
    "0": 0x30, "1": 0x31, "2": 0x32, "3": 0x33, "4": 0x34,
    "5": 0x35, "6": 0x36, "7": 0x37, "8": 0x38, "9": 0x39,
    "A": 0x41, "B": 0x42, "C": 0x43, "D": 0x44, "E": 0x45,
    "F": 0x46, "G": 0x47, "H": 0x48, "I": 0x49, "J": 0x4A,
    "K": 0x4B, "L": 0x4C, "M": 0x4D, "N": 0x4E, "O": 0x4F,
    "P": 0x50, "Q": 0x51, "R": 0x52, "S": 0x53, "T": 0x54,
    "U": 0x55, "V": 0x56, "W": 0x57, "X": 0x58, "Y": 0x59, "Z": 0x5A,
    "F1": 0x70, "F2": 0x71, "F3": 0x72, "F4": 0x73,
    "F5": 0x74, "F6": 0x75, "F7": 0x76, "F8": 0x77,
    "F9": 0x78, "F10": 0x79, "F11": 0x7A, "F12": 0x7B,
    "Left": 0x25, "Right": 0x27, "Up": 0x26, "Down": 0x28,
    "Home": 0x24, "End": 0x23, "Insert": 0x2D, "Delete": 0x2E,
    "PageUp": 0x21, "PageDown": 0x22,
    "Return": 0x0D, "Enter": 0x0D, "Backspace": 0x08,
    "Tab": 0x09, "Escape": 0x1B, "Esc": 0x1B, "Space": 0x20,
    "minus": 0xBD, "Minus": 0xBD,
    "plus": 0xBB, "Plus": 0xBB, "equal": 0xBB, "Equal": 0xBB,
    "period": 0xBE, "Period": 0xBE, "comma": 0xBC, "Comma": 0xBC,
    "slash": 0xBF, "Slash": 0xBF, "backslash": 0xDC, "Backslash": 0xDC,
    "semicolon": 0xBA, "Semicolon": 0xBA,
    "apostrophe": 0xDE, "Apostrophe": 0xDE,
    "bracketLeft": 0xDB, "bracketRight": 0xDD,
    "grave": 0xC0, "Grave": 0xC0,
    "CapsLock": 0x14, "NumLock": 0x90, "ScrollLock": 0x91,
    "Print": 0x2C, "Pause": 0x13,
    "Ctrl": 0x11, "Control": 0x11, "LCtrl": 0xA2, "RCtrl": 0xA3,
    "Shift": 0x10, "LShift": 0xA0, "RShift": 0xA1,
    "Alt": 0x12, "LAlt": 0xA4, "RAlt": 0xA5,
    "Meta": 0x5B, "Win": 0x5B, "LWin": 0x5B, "RWin": 0x5C,
    # DCS 特殊
    "JOY_BTN1": 0x01, "JOY_BTN2": 0x02, "JOY_BTN3": 0x03,
}

def inject_key_combo(key_str: str):
    """
    发送组合键到 DCS。
    
    优先方案: SendInput 系统注入 —— 驱动层按键，DCS 的 DirectInput
    /Raw Input 能正确捕获。需要 DCS 在前台（鼠标钩子+防激活保
    证了这一点）。

    回退方案: PostMessage 直投 DCS 窗口 —— 无需焦点，但 DCS 用
    DirectInput 读取键盘时会忽略 WM_KEYDOWN/WM_KEYUP 消息。
    """
    if not key_str:
        return

    parts = [p.strip() for p in key_str.split("+")]
    if not parts:
        return

    # 分类：修饰键 vs 主键
    modifier_names = {"Ctrl", "Control", "LCtrl", "RCtrl",
                      "Shift", "LShift", "RShift",
                      "Alt", "LAlt", "RAlt",
                      "Meta", "Win", "LWin", "RWin"}
    mod_vks = []
    main_vk = None
    main_name = None

    for p in parts:
        vk = _VK_MAP.get(p)
        if vk is None:
            continue
        if p in modifier_names:
            mod_vks.append(vk)
        else:
            main_vk = vk
            main_name = p

    if main_vk is None:
        return  # 全是修饰键，无主键

    # 优先 SendInput（驱动层注入，DCS DirectInput 能捕获）
    # PostMessage 投递 WM_KEYDOWN 虽然"成功"，但 DCS 用 DirectInput/Raw Input
    # 不读消息队列，所以消息被忽略。SendInput 走驱动层，DirectInput 能抓到。
    # 当 DCS 不在前台或 SendInput 失败时，回退到 PostMessage。
    _inject_via_sendinput(mod_vks, main_vk) or _inject_via_postmessage(mod_vks, main_vk)


# ========== 方案A: PostMessage 直投 DCS 窗口（无需焦点）==========
WM_KEYDOWN = 0x0100
WM_KEYUP   = 0x0101

# 已缓存 DCS 窗口句柄 (首次查找后缓存，效率高)
_dcs_hwnd_cache = None
_dcs_hwnd_cache_time = 0
_DCS_CACHE_TTL = 3.0  # 缓存 3 秒后重新查找

# 声明 Win32 API
_user32.FindWindowW.argtypes = [ctypes.wintypes.LPCWSTR, ctypes.wintypes.LPCWSTR]
_user32.FindWindowW.restype  = ctypes.wintypes.HWND
_user32.GetWindowThreadProcessId.argtypes = [ctypes.wintypes.HWND, ctypes.POINTER(ctypes.wintypes.DWORD)]
_user32.GetWindowThreadProcessId.restype  = ctypes.wintypes.DWORD
_user32.IsWindowVisible.argtypes = [ctypes.wintypes.HWND]
_user32.IsWindowVisible.restype  = ctypes.wintypes.BOOL
_user32.GetWindowTextLengthW.argtypes = [ctypes.wintypes.HWND]
_user32.GetWindowTextLengthW.restype  = ctypes.c_int
_user32.GetWindowTextW.argtypes = [ctypes.wintypes.HWND, ctypes.wintypes.LPWSTR, ctypes.c_int]
_user32.GetWindowTextW.restype  = ctypes.c_int
_user32.PostMessageW.argtypes = [ctypes.wintypes.HWND, ctypes.wintypes.UINT,
                                  ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM]
_user32.PostMessageW.restype  = ctypes.wintypes.BOOL
_user32.MapVirtualKeyW.argtypes = [ctypes.wintypes.UINT, ctypes.wintypes.UINT]
_user32.MapVirtualKeyW.restype  = ctypes.wintypes.UINT

_WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
_user32.EnumWindows.argtypes = [_WNDENUMPROC, ctypes.wintypes.LPARAM]
_user32.EnumWindows.restype  = ctypes.wintypes.BOOL


def _vk_to_scan(vk):
    """VK 码 → 扫描码 (MAPVK_VK_TO_VSC = 0)"""
    return _user32.MapVirtualKeyW(vk, 0)


def _find_dcs_window():
    """查找 DCS World 主窗口 HWND。支持多种匹配策略，结果缓存 3 秒。"""
    global _dcs_hwnd_cache, _dcs_hwnd_cache_time
    now = time.time()
    if _dcs_hwnd_cache and (now - _dcs_hwnd_cache_time) < _DCS_CACHE_TTL:
        # 验证缓存的窗口是否仍然有效
        if _user32.IsWindowVisible(_dcs_hwnd_cache):
            return _dcs_hwnd_cache
        _dcs_hwnd_cache = None

    found = []

    # 策略1: 精确匹配 "Digital Combat Simulator"
    def enum_callback(hwnd, lparam):
        if not _user32.IsWindowVisible(hwnd):
            return True
        length = _user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        _user32.GetWindowTextW(hwnd, buf, length + 1)
        if 'Digital Combat Simulator' in buf.value:
            found.append(hwnd)
            return False  # 找到，停止枚举
        return True

    _user32.EnumWindows(_WNDENUMPROC(enum_callback), 0)

    if found:
        _dcs_hwnd_cache = found[0]
        _dcs_hwnd_cache_time = now
        return found[0]

    # 策略2: 宽泛匹配 "DCS"
    found2 = []

    def enum_callback2(hwnd, lparam):
        if not _user32.IsWindowVisible(hwnd):
            return True
        length = _user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        _user32.GetWindowTextW(hwnd, buf, length + 1)
        if 'DCS' in buf.value:
            found2.append(hwnd)
        return True

    _user32.EnumWindows(_WNDENUMPROC(enum_callback2), 0)
    if found2:
        _dcs_hwnd_cache = found2[0]
        _dcs_hwnd_cache_time = now
        return found2[0]

    return None


def _post_key(vk_code, key_up=False):
    """通过 PostMessage 发送单个按键到 DCS 窗口。返回 True 表示投递成功。"""
    hwnd = _find_dcs_window()
    if not hwnd:
        return False

    scan = _vk_to_scan(vk_code)
    msg = WM_KEYUP if key_up else WM_KEYDOWN

    # lParam 编码 (标准 Windows 键盘消息格式):
    # bits 0-15:  repeat count (1)
    # bits 16-23: scan code
    # bit 24:     extended key (0 for most keys)
    # bit 29:     context code (0 = key was pressed, not Alt+SysRq)
    # bit 30:     previous key state (0 for press, 1 for release)
    # bit 31:     transition (0 = press, 1 = release)
    if key_up:
        lparam = (scan << 16) | 0xC0000001
    else:
        lparam = (scan << 16) | 0x00000001

    return bool(_user32.PostMessageW(hwnd, msg, vk_code, lparam))


def _inject_via_postmessage(mod_vks, main_vk):
    """PostMessage 直投方案。成功返回 True，失败返回 False。"""
    hwnd = _find_dcs_window()
    if not hwnd:
        return False

    # 1) 按下所有修饰键
    for vk in mod_vks:
        _post_key(vk, key_up=False)

    # 2) 按下 + 释放主键
    _post_key(main_vk, key_up=False)
    _post_key(main_vk, key_up=True)

    # 3) 释放修饰键（逆序）
    for vk in reversed(mod_vks):
        _post_key(vk, key_up=True)

    return True


# ========== 方案B: SendInput 系统注入 ==========
def _inject_via_sendinput(mod_vks, main_vk):
    """SendInput 系统级按键注入。返回 True 表示已发送（不保证 DCS 收到）。"""
    for vk in mod_vks:
        _send_input_key(vk, key_up=False)
    _send_input_key(main_vk, key_up=False)
    _send_input_key(main_vk, key_up=True)
    for vk in reversed(mod_vks):
        _send_input_key(vk, key_up=True)
    return True  # SendInput 已调用，但不保证 DCS 收到（DCS 用 Raw Input 会忽略合成事件）


# ========== DCS-BIOS 控制命令发送（正解！）==========
# DCS-BIOS 控制命令端口（客户端 → DCS）
