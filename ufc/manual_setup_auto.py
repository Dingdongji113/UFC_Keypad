# -*- coding: utf-8 -*-
"""Direct touch controls for SAI, RADALT minimum, and IFEI BINGO setup."""
from __future__ import annotations

import math
import re
import time
from typing import Any, Optional

from PyQt6.QtCore import QTimer

import ufc.dcs_bios as dcs_bios
from ufc.cold_direct_entry import PAGE, P_RESET
from ufc.cv_trim_auto import send_direct_clickable, send_direct_set_command

P_MANUAL_MINUS = (90, 0)
P_MANUAL_PLUS = (90, 2)

MANUAL_REPEAT_INITIAL_DELAY_MS = 250
RADALT_REPEAT_INTERVAL_MS = 100
BINGO_REPEAT_INTERVAL_MS = 100
MANUAL_FEEDBACK_REFRESH_MS = 200
RADALT_DIRECT_DCS_STEP = 1311  # local input mapping uses relative +/-0.02
RADALT_DIRECT_BRIDGE_STEP = 0.02
BINGO_PRESS_MS = 40

SAI_ROTATE_HOLD_MS = 300
SAI_ROTATE_SETTLE_MS = 350
SAI_ROTATE_EXT_VALUE = -0.3
TELEMETRY_MAX_AGE_S = 2.0

# Local F/A-18C mainpanel_init.lua calibration. Argument 287 is normalized.
_MIN_INPUT = (-0.03, 0.0, 0.5, 0.8, 1.0)
_MIN_OUTPUT = (0.0, 0.031, 0.525, 0.802, 0.982)
_ALT_FT = (-10.0, 0.0, 100.0, 200.0, 300.0, 400.0, 600.0, 800.0, 1000.0, 3000.0, 5000.0, 5100.0)
_ALT_OUTPUT = (0.0, 0.048, 0.171, 0.296, 0.416, 0.530, 0.616, 0.706, 0.799, 0.886, 0.974, 0.98)


def _interpolate(value: float, xs, ys) -> float:
    if value <= xs[0]:
        return float(ys[0])
    if value >= xs[-1]:
        return float(ys[-1])
    for index in range(1, len(xs)):
        if value <= xs[index]:
            span = float(xs[index] - xs[index - 1])
            ratio = 0.0 if span == 0 else (value - xs[index - 1]) / span
            return float(ys[index - 1] + ratio * (ys[index] - ys[index - 1]))
    return float(ys[-1])


def radalt_pointer_to_ft(pointer: Any) -> Optional[float]:
    try:
        value = float(pointer)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value) or value < -0.02 or value > 1.02:
        return None
    needle_position = _interpolate(value, _MIN_OUTPUT, _MIN_INPUT)
    return _interpolate(needle_position, _ALT_OUTPUT, _ALT_FT)


def parse_bingo_fuel(value: Any) -> Optional[int]:
    text = str(value or "").replace("\x00", "").strip()
    match = re.search(r"\d+", text)
    return int(match.group(0)) if match else None


def install_manual_setup_automation(UFCKeypadWindowClass) -> None:
    if getattr(UFCKeypadWindowClass, "_manual_setup_automation_installed", False):
        return
    UFCKeypadWindowClass._manual_setup_automation_installed = True

    previous_init_page = UFCKeypadWindowClass._init_cold_start_page
    previous_step_list = UFCKeypadWindowClass._cold_step_list
    previous_run_next_step = UFCKeypadWindowClass._cold_run_next_step
    previous_handle_click = UFCKeypadWindowClass._cold_handle_click
    previous_arm_or_continue = UFCKeypadWindowClass._cold_arm_or_continue
    previous_refresh_ui = UFCKeypadWindowClass._cold_refresh_ui
    previous_show_page = UFCKeypadWindowClass._show_page
    previous_reset_session = UFCKeypadWindowClass._cold_reset_session_state
    previous_close_event = UFCKeypadWindowClass.closeEvent

    def _init_cold_start_page(self):
        previous_init_page(self)
        minus = self.place_cell("−", P_MANUAL_MINUS, 216, 430, 160, 58,
                                font_size=24, register=False, page=PAGE, bold=True)
        value = self.place_cell("", None, 392, 430, 240, 58, font_size=20,
                                is_variable=True, register=False, no_feedback=True, page=PAGE, bold=True)
        plus = self.place_cell("+", P_MANUAL_PLUS, 648, 430, 160, 58,
                               font_size=24, register=False, page=PAGE, bold=True)
        self._cold_manual_input_cells = {"minus": minus, "value": value, "plus": plus}
        minus.action_pressed.connect(self._manual_control_press)
        plus.action_pressed.connect(self._manual_control_press)
        minus.action_released.connect(self._manual_control_release)
        plus.action_released.connect(self._manual_control_release)
        for cell in self._cold_manual_input_cells.values():
            cell.setVisible(False)

    def _cold_step_list(self):
        original = list(previous_step_list(self))
        moved = [step for step in original if step[0] in ("RADAR / INS", "AMPCD PB19")]
        steps = []
        for step in original:
            if step[0] in ("RADAR / INS", "AMPCD PB19"):
                continue
            if step[0] == "MANUAL SETUP":
                steps.extend(moved)
                steps.extend([
                    ("SAI UNLOCK", "manual_sai_unlock", "",
                     "Program rotates the SAI cage knob CCW. Verify uncaged, then press START."),
                    ("RADALT MIN", "manual_radalt_direct", "",
                     "Touch/hold left to decrease and right to increase. START confirms current cockpit value."),
                    ("BINGO FUEL", "manual_bingo_direct", "",
                     "Touch/hold left to decrease and right to increase. START confirms current IFEI value."),
                ])
            else:
                steps.append(step)
        return steps

    def _manual_feedback(self, name: str):
        latest = getattr(getattr(self, "dcs_bios", None), "latest", {}) or {}
        key = {"radalt": "radalt_min_ptr", "radalt_off": "radalt_off_flag", "bingo": "IFEI_BINGO"}[name]
        value = latest.get(key)
        if value not in (None, ""):
            return value
        snapshot_method = getattr(self, "_cv_trim_snapshot", None)
        if callable(snapshot_method):
            snapshot = snapshot_method()
            if time.time() - float(getattr(snapshot, "timestamp", 0.0) or 0.0) <= TELEMETRY_MAX_AGE_S:
                raw = getattr(snapshot, "raw", {}) or {}
                bridge_key = {
                    "radalt": "radalt_min_arg_287",
                    "radalt_off": "radalt_off_arg_288",
                    "bingo": "ifei_bingo",
                }[name]
                if raw.get(bridge_key) not in (None, ""):
                    return raw.get(bridge_key)
        return None

    def _manual_display_text(self) -> str:
        phase = getattr(self, "_cold_manual_phase", "")
        if phase == "radalt_direct":
            try:
                if float(self._manual_feedback("radalt_off")) > 0.5:
                    return "OFF"
            except (TypeError, ValueError):
                pass
            feet = radalt_pointer_to_ft(self._manual_feedback("radalt"))
            return "--- FT" if feet is None else f"{max(0, round(feet))} FT"
        if phase == "bingo_direct":
            bingo = parse_bingo_fuel(self._manual_feedback("bingo"))
            return "---- LB" if bingo is None else f"{bingo} LB"
        return ""

    def _manual_step_kind(self) -> str:
        steps = self._cold_step_list()
        index = int(getattr(self, "_cold_step_index", -1))
        return steps[index][1] if 0 <= index < len(steps) else ""

    def _manual_direct_context_valid(self, generation: Optional[int] = None) -> bool:
        phase = getattr(self, "_cold_manual_phase", "")
        expected_kind = "manual_radalt_direct" if phase == "radalt_direct" else "manual_bingo_direct"
        valid = (
            getattr(self, "_cold_state", None) == "wait_user"
            and getattr(self, "_current_page", None) == PAGE
            and phase in ("radalt_direct", "bingo_direct")
            and self._manual_step_kind() == expected_kind
            and getattr(self, "_cold_manual_step_index", None) == getattr(self, "_cold_step_index", None)
            and getattr(self, "_cold_manual_token", None) == getattr(self, "_cold_sequence_token", None)
        )
        if generation is not None:
            valid = valid and generation == getattr(self, "_cold_manual_repeat_generation", None)
        return valid

    def _manual_stop_repeat(self) -> None:
        self._cold_manual_repeat_active = False
        self._cold_manual_repeat_generation = int(getattr(self, "_cold_manual_repeat_generation", 0)) + 1

    def _manual_send_radalt_step(self, direction: int) -> None:
        value = RADALT_DIRECT_DCS_STEP if direction > 0 else -RADALT_DIRECT_DCS_STEP
        ok = dcs_bios.send_dcs_bios("RADALT_HEIGHT", f"{value:+d}")
        self._cold_log(f"RADALT DIRECT {'INC' if direction > 0 else 'DEC'} dcs_bios={'OK' if ok else 'FAIL'}")
        if not ok:
            bridge_value = RADALT_DIRECT_BRIDGE_STEP if direction > 0 else -RADALT_DIRECT_BRIDGE_STEP
            bridge_ok = send_direct_clickable(30, 3002, bridge_value, label="RADALT DIRECT")
            self._cold_log(f"RADALT DIRECT bridge={'OK' if bridge_ok else 'FAIL'} value={bridge_value}")

    def _manual_send_bingo_step(self, direction: int) -> None:
        ident = "IFEI_UP_BTN" if direction > 0 else "IFEI_DWN_BTN"
        ok = dcs_bios.send_dcs_bios(ident, 1)
        self._cold_log(f"BINGO DIRECT {ident} press dcs_bios={'OK' if ok else 'FAIL'}")
        if ok:
            # Release is always sent even after page/token changes so the
            # cockpit pushbutton can never remain stuck down.
            QTimer.singleShot(BINGO_PRESS_MS, lambda ident=ident: dcs_bios.send_dcs_bios(ident, 0))
        else:
            bridge_ok = send_direct_clickable(
                33, 3003 if direction > 0 else 3004, 1.0,
                label="BINGO DIRECT", hold_ms=BINGO_PRESS_MS, release_value=0.0,
            )
            self._cold_log(f"BINGO DIRECT bridge={'OK' if bridge_ok else 'FAIL'}")

    def _manual_send_direct_step(self, direction: int) -> None:
        if not self._manual_direct_context_valid():
            self._manual_stop_repeat()
            return
        if self._cold_manual_phase == "radalt_direct":
            self._manual_send_radalt_step(direction)
        else:
            self._manual_send_bingo_step(direction)
        QTimer.singleShot(60, self._cold_refresh_ui)

    def _manual_repeat_tick(self, generation: int, direction: int) -> None:
        # A timer from an older press must never cancel a newer hold.
        if generation != getattr(self, "_cold_manual_repeat_generation", None):
            return
        if not getattr(self, "_cold_manual_repeat_active", False) or not self._manual_direct_context_valid(generation):
            self._manual_stop_repeat()
            return
        self._manual_send_direct_step(direction)
        interval = RADALT_REPEAT_INTERVAL_MS if self._cold_manual_phase == "radalt_direct" else BINGO_REPEAT_INTERVAL_MS
        QTimer.singleShot(interval, lambda: self._manual_repeat_tick(generation, direction))

    def _manual_control_press(self, pos) -> None:
        if pos not in (P_MANUAL_MINUS, P_MANUAL_PLUS) or not self._manual_direct_context_valid():
            return
        self._manual_stop_repeat()
        direction = -1 if pos == P_MANUAL_MINUS else 1
        self._cold_manual_repeat_active = True
        generation = self._cold_manual_repeat_generation
        self._manual_send_direct_step(direction)
        QTimer.singleShot(
            MANUAL_REPEAT_INITIAL_DELAY_MS,
            lambda: self._manual_repeat_tick(generation, direction),
        )

    def _manual_control_release(self, _pos=None) -> None:
        self._manual_stop_repeat()

    def _manual_schedule_feedback_refresh(self, generation: int) -> None:
        if generation != getattr(self, "_cold_manual_feedback_generation", None):
            return
        if not self._manual_direct_context_valid():
            return
        self._cold_refresh_ui()
        QTimer.singleShot(
            MANUAL_FEEDBACK_REFRESH_MS,
            lambda: self._manual_schedule_feedback_refresh(generation),
        )

    def _manual_enter_direct(self, kind: str) -> None:
        self._manual_stop_repeat()
        self._cold_manual_step_index = self._cold_step_index
        self._cold_manual_token = self._cold_sequence_token
        self._cold_manual_phase = f"{kind}_direct"
        self._cold_state = "wait_user"
        self._cold_exec_phase = "DIRECT"
        self._cold_last_action = "RADALT MIN" if kind == "radalt" else "BINGO FUEL"
        self._cold_step_detail = "Hold − to decrease, + to increase. START confirms the live cockpit value."
        self._cold_manual_feedback_generation = int(getattr(self, "_cold_manual_feedback_generation", 0)) + 1
        generation = self._cold_manual_feedback_generation
        self._cold_refresh_ui()
        QTimer.singleShot(MANUAL_FEEDBACK_REFRESH_MS, lambda: self._manual_schedule_feedback_refresh(generation))

    def _manual_run_sai_unlock(self) -> None:
        self._manual_stop_repeat()
        token = int(getattr(self, "_cold_sequence_token", 0))
        self._cold_manual_step_index = self._cold_step_index
        self._cold_manual_phase = "sai_command"
        self._cold_exec_phase = "AUTO"
        self._cold_last_action = "SAI UNLOCK"
        self._cold_step_detail = "Rotating the SAI cage knob CCW with the dedicated uncage input."
        self._cold_refresh_ui()
        ok = send_direct_set_command(
            32, 3005, SAI_ROTATE_EXT_VALUE,
            label="SAI CAGE KNOB CCW", hold_ms=SAI_ROTATE_HOLD_MS, release_value=0.0,
        )
        self._cold_log(f"SAI UNLOCK SetCommand {'OK' if ok else 'FAIL'}")
        if not ok:
            self._cold_state = "wait_user"
            self._cold_exec_phase = "USER"
            self._cold_manual_phase = "failed"
            self._cold_last_action = "SAI UNLOCK FAILED"
            self._cold_step_detail = "Uncage SAI manually, then press START."
            self._cold_refresh_ui()
            return

        def finish():
            if token != getattr(self, "_cold_sequence_token", None) or getattr(self, "_cold_step_index", None) != self._cold_manual_step_index:
                return
            self._cold_state = "wait_user"
            self._cold_exec_phase = "USER"
            self._cold_manual_phase = "sai_confirm"
            self._cold_last_action = "SAI UNLOCK CONFIRM"
            self._cold_step_detail = "Verify SAI uncaged and attitude sphere free, then press START."
            self._cold_refresh_ui()

        QTimer.singleShot(SAI_ROTATE_HOLD_MS + SAI_ROTATE_SETTLE_MS, finish)

    def _cold_handle_click(self, pos):
        if pos in (P_MANUAL_MINUS, P_MANUAL_PLUS):
            # Press/release signals own direct control; release click must not
            # create a second step.
            return
        if pos == P_RESET:
            self._manual_stop_repeat()
        previous_handle_click(self, pos)

    def _cold_arm_or_continue(self):
        if getattr(self, "_cold_manual_phase", "") in ("radalt_direct", "bingo_direct"):
            self._manual_stop_repeat()
            self._cold_manual_feedback_generation = int(getattr(self, "_cold_manual_feedback_generation", 0)) + 1
        previous_arm_or_continue(self)

    def _cold_refresh_ui(self):
        previous_refresh_ui(self)
        cells = getattr(self, "_cold_manual_input_cells", {})
        visible = self._manual_direct_context_valid()
        for cell in cells.values():
            cell.setVisible(visible)
        if visible and cells.get("value"):
            cells["value"].setText(self._manual_display_text())

    def _show_page(self, page_name):
        if page_name != PAGE:
            self._manual_stop_repeat()
            self._cold_manual_feedback_generation = int(getattr(self, "_cold_manual_feedback_generation", 0)) + 1
        return previous_show_page(self, page_name)

    def _cold_reset_session_state(self, reason: str = ""):
        self._manual_stop_repeat()
        self._cold_manual_feedback_generation = int(getattr(self, "_cold_manual_feedback_generation", 0)) + 1
        return previous_reset_session(self, reason)

    def closeEvent(self, event):
        self._manual_stop_repeat()
        self._cold_manual_feedback_generation = int(getattr(self, "_cold_manual_feedback_generation", 0)) + 1
        return previous_close_event(self, event)

    def _cold_run_next_step(self):
        if getattr(self, "_cold_state", None) == "running":
            steps = self._cold_step_list()
            index = int(getattr(self, "_cold_step_index", -1))
            if 0 <= index < len(steps):
                kind = steps[index][1]
                self._cold_total_steps = len(steps)
                if kind == "manual_sai_unlock":
                    self._manual_run_sai_unlock()
                    return
                if kind == "manual_radalt_direct":
                    self._manual_enter_direct("radalt")
                    return
                if kind == "manual_bingo_direct":
                    self._manual_enter_direct("bingo")
                    return
        previous_run_next_step(self)

    UFCKeypadWindowClass._init_cold_start_page = _init_cold_start_page
    UFCKeypadWindowClass._cold_step_list = _cold_step_list
    UFCKeypadWindowClass._manual_feedback = _manual_feedback
    UFCKeypadWindowClass._manual_display_text = _manual_display_text
    UFCKeypadWindowClass._manual_step_kind = _manual_step_kind
    UFCKeypadWindowClass._manual_direct_context_valid = _manual_direct_context_valid
    UFCKeypadWindowClass._manual_stop_repeat = _manual_stop_repeat
    UFCKeypadWindowClass._manual_send_radalt_step = _manual_send_radalt_step
    UFCKeypadWindowClass._manual_send_bingo_step = _manual_send_bingo_step
    UFCKeypadWindowClass._manual_send_direct_step = _manual_send_direct_step
    UFCKeypadWindowClass._manual_repeat_tick = _manual_repeat_tick
    UFCKeypadWindowClass._manual_control_press = _manual_control_press
    UFCKeypadWindowClass._manual_control_release = _manual_control_release
    UFCKeypadWindowClass._manual_schedule_feedback_refresh = _manual_schedule_feedback_refresh
    UFCKeypadWindowClass._manual_enter_direct = _manual_enter_direct
    UFCKeypadWindowClass._manual_run_sai_unlock = _manual_run_sai_unlock
    UFCKeypadWindowClass._cold_handle_click = _cold_handle_click
    UFCKeypadWindowClass._cold_arm_or_continue = _cold_arm_or_continue
    UFCKeypadWindowClass._cold_refresh_ui = _cold_refresh_ui
    UFCKeypadWindowClass._show_page = _show_page
    UFCKeypadWindowClass._cold_reset_session_state = _cold_reset_session_state
    UFCKeypadWindowClass.closeEvent = closeEvent
    UFCKeypadWindowClass._cold_run_next_step = _cold_run_next_step
