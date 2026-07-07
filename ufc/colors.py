# -*- coding: utf-8 -*-
"""亮度相关颜色计算 (绿色 LED 风格)"""

_CURRENT_BRIGHTNESS = 0.8  # TODO: 调试亮度，上线前改回 0.0

def _dim(brightness):
    """亮度 → 强度因子：DCS断连~0.05（微弱可见），正常运行 25%~100%"""
    if brightness <= 0:
        return 0.05  # DCS 离线：微弱可见
    return max(0.25, 0.2 + brightness * 0.8)

def text_color_br(br=None):
    """文字颜色：绿色，亮度跟随"""
    b = br if br is not None else _CURRENT_BRIGHTNESS
    f = _dim(b)
    return f"rgb({int(0*f)}, {int(255*f)}, {int(0*f)})"

def border_color_br(br=None):
    """边框颜色"""
    b = br if br is not None else _CURRENT_BRIGHTNESS
    f = _dim(b)
    return f"rgb({int(0*f)}, {int(255*f)}, {int(0*f)})"

def hover_bg_br(br=None):
    """hover 背景色"""
    b = br if br is not None else _CURRENT_BRIGHTNESS
    f = _dim(b)
    return f"rgb({int(0*f)}, {int(51*f)}, {int(0*f)})"

def pressed_bg_br(br=None):
    """按下背景色"""
    b = br if br is not None else _CURRENT_BRIGHTNESS
    f = _dim(b)
    return f"rgb({int(0*f)}, {int(85*f)}, {int(0*f)})"

# 保持向后兼容（初始化阶段用）
BORDER_COLOR = text_color_br()
TEXT_COLOR = text_color_br()
HOVER_BG = hover_bg_br()
PRESSED_BG = pressed_bg_br()

# 按钮行号标签
ROW_LABELS = {
    0: "第0行: I/P, 连体空白(可变), 可变显示, SETTINGS",
    1: "第1行: SYSTEMS, 1, N2, 3, 可变显示, EM CON",
    2: "第2行: W4, 5, E6, 可变显示",
    3: "第3行: COMM1, 7, S8, 9, 可变显示, COMM2",
    4: "第4行: 可变显示, CLR, 0, ENT, 可变显示, 可变显示",
    5: "第5行: <, >, A/P, IFF, TCN, ILS, D/L, BCN, ON OFF, <, >",
}

# 所有可选的按键名称 (单个键)
KEY_OPTIONS_SINGLE = [
    "0", "1", "2", "3", "4", "5", "6", "7", "8", "9",
    "A", "B", "C", "D", "E", "F", "G", "H", "I", "J",
    "K", "L", "M", "N", "O", "P", "Q", "R", "S", "T",
    "U", "V", "W", "X", "Y", "Z",
    "F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10", "F11", "F12",
    "Left", "Right", "Up", "Down",
    "Home", "End", "Insert", "Delete", "PageUp", "PageDown",
    "Return", "Backspace", "Tab", "Escape", "Space",
    "minus", "equal", "period", "comma", "slash", "backslash",
    "semicolon", "apostrophe", "bracketLeft", "bracketRight",
    "grave", "CapsLock", "NumLock", "ScrollLock", "Print",
    "Alt", "Control", "Shift", "Meta",
]

# 组合键预设 (Ctrl/Shift/Alt/Meta/Win + 键)
KEY_OPTIONS_COMBO = [
    "Ctrl+C", "Ctrl+V", "Ctrl+X", "Ctrl+Z", "Ctrl+A",
    "Ctrl+S", "Ctrl+F", "Ctrl+N", "Ctrl+O", "Ctrl+W",
    "Shift+Tab", "Alt+Tab", "Ctrl+Shift+Tab",
    "Alt+F4", "Ctrl+Shift+Escape",
    "Ctrl+Left", "Ctrl+Right", "Ctrl+Up", "Ctrl+Down",
    "Shift+Left", "Shift+Right", "Shift+Up", "Shift+Down",
    "Ctrl+Home", "Ctrl+End", "Shift+Home", "Shift+End",
    "Ctrl+Shift+Left", "Ctrl+Shift+Right",
    "Ctrl+plus", "Ctrl+minus", "Ctrl+0",
    "Win+D", "Win+E", "Win+R", "Win+L",
    "Ctrl+PageUp", "Ctrl+PageDown",
]

KEY_OPTIONS = KEY_OPTIONS_SINGLE + KEY_OPTIONS_COMBO

# ============================================
# DCS-BIOS 数据接收与解析
# ============================================

