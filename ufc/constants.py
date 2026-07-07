# -*- coding: utf-8 -*-
"""UFC Keypad - 常量、DCS-BIOS 标识符与布局辅助 (从 ufc_keypad.py 拆分)"""

GWL_EXSTYLE      = -20
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW  = 0x00000080
SWP_NOMOVE       = 0x0002
SWP_NOSIZE       = 0x0001
SWP_NOZORDER     = 0x0004
SWP_FRAMECHANGED  = 0x0020
MONITOR_DEFAULTTONEAREST = 2

WIN_W = 1024
WIN_H = 600
MORSE_FORMATION_LIGHTS = "FORMATION_DIMMER"  # DCS-BIOS 编队灯 (definePotentiometer, 0-65535)

# ============ DCS-BIOS 外部灯光控制标识 (源: FA-18C_hornet.lua) ============
DCS_LDG_TAXI   = "LDG_TAXI_SW"           # 着陆/滑行灯 ToggleSwitch (0=OFF, 1=ON)
DCS_FORM       = "FORMATION_DIMMER"       # 编队灯旋钮 0-65535
DCS_POSITION   = "POSITION_DIMMER"        # 航线灯旋钮 0-65535
DCS_STROBE_SW  = "STROBE_SW"             # 频闪灯 3PosTumb (0=BRIGHT,1=OFF,2=DIM)
LDG_STATES     = ["OFF", "ON"]            # 着陆/滑行
STROBE_STATES  = ["BRI", "OFF", "DIM"]   # 频闪灯 0=亮,1=关,2=暗
FORM_STEP      = 6554                     # 编队灯/航线灯旋钮步进 (~10% of 65535)
BG_COLOR = "#000000"  # 背景始终纯黑
# ============ 精确布局参数 (基于用户提供的尺寸数据) ============
# 左右留白8px, 上下留白7px
# 第0行: y=7,  h=90
# 第1行: y=114, h=90  (7+90+17)
# 第2行: y=221, h=90
# 第3行: y=328, h=90
# 第4行: y=435, h=90
# 第5行: y=542, h=50

Y0, H0 = 7, 90
Y1, H1 = 114, 90
Y2, H2 = 221, 90
Y3, H3 = 328, 90
Y4, H4 = 435, 90
Y5, H5 = 542, 50

# 第5行小按钮专用高度常量
ROW5_H = H5  # 50

# 水平坐标
# 第0行特殊: I/P(140) | gap(16) | 连体空白(425) | gap(16) | RTTH(255) | gap(16) | SETTINGS(140)
# 第1-4行: col0=140 | gap16 | col1=121 | gap31 | col2=121 | gap31 | col3=121 | gap16 | col4=255 | gap16 | col5=140

# 第0行坐标
R0_X = [8, 164, 605, 876]           # I/P, 连体空白, RTTH, SETTINGS
R0_W = [140, 425, 255, 140]

# 第1-4行标准6列坐标
COL_X = [8, 164, 316, 468, 605, 876]
COL_W = [140, 121, 121, 121, 255, 140]

# 第5行小按钮坐标 (11个按钮, 两端各2个方向键各62px)
# (5,0): <,  (5,1): >,  (5,2): A/P ... (5,8): ON,  (5,9): <,  (5,10): >
R5_BTN_X = [8, 70, 157, 262, 367, 472, 577, 682, 787, 892, 954]
R5_BTN_W = [62, 62, 80, 80, 80, 80, 80, 80, 80, 62, 62]

ROW_Y = [Y0, Y1, Y2, Y3, Y4, Y5]
ROW_H = [H0, H1, H2, H3, H4, H5]

MARGIN_L = 8
MARGIN_R = 8

# ============ 布局辅助函数 ============
def col_x(n):
    """返回第n列(0-5)的x坐标"""
    if 0 <= n < len(COL_X):
        return COL_X[n]
    return 8 + n * (140 + 16)  # fallback

def col_w(n):
    """返回第n列(0-5)的宽度"""
    if 0 <= n < len(COL_W):
        return COL_W[n]
    return 140  # fallback

def row_y(n):
    """返回第n行(0-5)的y坐标"""
    if 0 <= n < len(ROW_Y):
        return ROW_Y[n]
    return 7 + n * (90 + 17)  # fallback

def row_h(n):
    """返回第n行(0-5)的高度"""
    if 0 <= n < len(ROW_H):
        return ROW_H[n]
    return 90 if n < 5 else 50  # fallback

def wide_w():
    """返回宽方块的宽度 (第4列, 605~860)"""
    return 255

