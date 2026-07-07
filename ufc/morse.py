# -*- coding: utf-8 -*-
"""莫尔斯电码引擎：文本 -> 点划序列"""

# ============ 摩尔斯电码表 ============
MORSE_CODE = {
    'A': '.-', 'B': '-...', 'C': '-.-.', 'D': '-..', 'E': '.',
    'F': '..-.', 'G': '--.', 'H': '....', 'I': '..', 'J': '.---',
    'K': '-.-', 'L': '.-..', 'M': '--', 'N': '-.', 'O': '---',
    'P': '.--.', 'Q': '--.-', 'R': '.-.', 'S': '...', 'T': '-',
    'U': '..-', 'V': '...-', 'W': '.--', 'X': '-..-', 'Y': '-.--',
    'Z': '--..',
    '0': '-----', '1': '.----', '2': '..---', '3': '...--', '4': '....-',
    '5': '.....', '6': '-....', '7': '--...', '8': '---..', '9': '----.',
}
MORSE_FORMATION_LIGHTS = "FORMATION_DIMMER"  # DCS-BIOS 编队灯 (definePotentiometer, 0-65535)

# ============ DCS-BIOS 外部灯光控制标识 (源: FA-18C_hornet.lua) ============
DCS_LDG_TAXI   = "LDG_TAXI_SW"           # 着陆/滑行灯 ToggleSwitch (0=OFF, 1=ON)
DCS_FORM       = "FORMATION_DIMMER"       # 编队灯旋钮 0-65535
DCS_POSITION   = "POSITION_DIMMER"        # 航线灯旋钮 0-65535
DCS_STROBE_SW  = "STROBE_SW"             # 频闪灯 3PosTumb (0=BRIGHT,1=OFF,2=DIM)
LDG_STATES     = ["OFF", "ON"]            # 着陆/滑行
STROBE_STATES  = ["BRI", "OFF", "DIM"]   # 频闪灯 0=亮,1=关,2=暗
FORM_STEP      = 6554                     # 编队灯/航线灯旋钮步进 (~10% of 65535)

def text_to_morse(text):
    """文本 → 摩尔斯电码字符串 (用 . - / 表示)"""
    result = []
    for ch in text.upper():
        if ch == ' ':
            result.append('/')
        elif ch in MORSE_CODE:
            result.append(MORSE_CODE[ch])
    return ' '.join(result)

