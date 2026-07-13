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
    "ufc/cv_trim_auto.py", "ufc/cv_trim_two_stage.py", "ufc/weight_trim.py",
    "ufc/asymmetric_launch_trim.py", "ufc/direct_command_fixups.py", "ufc/hmd_osb_timing.py",
    "ufc/radar_ins_steps.py", "ufc/manual_setup_auto.py", "ufc/cold_lighting_auto.py",
    "ufc/cold_control_check.py", "ufc/startup_rpm_guard.py", "ufc/light_flash_modes.py",
    "ufc/cold_prompt_polish.py", "ufc/system4_mapping.py", "ufc/system4_widgets.py",
    "ufc/system4_safety.py", "ufc/system4.py", "ufc/ui.py",
]
for path in modules:
    py_compile.compile(path, doraise=True)
for name in [
    "constants", "crashlog", "config", "fonts", "morse", "colors", "dcs_bios",
    "input", "widgets", "startup", "windowing", "ifei_rpm", "realtime_rpm",
    "cold_start", "cold_direct_entry", "cold_setup_split", "cold_ui_fixups",
    "cv_trim_auto", "cv_trim_two_stage", "weight_trim", "asymmetric_launch_trim",
    "direct_command_fixups", "hmd_osb_timing", "radar_ins_steps",
    "manual_setup_auto", "cold_lighting_auto", "cold_control_check", "startup_rpm_guard",
    "light_flash_modes", "cold_prompt_polish", "system4_mapping",
    "system4_widgets", "system4_safety", "system4", "ui",
]:
    importlib.import_module("ufc." + name)
print(f"[1] COMPILE / IMPORT OK ({len(modules)} modules)")

from PyQt6.QtCore import QEvent, QEventLoop, Qt, QTimer
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
from ufc.cv_trim_two_stage import install_cv_trim_two_stage
from ufc.direct_command_fixups import install_direct_command_fixups
from ufc.hmd_osb_timing import install_hmd_osb_timing_fix
from ufc.radar_ins_steps import install_radar_ins_step_split
from ufc.manual_setup_auto import install_manual_setup_automation
from ufc.cold_lighting_auto import install_cold_lighting_automation
from ufc.cold_control_check import install_cold_control_check
from ufc.startup_rpm_guard import install_startup_rpm_guard
from ufc.light_flash_modes import install_light_flash_modes
from ufc.cold_prompt_polish import install_cold_prompt_polish
from ufc.system4 import install_system4
import ufc.cv_trim_auto as CVA
import ufc.dcs_bios as DB
import ufc.manual_setup_auto as MSA
import ufc.cold_lighting_auto as CLA
import ufc.cold_control_check as CCC
import ufc.system4 as S4
from ufc.system4_mapping import CONTROLS
from ufc.system4_widgets import TouchButton
import ufc.ui as UI


def wait_ms(milliseconds):
    loop = QEventLoop()
    QTimer.singleShot(milliseconds, loop.quit)
    loop.exec()


class FakeTouchEvent:
    """Minimal native-touch event used to verify the explicit button path."""
    def __init__(self, event_type):
        self._event_type = event_type
        self.accepted = False

    def type(self):
        return self._event_type

    def accept(self):
        self.accepted = True


app = QApplication.instance() or QApplication(sys.argv)
cv_receiver_start = CVA._RECEIVER.start
CVA._RECEIVER.start = lambda: None
patch_cold_start(UFCKeypadWindow)
install_cold_direct_entry(UFCKeypadWindow)
install_split_land_cv_setup(UFCKeypadWindow)
install_cold_ui_fixups(UFCKeypadWindow)
install_cv_trim_automation(UFCKeypadWindow)
install_cv_trim_two_stage(UFCKeypadWindow)
install_direct_command_fixups(UFCKeypadWindow)
install_hmd_osb_timing_fix(UFCKeypadWindow)
install_radar_ins_step_split(UFCKeypadWindow)
install_manual_setup_automation(UFCKeypadWindow)
install_cold_lighting_automation(UFCKeypadWindow)
install_cold_control_check(UFCKeypadWindow)
install_startup_rpm_guard(UFCKeypadWindow)
install_light_flash_modes(UFCKeypadWindow)
install_cold_prompt_polish(UFCKeypadWindow)
install_system4(UFCKeypadWindow)
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
assert rx.parser.analog_addresses[0x7574] == "ext_refuel_probe"
assert rx.parser.analog_addresses[0x7586] == "ext_hook"
assert rx.parser.analog_addresses[0x75AE] == "ext_launch_bar"
assert rx.parser.analog_addresses[0x7570] == "ext_wing_folding"
assert CCC.FEEDBACK_TIMEOUT_MS == 25000

w._cold_profile = "land"
land = w._cold_step_list()
land_names = [step[0] for step in land]
assert len(land) == 28
assert land_names[11:18] == [
    "LIGHTS / ANTI-SKID", "APU OFF / FLAPS AUTO", "BRIGHTNESS",
    "CANOPY / OXYGEN", "BLEED AIR", "CONTROL CHECK", "TRIM RESET",
]
assert land_names[19:25] == [
    "ECM REC", "RADAR / INS", "AMPCD PB19", "SAI UNLOCK", "RADALT MIN", "BINGO FUEL",
]
assert land_names[25:] == ["LOCAL ICP", "HMD CAL / IFA", "COMPLETE"]
assert [step[1] for step in land[20:25]] == [
    "radar_ins_confirm", "ampcd_pb19_confirm", "manual_sai_unlock",
    "manual_radalt_direct", "manual_bingo_direct",
]
w._cold_profile = "carrier"
carrier_names = [step[0] for step in w._cold_step_list()]
assert len(carrier_names) == 29
assert carrier_names[20:29] == [
    "RADAR / INS", "AMPCD PB19", "SAI UNLOCK", "RADALT MIN", "BINGO FUEL",
    "LOCAL ICP", "CAT TRIM", "HMD CAL / IFA", "COMPLETE",
]
print("[3] 28/29-STEP ORDER OK")

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

# Optional CONTROL CHECK: exact sequence, progress lock, skip, and ABORT restore.
control_index = [step[0] for step in w._cold_step_list()].index("CONTROL CHECK")
w._cold_step_index = control_index
w._cold_state = "running"
w._cold_sequence_token += 1
w._cold_run_next_step()
assert w._cold_control_phase == "ask" and w._cold_state == "wait_user"
assert w._cold_control_cells["left"].label.text() == "SKIP"
assert w._cold_control_cells["right"].label.text() == "EXECUTE"
assert not w._cold_cells[P_START].isEnabled()

# SKIP advances immediately without running commands.
skip_next = []
original_next = w._cold_run_next_step
w._cold_run_next_step = lambda: skip_next.append(w._cold_step_index)
try:
    before_skip = w._cold_step_index
    w._control_skip()
finally:
    w._cold_run_next_step = original_next
assert skip_next == [before_skip + 1]

orig_control_send = CCC.dcs_bios.send_dcs_bios
orig_axis_send = CCC.send_axis_override
orig_scale = CCC.CONTROL_TIME_SCALE
mechanism_commands = []
axis_commands = []

def fake_control_send(identifier, value):
    mechanism_commands.append((identifier, value))
    if identifier == "PROBE_SW":
        w.dcs_bios.latest["ext_refuel_probe"] = "1" if value == 0 else "0"
    elif identifier == "HOOK_LEVER":
        w.dcs_bios.latest["ext_hook"] = "1" if value == 0 else "0"
    elif identifier == "LAUNCH_BAR_SW":
        w.dcs_bios.latest["ext_launch_bar"] = "1" if value == 1 else "0"
    elif identifier == "WING_FOLD_ROTATE":
        if value == 0:
            w.dcs_bios.latest["ext_wing_folding"] = "1"
        elif value == 2:
            w.dcs_bios.latest["ext_wing_folding"] = "0"
    return True

try:
    CCC.CONTROL_TIME_SCALE = 0.01
    CCC.dcs_bios.send_dcs_bios = fake_control_send
    CCC.send_axis_override = lambda pitch=0, roll=0, rudder=0, **kwargs: axis_commands.append(
        (pitch, roll, rudder, kwargs.get("label"), kwargs.get("duration_ms"))
    ) or True
    w.dcs_bios.latest.update({
        "ext_refuel_probe": "0", "ext_hook": "0",
        "ext_launch_bar": "0", "ext_wing_folding": "0",
    })
    w._cold_step_index = control_index
    w._cold_state = "running"
    w._cold_sequence_token += 1
    w._cold_run_next_step()
    w._cold_handle_click(CCC.P_CONTROL_RIGHT)
    wait_ms(2500)
    assert w._cold_control_phase == "done", (
        w._cold_control_phase, w._cold_control_progress, w._cold_last_action, w._cold_step_detail,
        mechanism_commands, axis_commands,
    )
    assert w._cold_control_progress == 100
    assert w._cold_cells[P_START].isEnabled()
    labels = [item[3] for item in axis_commands]
    assert labels == [
        "STICK FULL AFT", "STICK FULL AFT CENTER",
        "STICK FULL FORWARD", "STICK FULL FORWARD CENTER",
        "STICK FULL LEFT", "STICK FULL LEFT CENTER",
        "STICK FULL RIGHT", "STICK FULL RIGHT CENTER",
        "RUDDER FULL LEFT", "RUDDER FULL LEFT CENTER",
        "RUDDER FULL RIGHT", "RUDDER FULL RIGHT CENTER", "FINAL CENTER",
    ]
    assert axis_commands[0][:3] == (CCC.PITCH_AFT, 0.0, 0.0)
    assert axis_commands[2][:3] == (CCC.PITCH_FORWARD, 0.0, 0.0)
    assert axis_commands[4][:3] == (0.0, CCC.ROLL_LEFT, 0.0)
    assert axis_commands[6][:3] == (0.0, CCC.ROLL_RIGHT, 0.0)
    assert axis_commands[8][:3] == (0.0, 0.0, CCC.RUDDER_LEFT)
    assert axis_commands[10][:3] == (0.0, 0.0, CCC.RUDDER_RIGHT)
    ids = [item[0] for item in mechanism_commands]
    assert ids.index("PROBE_SW") < ids.index("HOOK_LEVER") < ids.index("LAUNCH_BAR_SW") < ids.index("WING_FOLD_PULL")
    wing_commands = [item for item in mechanism_commands if item[0].startswith("WING_FOLD_")]
    assert wing_commands[-5:] == [
        ("WING_FOLD_PULL", 1), ("WING_FOLD_ROTATE", 2),
        ("WING_FOLD_ROTATE", 1), ("WING_FOLD_PULL", 0),
        ("WING_FOLD_ROTATE", 0),
    ]

    # ABORT zeroes progress, forces center, restores all captured initial states,
    # and unlocks CONTINUE only after the restoration check finishes.
    mechanism_commands.clear(); axis_commands.clear()
    w.dcs_bios.latest.update({
        "ext_refuel_probe": "0", "ext_hook": "0",
        "ext_launch_bar": "0", "ext_wing_folding": "0",
    })
    w._cold_step_index = control_index
    w._cold_state = "running"
    w._cold_sequence_token += 1
    w._cold_run_next_step()
    w._cold_handle_click(CCC.P_CONTROL_RIGHT)
    wait_ms(20)
    w._cold_handle_click(CCC.P_CONTROL_LEFT)
    wait_ms(300)
    assert w._cold_control_phase == "aborted"
    assert w._cold_control_progress == 0
    assert axis_commands[-1][:4] == (0.0, 0.0, 0.0, "ABORT CENTER")
    assert w._cold_cells[P_START].isEnabled()
finally:
    CCC.dcs_bios.send_dcs_bios = orig_control_send
    CCC.send_axis_override = orig_axis_send
    CCC.CONTROL_TIME_SCALE = orig_scale
print("[3b] OPTIONAL CONTROL CHECK / PROGRESS / ABORT RESTORE OK")

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
assert "handle_axis" in lua and "apply_axis_override" in lua
axis_payloads = []
orig_payload = CVA._send_bridge_payload
CVA._send_bridge_payload = lambda payload: axis_payloads.append(payload) or True
try:
    assert CVA.send_axis_override(1.0, -1.0, 0.5, duration_ms=3000, label="AXIS TEST")
finally:
    CVA._send_bridge_payload = orig_payload
assert axis_payloads == [{
    "type": "axis", "pitch": 1.0, "roll": -1.0, "rudder": 0.5,
    "duration_ms": 3000, "label": "AXIS TEST",
}]
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

# SYSTEM 4 page registration, mapping, feedback and safety contracts.
assert "SYSTEM 4" in w._select_cells[(201, 3)].label.text()
assert "HUD / NAV / EW" in w._select_cells[(201, 3)].label.text()
assert len(w._system4_controls) == 22
assert CONTROLS["adf"].labels == ("1", "OFF", "2")
assert CONTROLS["adf"].values == (2, 1, 0)
assert not ({"ampcd_brt", "ampcd_mode", "ampcd_sym", "ampcd_cont", "ampcd_gain",
             "pb11", "pb12", "pb13", "pb14", "pb15"} & set(w._system4_controls))
assert (w._system4_controls["rwr_bit"].x()
        < w._system4_controls["rwr_offset"].x()
        < w._system4_controls["rwr_special"].x()
        < w._system4_controls["rwr_display"].x()
        < w._system4_controls["rwr_power"].x())
w._show_page("select")
w.on_cell_click((201, 3))
assert w._current_page == S4.PAGE_4A
assert not w._system4_controls["hud_rej"].isHidden()
w._show_page(S4.PAGE_4B)
assert not w._system4_controls["ecm_mode"].isHidden()

s4_sent = []
orig_s4_send = S4.dcs_bios.send_dcs_bios
S4.dcs_bios.send_dcs_bios = lambda ident, value: s4_sent.append((ident, value)) or True
w._system4_feedback_timer.stop()
w._dcs_disconnected = False
w._system4_safety.set_connected(True)
try:
    # Stable controls enter only declared detents.
    w._system4_controls["hud_rej"].select_index(2)
    assert s4_sent[-1] == ("HUD_SYM_REJ_SW", 2)
    w._system4_controls["hud_alt"].set_state_index(0)
    w._system4_controls["hud_alt"].select_index(1)
    assert s4_sent[-1] == ("HUD_ALT_SW", "TOGGLE")
    count_after_toggle = len(s4_sent)
    w._system4_controls["hud_alt"].select_index(1)
    assert len(s4_sent) == count_after_toggle
    w._system4_controls["ecm_mode"].set_state_index(0)
    w._system4_controls["ecm_mode"].step(1)
    assert w._system4_controls["ecm_mode"].current_index == 1
    assert s4_sent[-1] == ("ECM_MODE_SW", 1)

    # HDG/CRS are DCS-BIOS set-state rockers: 0/2 while held, 1 on release.
    s4_sent.clear()
    rocker = w._system4_controls["hdg"]
    rocker._press(-1); rocker._release(); rocker._press(1); rocker._release()
    assert s4_sent == [
        ("LEFT_DDI_HDG_SW", 0), ("LEFT_DDI_HDG_SW", 1),
        ("LEFT_DDI_HDG_SW", 2), ("LEFT_DDI_HDG_SW", 1),
    ]

    # ADF keeps the visible 1/OFF/2 order while reversing the end commands.
    s4_sent.clear()
    adf = w._system4_controls["adf"]
    adf.set_state_index(1)
    adf.buttons[0].click()
    adf.buttons[2].click()
    assert s4_sent == [("UFC_ADF", 2), ("UFC_ADF", 0)]

    # Ordinary buttons pulse; ALR-67 POWER toggles its latched 0/1 state.
    s4_sent.clear()
    w._system4_controls["rwr_display"].button.click()
    assert s4_sent == [("RWR_DISPLAY_BTN", 1), ("RWR_DISPLAY_BTN", 0)]
    s4_sent.clear()
    power = w._system4_controls["rwr_power"]
    power.set_feedback(0)
    power.button.click()
    power.button.click()
    assert s4_sent == [("RWR_POWER_BTN", 1), ("RWR_POWER_BTN", 0)]
    assert power.button.text() == ""
    for key in ("rwr_display", "rwr_special", "rwr_offset", "rwr_bit"):
        assert w._system4_controls[key].button.text() == ""
        assert w._system4_controls[key].legend_texts() == ("", "")
        assert w._system4_controls[key].button.minimumWidth() == w._system4_controls[key].button.minimumHeight()
    assert power.legend_texts() == ("",)

    # Native touch owns the full press lifecycle. It must not depend on a
    # synthesized mouse event, and every SYSTEM 4 button must use it.
    system4_buttons = []
    for control in w._system4_controls.values():
        system4_buttons.extend(control.findChildren(TouchButton))
    system4_buttons.extend([
        child for child in w.findChildren(TouchButton)
        if getattr(child, "_page", None) in S4.SYSTEM4_PAGES
    ])
    assert system4_buttons and all(
        button.testAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents)
        for button in system4_buttons
    )
    assert all(button.minimumWidth() >= 56 and button.minimumHeight() >= 44
               for control in w._system4_controls.values()
               for button in control.findChildren(TouchButton))
    s4_sent.clear()
    touch_button = w._system4_controls["rwr_display"].button
    begin = FakeTouchEvent(QEvent.Type.TouchBegin)
    end = FakeTouchEvent(QEvent.Type.TouchEnd)
    assert touch_button.event(begin) and begin.accepted
    assert s4_sent == [("RWR_DISPLAY_BTN", 1)]
    assert touch_button.event(end) and end.accepted
    assert s4_sent == [("RWR_DISPLAY_BTN", 1), ("RWR_DISPLAY_BTN", 0)]
    s4_sent.clear()
    power_button = w._system4_controls["rwr_power"].button
    w._system4_controls["rwr_power"].set_feedback(0)
    power_button.event(FakeTouchEvent(QEvent.Type.TouchBegin))
    power_button.event(FakeTouchEvent(QEvent.Type.TouchEnd))
    assert s4_sent == [("RWR_POWER_BTN", 1)]
    s4_sent.clear()
    alt_control = w._system4_controls["hud_alt"]
    alt_control.set_state_index(0)
    alt_button = alt_control.buttons[1]
    alt_button.event(FakeTouchEvent(QEvent.Type.TouchBegin))
    alt_button.event(FakeTouchEvent(QEvent.Type.TouchEnd))
    assert s4_sent == [("HUD_ALT_SW", "TOGGLE")] and alt_control.current_index == 1
    s4_sent.clear()
    alt_button.event(FakeTouchEvent(QEvent.Type.TouchBegin))
    alt_button.event(FakeTouchEvent(QEvent.Type.TouchEnd))
    assert s4_sent == [] and alt_button.isChecked()
    s4_sent.clear()
    held_button = w._system4_ecm_hold.button
    held_button.event(FakeTouchEvent(QEvent.Type.TouchBegin))
    held_button.event(FakeTouchEvent(QEvent.Type.TouchCancel))
    assert s4_sent == [] and not held_button._touch_active

    # Analog controls support step and repeat, with real feedback displayed.
    s4_sent.clear()
    knob = w._system4_controls["hud_brt"]
    knob.set_feedback(0.50); knob._start(1); knob.stop_repeat(); knob.set_feedback(0.52)
    assert s4_sent == [("HUD_SYM_BRT", 36045)]
    assert knob.value_label.text() == "52%"

    # AUX ENABLE needs two selections; NORM is immediate.
    s4_sent.clear()
    aux = w._system4_controls["aux_rel"]
    aux.select_index(1)
    assert s4_sent == [] and w._system4_safety.aux_pending and aux.current_index == 0
    aux.select_index(1)
    assert s4_sent == [("AUX_REL_SW", "TOGGLE")] and not w._system4_safety.aux_pending
    aux.select_index(0)
    assert s4_sent[-1] == ("AUX_REL_SW", "TOGGLE")

    # Short clicks cannot fire guarded jettison controls.
    s4_sent.clear()
    w._system4_ecm_hold.button.click()
    w._system4_emer_hold.button.click()
    assert s4_sent == []
    assert not w._system4_safety.execute_emergency()
    assert s4_sent == []

    # Completed ECM hold pulses once. EMER additionally requires ARM.
    w._system4_ecm_hold.begin_hold()
    w._system4_ecm_hold._started -= 2.0
    w._system4_ecm_hold._tick()
    wait_ms(w._system4_safety.PULSE_MS + 20)
    assert s4_sent[-2:] == [("CMSD_JET_SEL_BTN", 1), ("CMSD_JET_SEL_BTN", 0)]
    s4_sent.clear()
    assert w._system4_safety.arm_emergency()
    w._system4_emer_hold.begin_hold()
    w._system4_emer_hold._started -= 2.0
    w._system4_emer_hold._tick()
    wait_ms(w._system4_safety.PULSE_MS + 20)
    assert s4_sent == [("EMER_JETT_BTN", 1), ("EMER_JETT_BTN", 0)]
    assert not w._system4_safety.emer_armed

    # Feedback is read directly from the DCS-BIOS memory map, including
    # multiple bit fields sharing one 16-bit address.
    parser_state = w.dcs_bios.parser.state
    raw_742c = (2 << 9) | (1 << 11) | (1 << 14)
    parser_state[0x742C] = raw_742c & 0xFF
    parser_state[0x742D] = raw_742c >> 8
    parser_state[0x7458] = 0xFF; parser_state[0x7459] = 0x7F
    raw_74a8 = (2 << 11) | (0 << 13)
    parser_state[0x74A8] = raw_74a8 & 0xFF; parser_state[0x74A9] = raw_74a8 >> 8
    raw_7498 = (1 << 12) | (1 << 13) | (1 << 14) | (1 << 15)
    parser_state[0x7498] = raw_7498 & 0xFF; parser_state[0x7499] = raw_7498 >> 8
    w._system4_poll_feedback()
    assert w._system4_controls["hud_rej"].current_index == 2
    assert w._system4_controls["hud_mode"].current_index == 1
    assert w._system4_controls["hud_alt"].current_index == 1
    assert w._system4_controls["hdg"].position == 1
    assert w._system4_controls["hdg"].center.text() == "RIGHT"
    assert w._system4_controls["crs"].position == -1
    assert w._system4_controls["crs"].center.text() == "LEFT"
    assert w._system4_controls["rwr_power"].lamp_on
    assert not w._system4_controls["rwr_special"].lamp_on
    assert w._system4_controls["rwr_power"].legend_texts() == ("ON",)
    assert w._system4_controls["rwr_display"].legend_texts() == ("LIMIT", "DISPLAY")
    assert w._system4_controls["rwr_special"].legend_texts() == ("ENABLE", "")
    w._system4_apply_feedback("rwr_fail_lt", 1)
    w._system4_apply_feedback("rwr_bit_lt", 1)
    assert w._system4_controls["rwr_bit"].legend_texts() == ("FAIL", "BIT")
    assert "#cf3434" in w._system4_controls["rwr_bit"].button.styleSheet()

    # Page changes and disconnects disarm every pending action.
    assert w._system4_safety.arm_emergency()
    w._show_page(S4.PAGE_4A)
    assert not w._system4_safety.emer_armed
    w._system4_safety.request_aux(True)
    w._dcs_disconnected = True
    w._system4_poll_feedback()
    assert not w._system4_safety.aux_pending and not w._system4_safety.emer_armed
finally:
    S4.dcs_bios.send_dcs_bios = orig_s4_send
print("[7] SYSTEM 4 MAPPING / FEEDBACK / SAFETY OK")

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
