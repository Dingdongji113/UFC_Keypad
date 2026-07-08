"""UFC_Keypad 模块化项目验证脚本（无需显示器，offscreen 运行）"""
import sys
import os
import importlib

# ---- 1. 逐模块编译 ----
import py_compile
mods = [
    "main.py",
    "ufc/__init__.py", "ufc/constants.py", "ufc/crashlog.py", "ufc/config.py",
    "ufc/fonts.py", "ufc/morse.py", "ufc/colors.py", "ufc/dcs_bios.py",
    "ufc/input.py", "ufc/widgets.py", "ufc/startup.py", "ufc/ui.py",
]
for m in mods:
    py_compile.compile(m, doraise=True)
print(f"[1] COMPILE OK  ({len(mods)} 个模块全部通过)")

# ---- 2. 逐模块独立 import（捕获 import 级错误）----
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import PyQt6  # noqa
for name in ["constants", "crashlog", "config", "fonts", "morse",
             "colors", "dcs_bios", "input", "widgets", "startup", "ui"]:
    importlib.import_module("ufc." + name)
print("[2] IMPORT OK  (所有子模块均可独立导入)")

# ---- 3. 构造主窗口 + SettingsWindow ----
from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication(sys.argv)

from ufc.ui import UFCKeypadWindow, SettingsWindow
from ufc.startup import (
    STARTUP_STYLE_ANIME_MILLENNIUM,
    STARTUP_STYLE_UFC_BIT,
    AnimeMillenniumStartupOverlay,
    UFCBitStartupOverlay,
    attach_startup_style_settings,
    create_startup_overlay,
)
w = UFCKeypadWindow()
startup = create_startup_overlay(STARTUP_STYLE_UFC_BIT, w)
assert isinstance(startup, UFCBitStartupOverlay)
w._dcs_signal.connect(startup.on_dcs_signal)
s = SettingsWindow(w)
combo = attach_startup_style_settings(s)
assert combo is not None
print(f"[3] CONSTRUCT OK  (local cells={len(w.cells)}, "
      f"morse cells={len(w._morse_cells)}, light displays={len(w._light_displays)})")

# [3b] 触发真实 GUI 事件路径（复现 showEvent/paintEvent 类错误，如 _user32/_dim 缺失）
w.show()
app.processEvents()
startup.update()
app.processEvents()
startup.on_dcs_signal("ufc_brightness", "0.5")
app.processEvents()
anime = create_startup_overlay(STARTUP_STYLE_ANIME_MILLENNIUM, w)
assert isinstance(anime, AnimeMillenniumStartupOverlay)
anime.update()
app.processEvents()
anime.on_dcs_signal("ufc_brightness", "0.5")
app.processEvents()
for p in ["morse_light", "light_control", "select", "local_icp"]:
    w._show_page(p)
    app.processEvents()
w.update()
app.processEvents()
print("[3b] GUI EVENTS OK  (showEvent/paintEvent 触发无异常)")

# ---- 4. 页面切换 ----
for p in ["morse_light", "light_control", "select", "local_icp"]:
    w._show_page(p)
    assert w._current_page == p, p
print("[4] PAGE SWITCH OK  (local_icp / select / morse_light / light_control)")

# ---- 5. 莫尔斯引擎 ----
from ufc.morse import text_to_morse
assert text_to_morse("SOS") == "... --- ...", text_to_morse("SOS")
assert text_to_morse("A") == ".-", text_to_morse("A")
assert text_to_morse(" ") == "/", text_to_morse(" ")
assert " " in text_to_morse("SOS A")  # 字母间有空格分隔
print("[5] MORSE OK  (SOS -> '... --- ...', A -> '.-', space -> '/')")

# ---- 6. 亮度同步（单一真值 colors._CURRENT_BRIGHTNESS）----
import ufc.colors as C
w._brightness = 0.5
w._refresh_brightness()
assert C._CURRENT_BRIGHTNESS == 0.5, C._CURRENT_BRIGHTNESS
print(f"[6] BRIGHTNESS SYNC OK  (colors._CURRENT_BRIGHTNESS = {C._CURRENT_BRIGHTNESS})")

# ---- 7. 灯光状态机 ----
st = w._light_state
assert set(st.keys()) >= {"ldg", "form", "pos", "strobe"}
print(f"[7] LIGHT STATE OK  ({st})")

# ---- 8. DCS-BIOS 指令发送路径 ----
from ufc.dcs_bios import send_dcs_bios
ok = send_dcs_bios("FORMATION_DIMMER", 32767)
print(f"[8] DCS-BIOS SEND OK  (returned {ok})")

# ---- 9. 配置读写 ----
from ufc.config import load_config, save_config
cfg = load_config()
cfg.setdefault("startup_style", STARTUP_STYLE_UFC_BIT)
save_config(cfg)  # round-trip
print(f"[9] CONFIG OK  (keys={sorted(cfg.keys())})")

# ---- 10. 入口 main.py 可干净导入且含 main() ----
spec = importlib.util.spec_from_file_location("ufc_main", os.path.join(os.getcwd(), "main.py"))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
assert hasattr(mod, "main")
print("[10] MAIN.PY OK  (import clean, has main())")

app.quit()
print("\n========== ALL 10 CHECKS PASSED ==========")
