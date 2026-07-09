"""UFC_Keypad 模块化项目验证脚本（无需显示器，offscreen 运行）"""
import sys
import os
import importlib

from _bootstrap_imports import ensure_ufc_package

PKG_DIR = ensure_ufc_package(os.getcwd())
PKG_PATH = "ufc" if os.path.exists(os.path.join(os.getcwd(), "ufc", "__init__.py")) else "UFC"
if PKG_DIR is None:
    raise RuntimeError("Cannot find ufc/ or UFC/ package directory")

# ---- 1. 逐模块编译 ----
import py_compile
mods = [
    "main.py",
    f"{PKG_PATH}/__init__.py", f"{PKG_PATH}/constants.py", f"{PKG_PATH}/crashlog.py", f"{PKG_PATH}/config.py",
    f"{PKG_PATH}/fonts.py", f"{PKG_PATH}/morse.py", f"{PKG_PATH}/colors.py", f"{PKG_PATH}/dcs_bios.py",
    f"{PKG_PATH}/input.py", f"{PKG_PATH}/widgets.py", f"{PKG_PATH}/startup.py",
    f"{PKG_PATH}/windowing.py", f"{PKG_PATH}/ifei_rpm.py", f"{PKG_PATH}/cold_start.py",
    f"{PKG_PATH}/cold_direct_entry.py", f"{PKG_PATH}/ui.py",
]
for m in mods:
    py_compile.compile(m, doraise=True)
print(f"[1] COMPILE OK  ({len(mods)} 个模块全部通过, package={PKG_PATH})")

# ---- 2. 逐模块独立 import（捕获 import 级错误）----
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import PyQt6  # noqa
for name in ["constants", "crashlog", "config", "fonts", "morse",
             "colors", "dcs_bios", "input", "widgets", "startup",
             "windowing", "ifei_rpm", "cold_start", "cold_direct_entry", "ui"]:
    importlib.import_module("ufc." + name)
print("[2] IMPORT OK  (所有子模块均可独立导入)")

# ---- 3. 构造主窗口 + SettingsWindow ----
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QMouseEvent
app = QApplication.instance() or QApplication(sys.argv)

from ufc.ui import UFCKeypadWindow, SettingsWindow
from ufc.dcs_bios import DCSBIOSReceiver
from ufc.ifei_rpm import install_ifei_rpm_fallback
import ufc.cold_start as CS
import ufc.cold_direct_entry as CDE
from ufc.cold_start import patch_cold_start
from ufc.cold_direct_entry import install_cold_direct_entry
from ufc.startup import (
    STARTUP_STYLE_ANIME_MILLENNIUM,
    STARTUP_STYLE_UFC_BIT,
    AnimeMillenniumStartupOverlay,
    UFCBitStartupOverlay,
    attach_startup_style_settings,
    install_startup_overlay,
)
install_ifei_rpm_fallback()
patch_cold_start(UFCKeypadWindow)
install_cold_direct_entry(UFCKeypadWindow)
w = UFCKeypadWindow()
startup = install_startup_overlay(w, STARTUP_STYLE_UFC_BIT)
assert isinstance(startup, UFCBitStartupOverlay)
s = SettingsWindow(w)
combo = attach_startup_style_settings(s)
assert combo is not None
print(f"[3] CONSTRUCT OK  (local cells={len(w.cells)}, "
      f"morse cells={len(w._morse_cells)}, light displays={len(w._light_displays)})")

# ---- 3a. IFEI RPM fallback ----
rx = DCSBIOSReceiver()
rx._use_fallback_addresses()
assert rx.parser.address_to_field.get(0x749E) == ("IFEI_RPM_L", 3)
assert rx.parser.address_to_field.get(0x74A2) == ("IFEI_RPM_R", 3)
assert DCSBIOSReceiver.UFC_FIELDS["IFEI_RPM_L"][0] == "left_engine_rpm"
assert DCSBIOSReceiver.UFC_FIELDS["IFEI_RPM_R"][0] == "right_engine_rpm"
print("[3a] IFEI RPM FALLBACK OK  (L @ 0x749E, R @ 0x74A2, len=3)")

# [3b] 触发真实 GUI 事件路径（复现 showEvent/paintEvent 类错误，如 _user32/_dim 缺失）
w.show()
app.processEvents()
startup.update()
app.processEvents()
startup.on_dcs_signal("ufc_brightness", "0.5")
app.processEvents()
anime = install_startup_overlay(w, STARTUP_STYLE_ANIME_MILLENNIUM)
assert isinstance(anime, AnimeMillenniumStartupOverlay)
assert w._startup_overlay is anime
anime.update()
app.processEvents()
anime.on_dcs_signal("ufc_brightness", "0.5")
app.processEvents()
bit = install_startup_overlay(w, STARTUP_STYLE_UFC_BIT)
assert isinstance(bit, UFCBitStartupOverlay)
assert w._startup_overlay is bit
for p in ["morse_light", "light_control", "select", "cold_start", "local_icp"]:
    w._show_page(p)
    app.processEvents()
w.update()
app.processEvents()
print("[3b] GUI EVENTS OK  (showEvent/paintEvent 触发无异常)")

# ---- 4. 页面切换 ----
for p in ["morse_light", "light_control", "select", "cold_start", "local_icp"]:
    w._show_page(p)
    assert w._current_page == p, p
print("[4] PAGE SWITCH OK  (local_icp / select / morse_light / light_control / cold_start)")

# ---- 4b. 冷启动入口 + 任意一发 RPM gating + 断线重置 ----
w.dcs_bios.latest.clear()
w._cold_reset_session_state("verify start")
w._show_page("local_icp")
w._cold_on_dcs_signal("UFC_SCRATCHPAD_STRING_1_DISPLAY", "")
assert w._current_page == "cold_start"
assert w._cold_last_action == "WAIT ENGINE RPM DATA"
assert w._cold_detected_mode == CS.STARTUP_MODE_UNKNOWN

# fresh left low only -> still unknown
w._update_display("left_engine_rpm", "  0")
assert w._cold_detected_mode == CS.STARTUP_MODE_UNKNOWN
# fresh both low -> auto cold page
w._cold_first_mode_decided = False
w._update_display("right_engine_rpm", "  0")
assert w._current_page == "cold_start"
assert w._cold_last_action == "AUTO COLD START ENTRY"
w.on_cell_click((300, 0))  # START -> ARMED
assert w._cold_state == "armed"
w._cold_abort()

# Simulate leaving a cold mission: old latest still contains 0/0, but timeout reset must remove it.
w.dcs_bios.latest["IFEI_RPM_L"] = "  0"
w.dcs_bios.latest["IFEI_RPM_R"] = "  0"
w._cold_reset_session_state("verify mission switch")
assert "IFEI_RPM_L" not in w.dcs_bios.latest
assert "IFEI_RPM_R" not in w.dcs_bios.latest
w._show_page("local_icp")
w._cold_on_dcs_signal("UFC_SCRATCHPAD_STRING_1_DISPLAY", "")
assert w._current_page == "cold_start"
assert w._cold_last_action == "WAIT ENGINE RPM DATA"
# Now the new hot mission sends fresh right RPM. It must override old cold state and become non-cold.
w._cold_first_mode_decided = False
w._update_display("right_engine_rpm", "  75")
assert w._cold_detected_mode == CS.STARTUP_MODE_NON_COLD
assert CDE.MIN_STARTUP_ANIM_MS == 5000

w._cold_reset_session_state("verify suffix parse")
w._update_display("left_engine_rpm", "120F")
assert w._cold_detected_mode == CS.STARTUP_MODE_NON_COLD
print("[4b] COLD ENTRY / LOCAL ICP GATING OK  (fresh RPM only, stale RPM cleared, min anim 5s)")

# ---- 4c. 冷启动配置键 ----
cs_cfg = CS._merged_config()
required_controls = {
    "battery_on", "apu_start", "right_engine_crank", "left_engine_crank", "apu_off",
    "canopy_close", "bleed_air_cycle", "trim_reset", "fcs_reset", "ecm_receive",
    "ins_land", "ins_carrier", "display_lddi", "display_rddi", "display_ampcd", "display_hud",
}
assert required_controls.issubset(set(cs_cfg["cold_start_controls"].keys()))
assert "sequence" in cs_cfg["cold_start_controls"]["bleed_air_cycle"]
assert cs_cfg.get("cold_start_left_rpm_threshold") == 60
print("[4c] COLD START CONFIG OK  (supervised controls + bleed-air sequence + RPM threshold present)")

# ---- 5. UFCCell 真实按键路径 ----
import ufc.widgets as W
sent = []
_orig_send = W.send_dcs_bios
_orig_release = W._send_release
try:
    W.send_dcs_bios = lambda identifier, value: sent.append((identifier, value)) or True
    W._send_release = lambda identifier: sent.append((identifier, 0)) or True
    cell = W.UFCCell("1", (1, 1), no_feedback=False)
    press = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPointF(5, 5), QPointF(5, 5), QPointF(5, 5),
        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    )
    release = QMouseEvent(
        QMouseEvent.Type.MouseButtonRelease,
        QPointF(5, 5), QPointF(5, 5), QPointF(5, 5),
        Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
    )
    cell.mousePressEvent(press)
    cell.mouseReleaseEvent(release)
    app.processEvents()
    assert sent[0] == ("UFC_1", 1), sent
finally:
    W.send_dcs_bios = _orig_send
    W._send_release = _orig_release
print(f"[5] UFCCELL CLICK OK  (sent={sent})")

# ---- 6. 莫尔斯引擎 ----
from ufc.morse import text_to_morse
assert text_to_morse("SOS") == "... --- ...", text_to_morse("SOS")
assert text_to_morse("A") == ".-", text_to_morse("A")
assert text_to_morse(" ") == "/", text_to_morse(" ")
assert " " in text_to_morse("SOS A")
print("[6] MORSE OK  (SOS -> '... --- ...', A -> '.-', space -> '/')")

# ---- 7. 亮度同步（单一真值 colors._CURRENT_BRIGHTNESS）----
import ufc.colors as C
w._brightness = 0.5
w._refresh_brightness()
assert C._CURRENT_BRIGHTNESS == 0.5, C._CURRENT_BRIGHTNESS
print(f"[7] BRIGHTNESS SYNC OK  (colors._CURRENT_BRIGHTNESS = {C._CURRENT_BRIGHTNESS})")

# ---- 8. 灯光状态机 ----
st = w._light_state
assert set(st.keys()) >= {"ldg", "form", "pos", "strobe"}
print(f"[8] LIGHT STATE OK  ({st})")

# ---- 9. DCS-BIOS 指令发送路径 ----
from ufc.dcs_bios import send_dcs_bios
ok = send_dcs_bios("FORMATION_DIMMER", 32767)
print(f"[9] DCS-BIOS SEND OK  (returned {ok})")

# ---- 10. 配置读写 ----
from ufc.config import load_config, save_config
cfg = load_config()
cfg.setdefault("startup_style", STARTUP_STYLE_UFC_BIT)
cfg.setdefault("cold_start_display_mode", "day")
cfg.setdefault("cold_start_left_rpm_threshold", 60)
save_config(cfg)
print(f"[10] CONFIG OK  (keys={sorted(cfg.keys())})")

# ---- 11. 入口 main.py 可干净导入且含 main() ----
spec = importlib.util.spec_from_file_location("ufc_main", os.path.join(os.getcwd(), "main.py"))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
assert hasattr(mod, "main")
print("[11] MAIN.PY OK  (import clean, has main())")

app.quit()
print("\n========== ALL 11 CHECKS PASSED ==========")
