# -*- coding: utf-8 -*-
"""Offscreen regression checks for UFC Keypad."""
import importlib
import os
import py_compile
import sys

from _bootstrap_imports import ensure_ufc_package

PKG_DIR = ensure_ufc_package(os.getcwd())
if PKG_DIR is None:
    raise RuntimeError("Cannot find ufc package")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

modules = [
    "main.py", "main_safe.py", "install_dcs_export_bridge.py", "probe_hornet_bridge.py",
    "ufc/__init__.py", "ufc/constants.py", "ufc/crashlog.py", "ufc/config.py",
    "ufc/fonts.py", "ufc/morse.py", "ufc/colors.py", "ufc/dcs_bios.py",
    "ufc/input.py", "ufc/widgets.py", "ufc/startup.py", "ufc/windowing.py",
    "ufc/ifei_rpm.py", "ufc/realtime_rpm.py", "ufc/cold_start.py",
    "ufc/cold_direct_entry.py", "ufc/cold_setup_split.py", "ufc/cold_ui_fixups.py",
    "ufc/cv_trim_auto.py", "ufc/direct_command_fixups.py", "ufc/hmd_osb_timing.py",
    "ufc/radar_ins_steps.py", "ufc/manual_setup_auto.py", "ufc/cold_lighting_auto.py", "ufc/ui.py",
]
for path in modules:
    py_compile.compile(path, doraise=True)
for name in [
    "constants", "crashlog", "config", "fonts", "morse", "colors", "dcs_bios",
    "input", "widgets", "startup", "windowing", "ifei_rpm", "realtime_rpm",
    "cold_start", "cold_direct_entry", "cold_setup_split", "cold_ui_fixups",
    "cv_trim_auto", "direct_command_fixups", "hmd_osb_timing", "radar_ins_steps",
    "manual_setup_auto", "cold_lighting_auto", "ui",
]:
    importlib.import_module("ufc." + name)
print(f"[1] COMPILE / IMPORT OK ({len(modules)} modules)")

from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtGui import QFontMetrics
from PyQt6.QtWidgets import QApplication

from ufc.ui import UFCKeypadWindow
from ufc.dcs_bios import DCSBIOSReceiver
from ufc.cold_start import patch_cold_start
from ufc.cold_direct_entry import install_cold_direct_entry
from ufc.cold_direct_entry import P_START
from ufc.cold_setup_split import install_split_land_cv_setup
from ufc.cold_ui_fixups import install_cold_ui_fixups
from ufc.cv_trim_auto import install_cv_trim_automation
from ufc.direct_command_fixups import install_direct_command_fixups
from ufc.hmd_osb_timing import install_hmd_osb_timing_fix
from ufc.radar_ins_steps import install_radar_ins_step_split
from ufc.manual_setup_auto import install_manual_setup_automation
from ufc.cold_lighting_auto import install_cold_lighting_automation
import ufc.cv_trim_auto as CVA
import ufc.dcs_bios as DB
import ufc.manual_setup_auto as MSA
import ufc.cold_lighting_auto as CLA
import ufc.ui as UI


def wait_ms(milliseconds):
    loop = QEventLoop()
    QTimer.singleShot(milliseconds, loop.quit)
    loop.exec()


app = QApplication.instance() or QApplication(sys.argv)
cv_receiver_start = CVA._RECEIVER.start
CVA._RECEIVER.start = lambda: None
patch_cold_start(UFCKeypadWindow)
install_cold_direct_entry(UFCKeypadWindow)
install_split_land_cv_setup(UFCKeypadWindow)
install_cold_ui_fixups(UFCKeypadWindow)
install_cv_trim_automation(UFCKeypadWindow)
install_direct_command_fixups(UFCKeypadWindow)
install_hmd_osb_timing_fix(UFCKeypadWindow)
install_radar_ins_step_split(UFCKeypadWindow)
install_manual_setup_automation(UFCKeypadWindow)
install_cold_lighting_automation(UFCKeypadWindow)
CVA._RECEIVER.start = cv_receiver_start

# Do not attach hooks or UDP listeners to a concurrently running DCS session.
UI._start_mouse_hook = lambda: None
UI._stop_mouse_hook = lambda: None
UI._register_native_touch = lambda _hwnd: False
UI._unregister_native_touch = lambda _hwnd: True
receiver_start, receiver_stop = DCSBIOSReceiver.start, DCSBIOSReceiver.stop
DCSBIOSReceiver.start = lambda self: None
DCSBIOSReceiver.stop = lambda self: None
w = UFCKeypadWindow()
w._apply_noactivate_style = lambda: None
DCSBIOSReceiver.start, DCSBIOSReceiver.stop = receiver_start, receiver_stop
print("[2] OFFSCREEN CONSTRUCT OK")

# Primary action text: setup CONFIRM, checklist step 1 START, step 2+ CONTINUE.
w._cold_first_mode_decided = True
w._cold_detected_mode = "cold"
w._cold_entry_stage = "setup"
w._cold_state = "idle"
w._cold_step_index = -1
w._cold_refresh_ui()
primary_button = w._cold_cells[P_START]
assert primary_button.label.text() == "CONFIRM"
w._cold_entry_stage = "checklist"
w._cold_step_index = 0
w._cold_refresh_ui()
assert primary_button.label.text() == "START"
w._cold_step_index = 1
w._cold_refresh_ui()
assert primary_button.label.text() == "CONTINUE"
assert QFontMetrics(primary_button.label.font()).horizontalAdvance("CONTINUE") < primary_button.width() - 20
w._cold_state = "complete"
w._cold_refresh_ui()
assert primary_button.label.text() == "COMPLETE"
print("[2a] CONFIRM / START / CONTINUE LABELS FIT")

# Real DCS-BIOS output definitions used by the live center displays.
rx = DCSBIOSReceiver()
rx._use_fallback_addresses()
assert rx.parser.address_to_field[0x7468] == ("IFEI_BINGO", 6)
assert rx.parser.analog_addresses[0x7518] == "radalt_min_ptr"
assert rx.parser.analog_addresses[0x751C] == "radalt_off_flag"

w._cold_profile = "land"
land = w._cold_step_list()
land_names = [step[0] for step in land]
assert len(land) == 27
assert land_names[11:13] == ["LIGHTS / ANTI-SKID", "APU OFF / FLAPS AUTO"]
assert land_names[18:24] == [
    "ECM REC", "RADAR / INS", "AMPCD PB19", "SAI UNLOCK", "RADALT MIN", "BINGO FUEL",
]
assert land_names[24:] == ["LOCAL ICP", "HMD CAL / IFA", "COMPLETE"]
assert [step[1] for step in land[19:24]] == [
    "radar_ins_confirm", "ampcd_pb19_confirm", "manual_sai_unlock",
    "manual_radalt_direct", "manual_bingo_direct",
]
w._cold_profile = "carrier"
carrier_names = [step[0] for step in w._cold_step_list()]
assert len(carrier_names) == 28
assert carrier_names[19:28] == [
    "RADAR / INS", "AMPCD PB19", "SAI UNLOCK", "RADALT MIN", "BINGO FUEL",
    "LOCAL ICP", "CAT TRIM", "HMD CAL / IFA", "COMPLETE",
]
print("[3] 27/28-STEP ORDER OK")

# Post-engine lighting: external master is untouched and 70% uses BRT=100%.
assert CLA.LIGHT_BRIGHTNESS_VALUE == 45875
w._cold_profile = "land"
day_land = w._cold_lighting_entries("day", "land")
assert day_land == [
    {"id": "STROBE_SW", "value": 0, "delay_ms": 120},
    {"id": "ANTI_SKID_SW", "value": 1, "delay_ms": 120},
]
day_cv = w._cold_lighting_entries("day", "carrier")
assert day_cv[-1]["id"] == "ANTI_SKID_SW" and day_cv[-1]["value"] == 0
night = w._cold_lighting_entries("night", "land", flood_enabled=True, chart_enabled=False)
night_values = {entry["id"]: entry["value"] for entry in night}
assert night_values == {
    "STROBE_SW": 0,
    "LDG_TAXI_SW": 1,
    "FORMATION_DIMMER": 45875,
    "POSITION_DIMMER": 45875,
    "CONSOLES_DIMMER": 45875,
    "INST_PNL_DIMMER": 45875,
    "WARN_CAUTION_DIMMER": 45875,
    "COCKKPIT_LIGHT_MODE_SW": 1,
    "FLOOD_DIMMER": 45875,
    "CHART_DIMMER": 0,
    "ANTI_SKID_SW": 1,
}
assert not any("MASTER" in entry["id"] for entry in day_land + night)

# NIGHT asks FLOOD then CHART using the cold-page NO/YES touch controls.
w._cold_display_mode = "night"
w._cold_profile = "land"
w._current_page = "cold_start"
w._cold_entry_stage = "checklist"
w._cold_state = "running"
w._cold_sequence_token += 1
w._cold_step_index = land_names.index("LIGHTS / ANTI-SKID")
captured_lighting = []
original_sequence_runner = w._cold_run_sequence_entries
w._cold_run_sequence_entries = lambda _key, entries, _index, _token, _done: captured_lighting.extend(entries)
try:
    w._cold_run_next_step()
    assert w._cold_state == "wait_user" and w._cold_lighting_phase == "ask_flood"
    assert not w._cold_lighting_cells["yes"].isHidden()
    assert w._cold_lighting_cells["question"]._var_text == "FLOOD LIGHT?"
    question_cell = w._cold_lighting_cells["question"]
    question_metrics = QFontMetrics(question_cell._var_font)
    assert question_metrics.horizontalAdvance("FLOOD LIGHT?") < question_cell.width() - 12
    assert question_metrics.horizontalAdvance("CHART LIGHT?") < question_cell.width() - 12
    w._cold_handle_click(CLA.P_LIGHT_YES)
    assert w._cold_lighting_phase == "ask_chart"
    old_index = w._cold_step_index
    w._cold_arm_or_continue()
    assert w._cold_step_index == old_index and w._cold_state == "wait_user"
    w._cold_handle_click(CLA.P_LIGHT_NO)
finally:
    w._cold_run_sequence_entries = original_sequence_runner
assert {entry["id"]: entry["value"] for entry in captured_lighting}["FLOOD_DIMMER"] == 45875
assert {entry["id"]: entry["value"] for entry in captured_lighting}["CHART_DIMMER"] == 0
print("[3a] POST-ENGINE LIGHTING / ANTI-SKID / PROMPTS OK")

# FLAPS AUTO values and PB19's exactly-one-channel contract.
flaps = w._cold_entries_from_config("apu_off_flaps_auto")
assert flaps[-2] == {"id": "FLAP_SW", "value": 0, "delay_ms": 150}
assert flaps[-1]["device"] == 2 and flaps[-1]["command"] == 3007
assert flaps[-1]["value"] == 1.0 and flaps[-1]["label"] == "FLAPS AUTO"
pb19 = w._cold_entries_from_config("ampcd_pb19")
assert pb19 == [
    {"id": "AMPCD_PB_19", "value": 1, "delay_ms": 120},
    {"id": "AMPCD_PB_19", "value": 0, "delay_ms": 120},
]
assert not any("bridge" in entry for entry in pb19)

# SAI uses device SetCommand, not a clickable-action approximation.
payloads = []
orig_payload = CVA._send_bridge_payload
CVA._send_bridge_payload = lambda payload: payloads.append(payload) or True
try:
    assert CVA.send_direct_set_command(32, 3005, -0.3, label="SAI", hold_ms=300, release_value=0.0)
finally:
    CVA._send_bridge_payload = orig_payload
assert payloads == [{
    "type": "set_command", "device": 32, "command": 3005, "value": -0.3,
    "label": "SAI", "hold_ms": 300, "release_value": 0.0,
}]
lua = open("dcs_export/UFC_Keypad_CVTrim.lua", encoding="utf-8").read()
assert "handle_set_command" in lua and "p.device:SetCommand(p.command, p.value)" in lua
print("[4] FLAPS / PB19 / SAI CHANNELS OK")

orig_send = MSA.dcs_bios.send_dcs_bios
orig_bridge = MSA.send_direct_clickable
orig_set_command = MSA.send_direct_set_command
try:
    w._cold_profile = "land"
    w._current_page = "cold_start"

    def enter(kind):
        w._cold_state = "running"
        w._cold_entry_stage = "checklist"
        w._cold_sequence_token += 1
        title = "RADALT MIN" if kind == "radalt" else "BINGO FUEL"
        w._cold_step_index = [step[0] for step in w._cold_step_list()].index(title)
        w._manual_enter_direct(kind)
        assert w._manual_direct_context_valid()

    # Center cell is real telemetry only, including explicit missing/off states.
    enter("radalt")
    w.dcs_bios.latest.clear()
    assert w._manual_display_text() == "--- FT"
    w.dcs_bios.latest.update({"radalt_off_flag": "1", "radalt_min_ptr": "0.5"})
    assert w._manual_display_text() == "OFF"
    w.dcs_bios.latest.update({"radalt_off_flag": "0", "radalt_min_ptr": "0.323448"})
    assert w._manual_display_text() == "200 FT"
    enter("bingo")
    w.dcs_bios.latest.clear()
    assert w._manual_display_text() == "---- LB"
    w.dcs_bios.latest["IFEI_BINGO"] = " 3400\x00"
    assert w._manual_display_text() == "3400 LB"

    # One click means one pulse; a successful primary path never duplicates via bridge.
    enter("radalt")
    primary, bridge = [], []
    MSA.dcs_bios.send_dcs_bios = lambda ident, value: primary.append((ident, value)) or True
    MSA.send_direct_clickable = lambda *args, **kwargs: bridge.append((args, kwargs)) or True
    w._manual_control_press(MSA.P_MANUAL_PLUS)
    w._manual_control_release(MSA.P_MANUAL_PLUS)
    wait_ms(320)
    assert primary == [("RADALT_HEIGHT", f"+{MSA.RADALT_DIRECT_DCS_STEP}")]
    assert bridge == []

    # Primary failure invokes exactly one bridge pulse, never both successful channels.
    enter("radalt")
    primary.clear(); bridge.clear()
    MSA.dcs_bios.send_dcs_bios = lambda ident, value: primary.append((ident, value)) or False
    w._manual_control_press(MSA.P_MANUAL_MINUS)
    w._manual_control_release(MSA.P_MANUAL_MINUS)
    assert primary == [("RADALT_HEIGHT", f"-{MSA.RADALT_DIRECT_DCS_STEP}")]
    assert len(bridge) == 1 and bridge[0][0][2] == -MSA.RADALT_DIRECT_BRIDGE_STEP

    # Hold repeats after 250 ms, roughly every 100 ms, and release stops immediately.
    enter("radalt")
    pulses = []
    MSA.dcs_bios.send_dcs_bios = lambda ident, value: pulses.append((ident, value)) or True
    w._manual_control_press(MSA.P_MANUAL_PLUS)
    wait_ms(475)
    w._manual_control_release(MSA.P_MANUAL_PLUS)
    count_at_release = len(pulses)
    assert count_at_release >= 3
    wait_ms(250)
    assert len(pulses) == count_at_release

    # Page changes invalidate and stop an active hold.
    enter("radalt")
    pulses.clear()
    w._manual_control_press(MSA.P_MANUAL_PLUS)
    w._show_page("local_icp")
    count_at_page_change = len(pulses)
    wait_ms(350)
    assert len(pulses) == count_at_page_change

    # Reset/disconnect and sequence-token changes also cancel pending repeats.
    w._show_page("cold_start")
    enter("radalt")
    pulses.clear()
    w._manual_control_press(MSA.P_MANUAL_PLUS)
    w._cold_reset_session_state("DCS-BIOS TIMEOUT")
    count_at_reset = len(pulses)
    wait_ms(350)
    assert len(pulses) == count_at_reset

    w._show_page("cold_start")
    enter("radalt")
    pulses.clear()
    w._manual_control_press(MSA.P_MANUAL_PLUS)
    w._cold_sequence_token += 1
    count_at_token_change = len(pulses)
    wait_ms(350)
    assert len(pulses) == count_at_token_change

    # BINGO click has one DCS press/release and no bridge on primary success.
    w._show_page("cold_start")
    enter("bingo")
    primary.clear(); bridge.clear()
    MSA.dcs_bios.send_dcs_bios = lambda ident, value: primary.append((ident, value)) or True
    w._manual_control_press(MSA.P_MANUAL_MINUS)
    w._manual_control_release(MSA.P_MANUAL_MINUS)
    wait_ms(MSA.BINGO_PRESS_MS + 30)
    assert primary == [("IFEI_DWN_BTN", 1), ("IFEI_DWN_BTN", 0)]
    assert bridge == []

    # Right is UP, hold repeats complete clicks, and release stops the repeat.
    enter("bingo")
    primary.clear()
    w._manual_control_press(MSA.P_MANUAL_PLUS)
    wait_ms(375)
    w._manual_control_release(MSA.P_MANUAL_PLUS)
    wait_ms(MSA.BINGO_PRESS_MS + 20)
    count_at_bingo_release = len(primary)
    assert count_at_bingo_release >= 4
    assert all(primary[i:i + 2] == [("IFEI_UP_BTN", 1), ("IFEI_UP_BTN", 0)]
               for i in range(0, len(primary), 2))
    wait_ms(200)
    assert len(primary) == count_at_bingo_release

    # A failed BINGO primary press falls back once without a DCS release copy.
    enter("bingo")
    primary.clear(); bridge.clear()
    MSA.dcs_bios.send_dcs_bios = lambda ident, value: primary.append((ident, value)) or False
    w._manual_control_press(MSA.P_MANUAL_PLUS)
    w._manual_control_release(MSA.P_MANUAL_PLUS)
    assert primary == [("IFEI_UP_BTN", 1)]
    assert len(bridge) == 1 and bridge[0][0][1] == 3003

    # START confirms and advances; it does not regulate toward a local target.
    enter("radalt")
    primary.clear(); bridge.clear()
    old_index = w._cold_step_index
    w._cold_arm_or_continue()
    assert w._cold_step_index == old_index + 1
    assert w._cold_manual_phase == "bingo_direct"
    assert primary == [] and bridge == []

    # Dedicated SAI command executes once, then waits for manual confirmation.
    w._cold_state = "running"
    w._cold_sequence_token += 1
    w._cold_step_index = [step[0] for step in w._cold_step_list()].index("SAI UNLOCK")
    sai = []
    MSA.send_direct_set_command = lambda *args, **kwargs: sai.append((args, kwargs)) or True
    w._manual_run_sai_unlock()
    wait_ms(MSA.SAI_ROTATE_HOLD_MS + MSA.SAI_ROTATE_SETTLE_MS + 30)
    assert len(sai) == 1 and sai[0][0] == (32, 3005, MSA.SAI_ROTATE_EXT_VALUE)
    assert w._cold_state == "wait_user" and w._cold_manual_phase == "sai_confirm"
finally:
    MSA.dcs_bios.send_dcs_bios = orig_send
    MSA.send_direct_clickable = orig_bridge
    MSA.send_direct_set_command = orig_set_command
print("[5] DIRECT TOUCH / HOLD / FEEDBACK / SAFETY OK")

# HMD timing and ordered OSB regression remains intact.
assert CVA.RDDI_OSB_INTERVAL_MS == 3000
sent = []
orig_async = w._cold_send_configured_async
orig_timer = CVA.QTimer.singleShot
try:
    w._cold_send_configured_async = lambda key, done: sent.append(key) or done()
    CVA.QTimer.singleShot = lambda _ms, callback: callback()
    w._cold_profile = "carrier"
    w._cold_display_mode = "night"
    w._cold_state = "running"
    w._cold_step_index = [step[0] for step in w._cold_step_list()].index("HMD CAL / IFA")
    w._cold_run_next_step()
finally:
    w._cold_send_configured_async = orig_async
    CVA.QTimer.singleShot = orig_timer
assert sent == [
    "hmd_night", "ins_ifa", "right_ddi_pb18", "right_ddi_pb18",
    "right_ddi_pb03", "right_ddi_pb20",
]
assert w._cold_state == "wait_user"
print("[6] HMD ORDER OK")

# Closing the window while held must invalidate every pending repeat callback.
w._show_page("cold_start")
w._cold_profile = "land"
w._cold_entry_stage = "checklist"
w._cold_state = "running"
w._cold_sequence_token += 1
w._cold_step_index = [step[0] for step in w._cold_step_list()].index("RADALT MIN")
w._manual_enter_direct("radalt")
closing_pulses = []
orig_close_send = MSA.dcs_bios.send_dcs_bios
MSA.dcs_bios.send_dcs_bios = lambda ident, value: closing_pulses.append((ident, value)) or True
w._manual_control_press(MSA.P_MANUAL_PLUS)
w.close()
app.processEvents()
count_at_close = len(closing_pulses)
wait_ms(350)
assert len(closing_pulses) == count_at_close
MSA.dcs_bios.send_dcs_bios = orig_close_send
app.quit()
print("========== ALL CHECKS PASSED ==========")
