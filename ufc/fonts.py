# -*- coding: utf-8 -*-
"""Hornet UFC 字体加载 (带 B612 回退)"""
import os
import sys

from PyQt6.QtGui import QFont, QFontDatabase


# ============ Hornet UFC 字体路径 ============
# 优先查找脚本同目录下的字体文件（便于移植）
# PyInstaller 打包后 sys._MEIPASS 中查找
if getattr(sys, 'frozen', False):
    _SCRIPT_DIR = sys._MEIPASS
else:
    _SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_HORNET_FONT_FILENAME = "FA-18C_Hornet_Up_Front_Controller.ttf"
HORNET_UFC_FONT_PATH = os.path.join(_SCRIPT_DIR, _HORNET_FONT_FILENAME)
_HORNET_UFC_FALLBACK = r"D:\Helios-DCS-Fonts-master\Helios-DCS-Fonts-master\Hornet Harrier Hawg Fonts\Output\FA-18C_Hornet_Up_Front_Controller.ttf"
_hornet_font_loaded = False
HORNET_UFC_FAMILY = None

def _load_hornet_font():
    """加载 Hornet UFC 字体，返回字体族名称
    查找顺序：脚本目录 → 原 D 盘路径 → B612 回退"""
    global _hornet_font_loaded, HORNET_UFC_FAMILY
    if _hornet_font_loaded:
        return HORNET_UFC_FAMILY
    _hornet_font_loaded = True
    
    # 1) 脚本同目录（便携）
    if os.path.exists(HORNET_UFC_FONT_PATH):
        font_id = QFontDatabase.addApplicationFont(HORNET_UFC_FONT_PATH)
        if font_id != -1:
            families = QFontDatabase.applicationFontFamilies(font_id)
            if families:
                HORNET_UFC_FAMILY = families[0]
                print(f"[字体] 已加载 (脚本目录): {HORNET_UFC_FAMILY}")
                return HORNET_UFC_FAMILY
    
    # 2) 原始安装路径
    if os.path.exists(_HORNET_UFC_FALLBACK):
        font_id = QFontDatabase.addApplicationFont(_HORNET_UFC_FALLBACK)
        if font_id != -1:
            families = QFontDatabase.applicationFontFamilies(font_id)
            if families:
                HORNET_UFC_FAMILY = families[0]
                print(f"[字体] 已加载 (备用路径): {HORNET_UFC_FAMILY}")
                return HORNET_UFC_FAMILY
    
    # 3) 全部失败，回退 B612
    print("[字体] Hornet UFC 字体未找到，回退到 B612")
    HORNET_UFC_FAMILY = None
    return None

def get_hornet_font(font_size):
    """获取 Hornet UFC 字体对象"""
    family = _load_hornet_font()
    if family:
        return QFont(family, font_size)
    return QFont("B612", font_size)

# ============ 分辨率 ============
WIN_W = 1024
WIN_H = 600

# ============ 按钮文本配置 ============
BUTTON_TEXTS = {
    (0, 0): "I/P",
    (0, 4): "可变显示\n(原RTTH)",
    (0, 5): "SETTINGS",
    (1, 0): "SYSTEMS",
    (1, 1): "1",
    (1, 2): "N\n2",
    (1, 3): "3",
    (1, 4): "可变显示\n(原HSEL)",
    (1, 5): "EM\nCON",
    (2, 1): "W\n4",
    (2, 2): "5",
    (2, 3): "E\n6",
    (2, 4): "可变显示\n(原BALT)",
    (3, 0): "COMM 1",
    (3, 1): "7",
    (3, 2): "S\n8",
    (3, 3): "9",
    (3, 4): "可变显示\n(原RALT)",
    (3, 5): "COMM 2",
    (4, 0): "可变显示\n(原1)",
    (4, 1): "CLR",
    (4, 2): "0",
    (4, 3): "ENT",
    (4, 4): "可变显示\n(原空白)",
    (4, 5): "可变显示\n(原2)",
    (5, 0): "<",
    (5, 1): ">",
    (5, 2): "A/P",
    (5, 3): "IFF",
    (5, 4): "TCN",
    (5, 5): "ILS",
    (5, 6): "D/L",
    (5, 7): "BCN",
    (5, 8): "ON\nOFF",
    (5, 9): "<",
    (5, 10): ">",
}
