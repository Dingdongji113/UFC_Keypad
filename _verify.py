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

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# ---- 1. 编译 ----
mods = [
    "main.py", "main_safe.py",
    f"{PKG_PATH}/__init__.py", f"{PKG_PATH}/constants.py", f"{PKG_PATH}/crashlog.py", f"{PKG_PATH}/config.py",
    f"{PKG_PATH}/fonts.py", f"{PKG_PATH}/morse.py", f"{PKG_PATH}/colors.py", f"{PKG_PATH}/dcs_bios.py",
    f"{PKG_PATH}/input.py", f"{PKG_PATH}/widgets.py", f"{PKG_PATH}/startup.py", f"{PKG_PATH}/windowing.py",
    f"{PKG_PATH}/ifei_rpm.py", f"{PKG_PATH}/realtime_rpm.py", f"{PKG_PATH}/cold_start.py",
    f"{PKG_PATH}/cold_direct_entry.py", f"{PKG_PATH}/cold_setup_split.py", f"{PKG_PATH}/cold_ui_fixups.py",
    f"{PKG_PATH}/cv_trim_auto.py", f"{PKG_PATH}/direct_command_fixups.py", f"{PKG_PATH}/ui.py",
]
for m in mods:
    py_compile.compile(m, doraise=True)
print(f"[1] COMPILE OK ({len(mods)} modules)")

# ---- 2. 导入 ----
for name in [
    "constants", "crashlog", "config", "fonts", "morse", "colors", "dcs_bios", "input", "widgets",
    "startup", "windowing", "ifei_rpm", "realtime_rpm", "cold_start", "cold_direct_entry",
    "cold_setup_split", "cold_ui_fixups", "cv_trim_auto", "direct_command_fixups", "ui",
]:
    importlib.import_module("ufc." + name)
print("[2] IMPORT OK")

from PyQt6.QtWidgets import QApplication, QLabel
from PyQt6.QtCore import QPointF, Qt, QEventLoop, QTimer
from PyQt6.QtGui import QMouseEvent

app = QApplication.instance() or QApplication(sys.argv)

from ufc.ui import UFCKeypadWindow, SettingsWindow
from ufc.dcs_bios import DCSBIOSReceiver
from ufc.ifei_rpm import install_ifei_rpm_fallback, IFEI_RPM_L_ADDR, IFEI_RPM_R_ADDR
from ufc.realtime_rpm import install_realtime_rpm_callbacks, _decode_rpm_state
import ufc.cold_start as CS
import ufc.cold_direct_entry as CDE
import ufc.cold_setup_split as CSS
import ufc.direct_command_fixups as DCF
from ufc.cold_start import patch_cold_start
from ufc.cold_direct_entry import install_cold_direct_entry
from ufc.cold_setup_split import install_split_land_cv_setup
from ufc.cold_ui_fixups import install_cold_ui_fixups
from ufc.cv_trim_auto import install_cv_trim_automation, cv_trim_target_deg, _RECEIVER
from ufc.direct_command_fixups import install_direct_command_fixups
from ufc.startup import STARTUP_STYLE_UFC_BIT, UFCBitStartupOverlay, attach_startup_style_settings, install_startup_overlay

install_ifei_rpm_fallback()
install_realtime_rpm_callbacks()
patch_cold_start(UFCKeypadWindow)
install_cold_direct_entry(UFCKeypadWindow)
install_split_land_cv_setup(UFCKeypadWindow)
install_cold_ui_fixups(UFCKeypadWindow)
install_cv_trim_automation(UFCKeypadWindow)
install_direct_command_fixups(UFCKeypadWindow)

w = UFCKeypadWindow()
startup = install_startup_overlay(w, STARTUP_STYLE_UFC_BIT)
assert isinstance(startup, UFCBitStartupOverlay)
s = SettingsWindow(w)
assert attach_startup_style_settings(s) is not None
print("[3] CONSTRUCT OK")

# ---- 3a. IFEI/RPM 地址和轮询 ----
rx = DCSBIOSReceiver()
rx._use_fallback_addresses()
assert rx.parser.address_to_field.get(0x749E) == ("IFEI_RPM_L", 3)
assert rx.parser.address_to_field.get(0x74A2) == ("IFEI_RPM_R", 3)
assert _decode_rpm_state(rx.parser, IFEI_RPM_L_ADDR, 3) == "0"
rx.parser.state[IFEI_RPM_R_ADDR:IFEI_RPM_R_ADDR + 3] = b"075"
assert _decode_rpm_state(rx.parser, IFEI_RPM_R_ADDR, 3) == "075"
print("[3a] IFEI RPM OK")

# ---- 4. 冷启动页面 / 步骤 ----
w.show()
app.processEvents()
for p in ["morse_light", "light_control", "select", "cold_start", "local_icp"]:
    w._show_page(p)
    app.processEvents()
    assert w._current_page == p
print("[4] PAGE SWITCH OK")

w.dcs_bios.latest.clear()
w._cold_reset_session_state("verify start")
w._show_page("local_icp")
w._cold_on_dcs_signal("UFC_SCRATCHPAD_STRING_1_DISPLAY", "")
assert w._current_page == "cold_start"
assert w._cold_detected_mode == CS.STARTUP_MODE_UNKNOWN
w._cold_refresh_ui()
assert not w._cold_cells[CDE.P_DAY].isVisible()
assert not w._cold_cells[CDE.P_START].isVisible()

w._update_display("left_engine_rpm", "  0")
w._cold_first_mode_decided = False
w._update_display("right_engine_rpm", "  0")
w._cold_refresh_ui()
assert w._cold_cells[CDE.P_DAY].isVisible()
assert w._cold_cells[CDE.P_NIGHT].isVisible()
assert w._cold_cells[CSS.P_LAND].isVisible()
assert w._cold_cells[CSS.P_CV].isVisible()
assert all(isinstance(v, QLabel) for v in w._cold_status_cells.values())

w._cold_profile = "land"
land_steps = w._cold_step_list()
land_names = [s[0] for s in land_steps]
assert len(land_steps) == 22
assert land_names[0] == "EJECT SAFE OFF"
assert land_names[11:14] == ["APU OFF", "BRIGHTNESS", "CANOPY CLOSE"]
assert land_names[16:19] == ["FCS / RWR", "ECM REC", "MANUAL SETUP"]
assert "IFF MANUAL" not in land_names
assert "CAT TRIM" not in land_names
assert land_names[-1] == "COMPLETE"

w._cold_profile = "carrier"
cv_steps = w._cold_step_list()
cv_names = [s[0] for s in cv_steps]
assert len(cv_steps) == 23
assert cv_names[-2:] == ["CAT TRIM", "COMPLETE"]
assert cv_steps[-2][1] == "cat_trim_auto"
assert w._cv_trim_target_deg(44000) == 16.0
assert w._cv_trim_target_deg(45000) == 17.0
assert w._cv_trim_target_deg(48000) == 17.0
assert w._cv_trim_target_deg(49000) == 19.0
assert cv_trim_target_deg(50000) == 19.0
print("[4b] COLD STEP LIST OK")

# ---- 4c. 控制值 / 直控 fallback / 亮度 / COMPLETE ----
eject_entries = w._cold_entries_from_config("ejection_seat_arm")
assert eject_entries[0] == {"id": "EJECTION_SEAT_ARMED", "value": 1, "delay_ms": 150}
assert eject_entries[1]["bridge"] == "clickable"
assert eject_entries[1]["device"] == 7 and eject_entries[1]["command"] == 3006 and eject_entries[1]["value"] == 1.0
assert w._cold_entries_from_config("battery_on")[0] == {"id": "BATTERY_SW", "value": 2}
ecm_entries = w._cold_entries_from_config("ecm_receive")
assert ecm_entries[0] == {"id": "ECM_MODE_SW", "value": 1, "delay_ms": 150}
assert ecm_entries[1]["bridge"] == "clickable"
assert ecm_entries[1]["device"] == 66 and ecm_entries[1]["command"] == 3001 and ecm_entries[1]["value"] == 0.1

# Verify mixed DCS-BIOS + bridge sequence execution order without sending real UDP.
import ufc.dcs_bios as DB
sent = []
bridge = []
_orig_db_send = DB.send_dcs_bios
_orig_bridge = DCF.send_direct_clickable
try:
    DB.send_dcs_bios = lambda identifier, value: sent.append((identifier, value)) or True
    DCF.send_direct_clickable = lambda device, command, value, **kwargs: bridge.append((device, command, value, kwargs.get("label"))) or True
    w._cold_state = "running"
    w._cold_sequence_token += 1
    token = w._cold_sequence_token
    loop = QEventLoop()
    w._cold_run_sequence_entries("ecm_receive", ecm_entries, 0, token, loop.quit)
    QTimer.singleShot(800, loop.quit)
    loop.exec()
finally:
    DB.send_dcs_bios = _orig_db_send
    DCF.send_direct_clickable = _orig_bridge
assert sent == [("ECM_MODE_SW", 1)]
assert bridge == [(66, 3001, 0.1, "ECM REC")]

w._cold_display_mode = "day"
brightness_ids = [e["id"] for e in w._cold_display_brightness_entries()]
for required_id in [
    "LEFT_DDI_BRT_SELECT", "RIGHT_DDI_BRT_SELECT", "AMPCD_NIGHT_DAY", "HUD_SYM_BRT_SELECT",
    "LEFT_DDI_BRT_CTL", "RIGHT_DDI_BRT_CTL", "AMPCD_BRT_CTL", "HUD_SYM_BRT",
]:
    assert required_id in brightness_ids

_REE = _RECEIVER
_REE.inject_for_test(45000, 17.0)
w._cold_profile = "carrier"
w._cold_state = "running"
w._cold_entry_stage = CDE.ENTRY_CHECKLIST
w._current_page = "cold_start"
w._cold_step_index = [s[0] for s in w._cold_step_list()].index("CAT TRIM")
w._cold_run_next_step()
loop = QEventLoop()
QTimer.singleShot(200, loop.quit)
loop.exec()
assert w._cold_state == "complete" or w._cold_step_index == len(w._cold_step_list()) - 1

w._cold_state = "complete"
w._cold_entry_stage = CDE.ENTRY_CHECKLIST
w._current_page = "cold_start"
w._cold_refresh_ui()
assert w._cold_cells[CDE.P_START].label.text() == "COMPLETE"
w.on_cell_click(CDE.P_START)
assert w._current_page == "local_icp"
print("[4c] COMMANDS / DIRECT BRIDGE / CV TRIM / COMPLETE OK")

# ---- 5. UFCCell 基本点击 ----
import ufc.widgets as W
click_sent = []
_orig_send = W.send_dcs_bios
_orig_release = W._send_release
try:
    W.send_dcs_bios = lambda identifier, value: click_sent.append((identifier, value)) or True
    W._send_release = lambda identifier: click_sent.append((identifier, 0)) or True
    cell = W.UFCCell("1", (1, 1), no_feedback=False)
    press = QMouseEvent(QMouseEvent.Type.MouseButtonPress, QPointF(5, 5), QPointF(5, 5), QPointF(5, 5), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    release = QMouseEvent(QMouseEvent.Type.MouseButtonRelease, QPointF(5, 5), QPointF(5, 5), QPointF(5, 5), Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
    cell.mousePressEvent(press)
    cell.mouseReleaseEvent(release)
    app.processEvents()
    assert click_sent[0] == ("UFC_1", 1)
finally:
    W.send_dcs_bios = _orig_send
    W._send_release = _orig_release
print("[5] UFCCELL CLICK OK")

# ---- 6. 其他轻量检查 ----
from ufc.morse import text_to_morse
assert text_to_morse("SOS") == "... --- ..."
import ufc.colors as C
w._brightness = 0.5
w._refresh_brightness()
assert C._CURRENT_BRIGHTNESS == 0.5
spec = importlib.util.spec_from_file_location("ufc_main", os.path.join(os.getcwd(), "main.py"))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
assert hasattr(mod, "main")

app.quit()
print("\n========== ALL CHECKS PASSED ==========")
