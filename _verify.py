"""UFC_Keypad 模块化项目验证脚本（无需显示器，offscreen 运行）"""
import os
import sys
import importlib
import py_compile

from _bootstrap_imports import ensure_ufc_package

PKG_DIR = ensure_ufc_package(os.getcwd())
PKG_PATH = "ufc" if os.path.exists(os.path.join(os.getcwd(), "ufc", "__init__.py")) else "UFC"
if PKG_DIR is None:
    raise RuntimeError("Cannot find ufc/ or UFC/ package directory")

# ---- 1. 逐模块编译 ----
mods = [
    "main.py",
    f"{PKG_PATH}/__init__.py", f"{PKG_PATH}/constants.py", f"{PKG_PATH}/crashlog.py", f"{PKG_PATH}/config.py",
    f"{PKG_PATH}/fonts.py", f"{PKG_PATH}/morse.py", f"{PKG_PATH}/colors.py", f"{PKG_PATH}/dcs_bios.py",
    f"{PKG_PATH}/input.py", f"{PKG_PATH}/widgets.py", f"{PKG_PATH}/startup.py",
    f"{PKG_PATH}/windowing.py", f"{PKG_PATH}/ifei_rpm.py", f"{PKG_PATH}/realtime_rpm.py",
    f"{PKG_PATH}/cold_start.py", f"{PKG_PATH}/cold_direct_entry.py", f"{PKG_PATH}/cold_setup_split.py",
    f"{PKG_PATH}/cold_ui_fixups.py", f"{PKG_PATH}/ui.py",
]
for m in mods:
    py_compile.compile(m, doraise=True)
print(f"[1] COMPILE OK  ({len(mods)} 个模块全部通过, package={PKG_PATH})")

# ---- 2. 逐模块独立 import ----
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import PyQt6  # noqa
for name in [
    "constants", "crashlog", "config", "fonts", "morse", "colors", "dcs_bios", "input", "widgets",
    "startup", "windowing", "ifei_rpm", "realtime_rpm", "cold_start", "cold_direct_entry",
    "cold_setup_split", "cold_ui_fixups", "ui",
]:
    importlib.import_module("ufc." + name)
print("[2] IMPORT OK  (所有子模块均可独立导入)")

# ---- 3. 构造主窗口 + SettingsWindow ----
from PyQt6.QtWidgets import QApplication, QLabel
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QMouseEvent
app = QApplication.instance() or QApplication(sys.argv)

from ufc.ui import UFCKeypadWindow, SettingsWindow
from ufc.dcs_bios import DCSBIOSReceiver
from ufc.ifei_rpm import install_ifei_rpm_fallback, IFEI_RPM_L_ADDR, IFEI_RPM_R_ADDR
from ufc.realtime_rpm import install_realtime_rpm_callbacks, _decode_rpm_state
import ufc.cold_start as CS
import ufc.cold_direct_entry as CDE
import ufc.cold_setup_split as CSS
from ufc.cold_start import patch_cold_start
from ufc.cold_direct_entry import install_cold_direct_entry
from ufc.cold_setup_split import install_split_land_cv_setup
from ufc.cold_ui_fixups import install_cold_ui_fixups
from ufc.startup import (
    STARTUP_STYLE_ANIME_MILLENNIUM,
    STARTUP_STYLE_UFC_BIT,
    AnimeMillenniumStartupOverlay,
    UFCBitStartupOverlay,
    attach_startup_style_settings,
    install_startup_overlay,
)
install_ifei_rpm_fallback()
install_realtime_rpm_callbacks()
patch_cold_start(UFCKeypadWindow)
install_cold_direct_entry(UFCKeypadWindow)
install_split_land_cv_setup(UFCKeypadWindow)
install_cold_ui_fixups(UFCKeypadWindow)
w = UFCKeypadWindow()
startup = install_startup_overlay(w, STARTUP_STYLE_UFC_BIT)
assert isinstance(startup, UFCBitStartupOverlay)
s = SettingsWindow(w)
combo = attach_startup_style_settings(s)
assert combo is not None
print(f"[3] CONSTRUCT OK  (local cells={len(w.cells)}, morse cells={len(w._morse_cells)}, light displays={len(w._light_displays)})")

# ---- 3a. IFEI RPM fallback / forced injection / state polling ----
rx = DCSBIOSReceiver()
rx._use_fallback_addresses()
assert rx.parser.address_to_field.get(0x749E) == ("IFEI_RPM_L", 3)
assert rx.parser.address_to_field.get(0x74A2) == ("IFEI_RPM_R", 3)
assert _decode_rpm_state(rx.parser, IFEI_RPM_L_ADDR, 3) == "0"
rx.parser.state[IFEI_RPM_R_ADDR:IFEI_RPM_R_ADDR + 3] = b"075"
assert _decode_rpm_state(rx.parser, IFEI_RPM_R_ADDR, 3) == "075"
rx_external = DCSBIOSReceiver()
rx_external.parser.inject_address_map({0x7424: ("UFC_COMM1_DISPLAY", 2)})
rx_external.parser.address_to_field.pop(0x749E, None)
rx_external.parser.address_to_field.pop(0x74A2, None)
rx_external._addr_map_built = True
rx_external._learn_addresses()
assert rx_external.parser.address_to_field.get(0x749E) == ("IFEI_RPM_L", 3)
assert rx_external.parser.address_to_field.get(0x74A2) == ("IFEI_RPM_R", 3)
print("[3a] IFEI RPM OK  (forced injection + state polling)")

# ---- 3b. GUI 事件路径 ----
w.show()
app.processEvents()
startup.update()
app.processEvents()
startup.on_dcs_signal("ufc_brightness", "0.5")
app.processEvents()
anime = install_startup_overlay(w, STARTUP_STYLE_ANIME_MILLENNIUM)
assert isinstance(anime, AnimeMillenniumStartupOverlay)
anime.update()
app.processEvents()
anime.on_dcs_signal("ufc_brightness", "0.5")
app.processEvents()
bit = install_startup_overlay(w, STARTUP_STYLE_UFC_BIT)
assert isinstance(bit, UFCBitStartupOverlay)
for p in ["morse_light", "light_control", "select", "cold_start", "local_icp"]:
    w._show_page(p)
    app.processEvents()
w.update()
app.processEvents()
print("[3b] GUI EVENTS OK")

# ---- 4. 页面切换 ----
for p in ["morse_light", "light_control", "select", "cold_start", "local_icp"]:
    w._show_page(p)
    assert w._current_page == p, p
print("[4] PAGE SWITCH OK")

# ---- 4b. 独立 setup 页 + LAND/CV 分开 + 样式统一 + RESET 保留步数 ----
w.dcs_bios.latest.clear()
w._cold_reset_session_state("verify start")
w._show_page("local_icp")
w._cold_on_dcs_signal("UFC_SCRATCHPAD_STRING_1_DISPLAY", "")
assert w._current_page == "cold_start"
assert w._cold_detected_mode == CS.STARTUP_MODE_UNKNOWN
w._cold_refresh_ui()
assert not w._cold_cells[CDE.P_DAY].isVisible()
assert not w._cold_cells[CDE.P_NIGHT].isVisible()
assert not w._cold_cells[CSS.P_LAND].isVisible()
assert not w._cold_cells[CSS.P_CV].isVisible()
assert not w._cold_cells[CDE.P_START].isVisible()

w._update_display("left_engine_rpm", "  0")
assert w._cold_detected_mode == CS.STARTUP_MODE_UNKNOWN
w._cold_first_mode_decided = False
w._update_display("right_engine_rpm", "  0")
assert w._current_page == "cold_start"
assert w._cold_last_action == "SELECT SETUP"
lines = w._cold_status_lines()
assert lines["title"] == "COLD START SETUP"
assert "L 000.0%" in lines["rpm"] and "R 000.0%" in lines["rpm"]
assert set(w._cold_status_cells.keys()) == {"title", "rpm", "step", "hint", "status"}
assert all(isinstance(v, QLabel) for v in w._cold_status_cells.values())
assert "#d7f3df" not in w._cold_status_cells["title"].styleSheet().lower()
assert "rgb(0" in w._cold_status_cells["title"].styleSheet().lower()
assert set(w._cold_cells.keys()) == {CDE.P_DAY, CDE.P_NIGHT, CSS.P_LAND, CSS.P_CV, CDE.P_START, CDE.P_RESET}

# Four setup buttons are centered as one row in the 1024 px design layout.
setup_buttons = [w._cold_cells[CDE.P_DAY], w._cold_cells[CDE.P_NIGHT], w._cold_cells[CSS.P_LAND], w._cold_cells[CSS.P_CV]]
row_left = min(c.geometry().x() for c in setup_buttons)
row_right = max(c.geometry().x() + c.geometry().width() for c in setup_buttons)
assert abs((row_left + row_right) / 2 - 512) <= 4, (row_left, row_right)

steps = w._cold_step_list()
assert steps[2][1] == "timer" and steps[2][2] == CDE.APU_TO_RIGHT_CRANK_MS
assert not any(step[0] == "DISPLAY MODE" for step in steps)
assert not any(label in [step[0] for step in steps] for label in ["PAUSE", "SKIP", "ABORT"])
w._cold_refresh_ui()
assert w._cold_cells[CDE.P_DAY].isVisible()
assert w._cold_cells[CDE.P_NIGHT].isVisible()
assert w._cold_cells[CSS.P_LAND].isVisible()
assert w._cold_cells[CSS.P_CV].isVisible()
assert w._cold_cells[CDE.P_START].isVisible()
assert not w._cold_cells[CDE.P_RESET].isVisible()

w.on_cell_click(CDE.P_NIGHT)
assert w._cold_display_mode == "night"
w.on_cell_click(CSS.P_LAND)
assert w._cold_profile == "land"
w.on_cell_click(CSS.P_CV)
assert w._cold_profile == "carrier"
w.on_cell_click(CDE.P_START)
assert w._cold_entry_stage == CDE.ENTRY_SETUP
assert w._cold_entry_confirm_count == 1
w.on_cell_click(CDE.P_START)
assert w._cold_entry_stage == CDE.ENTRY_CHECKLIST
assert w._cold_last_action == "COLD START READY"
w._cold_refresh_ui()
assert not w._cold_cells[CDE.P_DAY].isVisible()
assert not w._cold_cells[CDE.P_NIGHT].isVisible()
assert not w._cold_cells[CSS.P_LAND].isVisible()
assert not w._cold_cells[CSS.P_CV].isVisible()
assert w._cold_cells[CDE.P_START].isVisible()
assert w._cold_cells[CDE.P_RESET].isVisible()

w.on_cell_click(CDE.P_START)
assert w._cold_state == "armed"
w.on_cell_click(CDE.P_START)
assert w._cold_state in ("running", "wait_user")
# Jump to the APU READY user step to verify reset/setup preserves the actual step title.
w._cold_step_index = 3
w._cold_state = "wait_user"
saved_step = w._cold_step_index
w.on_cell_click(CDE.P_RESET)
assert w._cold_entry_stage == CDE.ENTRY_CHECKLIST
assert w._cold_step_index == saved_step
assert w._cold_last_action == "RESET 1/2"
w.on_cell_click(CDE.P_RESET)
assert w._cold_entry_stage == CDE.ENTRY_SETUP
assert w._cold_step_index == saved_step
assert w._cold_setup_preserve_progress is True
assert "STEP KEPT" in w._cold_status_lines()["status"]
w.on_cell_click(CDE.P_START)
w.on_cell_click(CDE.P_START)
assert w._cold_entry_stage == CDE.ENTRY_CHECKLIST
assert w._cold_step_index == saved_step
assert w._cold_last_action == "APU READY?"
assert "CONFIRM SETUP" not in w._cold_status_lines()["step"]
print("[4b] COLD UI OK  (green labels, centered setup buttons, reset keeps real step)")

# ---- 4c. 冷启动配置键 + battery ON 修正 ----
cs_cfg = CS._merged_config()
required_controls = {
    "battery_on", "apu_start", "right_engine_crank", "left_engine_crank", "apu_off",
    "canopy_close", "bleed_air_cycle", "trim_reset", "fcs_reset", "ecm_receive",
    "ins_land", "ins_carrier", "display_lddi", "display_rddi", "display_ampcd", "display_hud",
}
assert required_controls.issubset(set(cs_cfg["cold_start_controls"].keys()))
assert "sequence" in cs_cfg["cold_start_controls"]["bleed_air_cycle"]
assert cs_cfg.get("cold_start_left_rpm_threshold") == 60
battery_entries = w._cold_entries_from_config("battery_on")
assert battery_entries and battery_entries[0]["id"] == "BATTERY_SW" and battery_entries[0]["value"] == 2
print("[4c] COLD START CONFIG OK  (battery ON value forced to 2)")

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
assert text_to_morse("SOS") == "... --- ..."
assert text_to_morse("A") == ".-"
assert text_to_morse(" ") == "/"
assert " " in text_to_morse("SOS A")
print("[6] MORSE OK")

# ---- 7. 亮度同步 ----
import ufc.colors as C
w._brightness = 0.5
w._refresh_brightness()
assert C._CURRENT_BRIGHTNESS == 0.5
print(f"[7] BRIGHTNESS SYNC OK  ({C._CURRENT_BRIGHTNESS})")

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
