# -*- coding: utf-8 -*-
"""Three confirmed cold-start setup steps with touch input and feedback loops."""
from __future__ import annotations

import math
import re
import time
from typing import Any, Callable, Dict, Optional

from PyQt6.QtCore import QTimer

import ufc.dcs_bios as dcs_bios
from ufc.cold_direct_entry import PAGE
from ufc.cold_start import _merged_config
from ufc.cv_trim_auto import send_direct_clickable, send_direct_set_command

DEFAULT_MANUAL_SETUP_TARGETS = {
    "land": {"radalt_min_ft": 200, "bingo_fuel_lb": 3000},
    "carrier": {"radalt_min_ft": 200, "bingo_fuel_lb": 4000},
}

P_MANUAL_MINUS = (90, 0)
P_MANUAL_PLUS = (90, 2)
RADALT_INPUT_STEP_FT = 20
RADALT_INPUT_MIN_FT = 20
RADALT_INPUT_MAX_FT = 5000
BINGO_INPUT_STEP_LB = 100
BINGO_INPUT_MIN_LB = 0
BINGO_INPUT_MAX_LB = 20000

SAI_ROTATE_HOLD_MS = 300
SAI_ROTATE_SETTLE_MS = 350
SAI_ROTATE_EXT_VALUE = -0.3
RADALT_TOLERANCE_FT = 10.0
RADALT_MAX_PULSES = 150
RADALT_FEEDBACK_TIMEOUT_MS = 1000
RADALT_DCS_BIOS_STEP = 1000
BINGO_TOLERANCE_LB = 0
BINGO_MAX_PULSES = 200
BINGO_FEEDBACK_TIMEOUT_MS = 1000
BINGO_HOLD_MS = 160
TELEMETRY_MAX_AGE_S = 2.0
FEEDBACK_EPSILON = 0.0005

# Local F/A-18C mainpanel_init.lua calibration. Argument 287 is a normalized
# needle position, not feet. Convert it through both cockpit gauge curves.
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


def radalt_ft_to_pointer(feet: Any) -> Optional[float]:
    try:
        value = float(feet)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value) or value < _ALT_FT[0] or value > _ALT_FT[-1]:
        return None
    needle_position = _interpolate(value, _ALT_FT, _ALT_OUTPUT)
    return _interpolate(needle_position, _MIN_INPUT, _MIN_OUTPUT)


def parse_bingo_fuel(value: Any) -> Optional[int]:
    text = str(value or "").replace("\x00", "").strip()
    match = re.search(r"\d+", text)
    return int(match.group(0)) if match else None


def manual_setup_targets(profile: str) -> Dict[str, int]:
    key = "carrier" if str(profile or "").lower() in ("carrier", "cv") else "land"
    defaults = dict(DEFAULT_MANUAL_SETUP_TARGETS[key])
    configured = _merged_config().get("manual_setup_targets", {})
    if isinstance(configured, dict) and isinstance(configured.get(key), dict):
        for name in ("radalt_min_ft", "bingo_fuel_lb"):
            try:
                defaults[name] = int(configured[key].get(name, defaults[name]))
            except (TypeError, ValueError):
                pass
    defaults["radalt_min_ft"] = _snap_clamp(
        defaults["radalt_min_ft"], RADALT_INPUT_STEP_FT, RADALT_INPUT_MIN_FT, RADALT_INPUT_MAX_FT
    )
    defaults["bingo_fuel_lb"] = _snap_clamp(
        defaults["bingo_fuel_lb"], BINGO_INPUT_STEP_LB, BINGO_INPUT_MIN_LB, BINGO_INPUT_MAX_LB
    )
    return defaults


def _snap_clamp(value: int, step: int, minimum: int, maximum: int) -> int:
    snapped = int(round(int(value) / step) * step)
    return max(minimum, min(maximum, snapped))


def _numeric_changed(before: Any, after: Any) -> bool:
    try:
        return abs(float(after) - float(before)) > FEEDBACK_EPSILON
    except (TypeError, ValueError):
        return False


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

    def _init_cold_start_page(self):
        previous_init_page(self)
        self._cold_manual_input_cells = {
            "minus": self.place_cell("−", P_MANUAL_MINUS, 216, 430, 160, 58,
                                     font_size=24, register=False, page=PAGE, bold=True),
            "value": self.place_cell("", None, 392, 430, 240, 58, font_size=20,
                                     is_variable=True, register=False, no_feedback=True, page=PAGE, bold=True),
            "plus": self.place_cell("+", P_MANUAL_PLUS, 648, 430, 160, 58,
                                    font_size=24, register=False, page=PAGE, bold=True),
        }
        for cell in self._cold_manual_input_cells.values():
            cell.setVisible(False)

    def _cold_step_list(self):
        steps = []
        for step in previous_step_list(self):
            if step[0] == "MANUAL SETUP":
                steps.extend([
                    ("SAI UNLOCK", "manual_sai_unlock", "",
                     "Program pulls and rotates the SAI cage knob. Verify uncaged, then press START."),
                    ("RADALT MIN", "manual_radalt_input", "",
                     "Use touch −/+ in 20 FT steps, press START to apply, then confirm."),
                    ("BINGO FUEL", "manual_bingo_input", "",
                     "Use touch −/+ in 100 LB steps, press START to apply, then confirm."),
                ])
            else:
                steps.append(step)
        return steps

    def _manual_feedback(self, name: str):
        latest = getattr(getattr(self, "dcs_bios", None), "latest", {}) or {}
        key = {
            "radalt": "radalt_min_ptr",
            "radalt_off": "radalt_off_flag",
            "bingo": "IFEI_BINGO",
        }[name]
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

    def _manual_valid(self, token: int) -> bool:
        return (
            token == getattr(self, "_cold_sequence_token", None)
            and getattr(self, "_cold_state", None) == "running"
            and getattr(self, "_cold_manual_step_index", None) == getattr(self, "_cold_step_index", None)
        )

    def _manual_log(self, message: str) -> None:
        self._cold_log("MANUAL_SETUP " + message)

    def _manual_fail(self, reason: str) -> None:
        if getattr(self, "_cold_state", None) != "running":
            return
        self._cold_manual_phase = "failed"
        self._cold_state = "wait_user"
        self._cold_exec_phase = "USER"
        self._cold_last_action = "MANUAL SETUP PARTIAL"
        self._cold_step_detail = f"{reason}. Complete this item manually, then press START."
        self._manual_log(f"failed reason={reason}")
        self._cold_refresh_ui()

    def _manual_enter_confirm(self, phase: str, action: str, detail: str) -> None:
        self._cold_manual_phase = phase
        self._cold_state = "wait_user"
        self._cold_exec_phase = "USER"
        self._cold_last_action = action
        self._cold_step_detail = detail
        self._cold_refresh_ui()

    def _manual_run_sai_unlock(self) -> None:
        token = int(getattr(self, "_cold_sequence_token", 0))
        self._cold_manual_step_index = self._cold_step_index
        self._cold_manual_phase = "sai_command"
        self._cold_exec_phase = "AUTO"
        self._cold_last_action = "SAI UNLOCK"
        self._cold_step_detail = "Rotating the SAI cage knob CCW with the dedicated uncage input."
        self._cold_refresh_ui()
        # SAI_Rotate_EXT is an input-only command from the local FA-18C input
        # map. It rotates the cage control without using SAI_SET, which adjusts
        # the miniature-aircraft pitch when the knob is not pulled.
        ok = send_direct_set_command(
            32, 3005, SAI_ROTATE_EXT_VALUE,
            label="SAI CAGE KNOB CCW", hold_ms=SAI_ROTATE_HOLD_MS, release_value=0.0,
        )
        self._manual_log(
            f"sai channel=bridge_set_command dev=32 cmd=3005 value={SAI_ROTATE_EXT_VALUE} "
            f"hold={SAI_ROTATE_HOLD_MS} ok={ok}"
        )
        if not ok:
            self._manual_fail("SAI UNLOCK SEND FAILED")
            return

        def finish():
            if not self._manual_valid(token):
                return
            self._manual_enter_confirm(
                "sai_confirm", "SAI UNLOCK CONFIRM",
                "CCW cage-knob rotation sent. Verify SAI uncaged and attitude sphere free, then press START.",
            )

        QTimer.singleShot(SAI_ROTATE_HOLD_MS + SAI_ROTATE_SETTLE_MS, finish)

    def _manual_enter_input(self, kind: str) -> None:
        targets = manual_setup_targets(getattr(self, "_cold_profile", "land"))
        self._cold_manual_step_index = self._cold_step_index
        self._cold_state = "wait_user"
        self._cold_exec_phase = "INPUT"
        if kind == "radalt":
            self._cold_manual_phase = "radalt_input"
            self._cold_manual_radalt_target = targets["radalt_min_ft"]
            self._cold_last_action = "RADALT TARGET"
            self._cold_step_detail = "Touch −/+ (20 FT per step), then press START to power and set RADALT."
        else:
            self._cold_manual_phase = "bingo_input"
            self._cold_manual_bingo_target = targets["bingo_fuel_lb"]
            self._cold_last_action = "BINGO TARGET"
            self._cold_step_detail = "Touch −/+ (100 LB per step), then press START to set BINGO."
        self._cold_refresh_ui()

    def _manual_adjust_input(self, direction: int) -> None:
        phase = getattr(self, "_cold_manual_phase", "")
        if getattr(self, "_cold_state", None) != "wait_user" or phase not in ("radalt_input", "bingo_input"):
            return
        if phase == "radalt_input":
            value = int(getattr(self, "_cold_manual_radalt_target", RADALT_INPUT_MIN_FT))
            self._cold_manual_radalt_target = max(
                RADALT_INPUT_MIN_FT, min(RADALT_INPUT_MAX_FT, value + direction * RADALT_INPUT_STEP_FT)
            )
            self._cold_step_detail = f"Selected {self._cold_manual_radalt_target} FT. Press START to apply."
        else:
            value = int(getattr(self, "_cold_manual_bingo_target", BINGO_INPUT_MIN_LB))
            self._cold_manual_bingo_target = max(
                BINGO_INPUT_MIN_LB, min(BINGO_INPUT_MAX_LB, value + direction * BINGO_INPUT_STEP_LB)
            )
            self._cold_step_detail = f"Selected {self._cold_manual_bingo_target} LB. Press START to apply."
        self._cold_refresh_ui()

    def _manual_start_radalt_apply(self) -> None:
        self._cold_state = "running"
        self._cold_exec_phase = "AUTO"
        self._cold_manual_phase = "radalt_power"
        self._cold_manual_radalt_pulses = 0
        token = int(self._cold_sequence_token)
        target = int(self._cold_manual_radalt_target)
        self._cold_last_action = "RADALT POWER / SET"
        self._cold_step_detail = f"Powering RADALT and setting {target} FT."
        self._cold_refresh_ui()
        self._manual_radalt_power(token, target)

    def _manual_radalt_power(self, token: int, target: int) -> None:
        if not self._manual_valid(token):
            return
        try:
            off_flag = float(self._manual_feedback("radalt_off"))
        except (TypeError, ValueError):
            off_flag = None
        if off_flag is not None and off_flag <= 0.5:
            self._manual_log(f"radalt power already on off_flag={off_flag:.3f}")
            self._manual_radalt(token, target)
            return
        before = self._manual_feedback("radalt")
        ok = dcs_bios.send_dcs_bios("RADALT_HEIGHT", f"+{RADALT_DCS_BIOS_STEP}")
        self._manual_log(f"radalt power primary=RADALT_HEIGHT +{RADALT_DCS_BIOS_STEP} off_flag={off_flag} ok={ok}")

        def verify_primary():
            if not self._manual_valid(token):
                return
            try:
                after_off = float(self._manual_feedback("radalt_off"))
            except (TypeError, ValueError):
                after_off = None
            after = self._manual_feedback("radalt")
            if (after_off is not None and after_off <= 0.5) or _numeric_changed(before, after):
                self._manual_radalt(token, target)
            else:
                self._manual_radalt_power_bridge(token, target, before)

        if ok:
            QTimer.singleShot(RADALT_FEEDBACK_TIMEOUT_MS, verify_primary)
        else:
            self._manual_radalt_power_bridge(token, target, before)

    def _manual_radalt_power_bridge(self, token: int, target: int, before: Any) -> None:
        if not self._manual_valid(token):
            return
        value = RADALT_DCS_BIOS_STEP / 65535.0
        ok = send_direct_clickable(30, 3002, value, label="RADALT POWER ON")
        self._manual_log(f"radalt power fallback dev=30 cmd=3002 value={value:.6f} ok={ok}")

        def verify():
            if not self._manual_valid(token):
                return
            after = self._manual_feedback("radalt")
            if _numeric_changed(before, after):
                self._manual_radalt(token, target)
            else:
                self._manual_fail("RADALT DID NOT POWER ON")

        QTimer.singleShot(RADALT_FEEDBACK_TIMEOUT_MS, verify)

    def _manual_radalt(self, token: int, target: int) -> None:
        if not self._manual_valid(token):
            return
        current = radalt_pointer_to_ft(self._manual_feedback("radalt"))
        if current is None:
            self._manual_fail("RADALT NO FEEDBACK")
            return
        pulse = int(getattr(self, "_cold_manual_radalt_pulses", 0))
        self._manual_log(f"radalt current={current:.1f} target={target} pulse={pulse}")
        if abs(current - target) <= RADALT_TOLERANCE_FT:
            self._manual_enter_confirm(
                "radalt_confirm", "RADALT CONFIRM",
                f"RADALT powered and set to {current:.0f} FT (target {target} FT). Verify, then press START.",
            )
            return
        if pulse >= RADALT_MAX_PULSES:
            self._manual_fail("RADALT PULSE LIMIT")
            return
        direction = 1 if current < target else -1
        before = self._manual_feedback("radalt")
        command_value = f"{direction * RADALT_DCS_BIOS_STEP:+d}"
        self._cold_manual_radalt_pulses = pulse + 1
        ok = dcs_bios.send_dcs_bios("RADALT_HEIGHT", command_value)
        self._manual_log(f"radalt primary command={command_value} pulse={pulse + 1} ok={ok}")

        def verify_primary():
            if not self._manual_valid(token):
                return
            after = self._manual_feedback("radalt")
            if _numeric_changed(before, after):
                self._manual_radalt(token, target)
            else:
                self._manual_radalt_bridge(token, target, direction, before)

        if ok:
            QTimer.singleShot(RADALT_FEEDBACK_TIMEOUT_MS, verify_primary)
        else:
            self._manual_radalt_bridge(token, target, direction, before)

    def _manual_radalt_bridge(self, token: int, target: int, direction: int, before: Any) -> None:
        if not self._manual_valid(token):
            return
        value = direction * RADALT_DCS_BIOS_STEP / 65535.0
        ok = send_direct_clickable(30, 3002, value, label="RADALT MIN")
        self._manual_log(f"radalt fallback dev=30 cmd=3002 value={value:.6f} ok={ok}")

        def verify():
            if not self._manual_valid(token):
                return
            after = self._manual_feedback("radalt")
            if _numeric_changed(before, after):
                self._manual_radalt(token, target)
            else:
                self._manual_fail("RADALT NO FEEDBACK CHANGE")

        QTimer.singleShot(RADALT_FEEDBACK_TIMEOUT_MS, verify)

    def _manual_start_bingo_apply(self) -> None:
        self._cold_state = "running"
        self._cold_exec_phase = "AUTO"
        self._cold_manual_phase = "bingo_apply"
        self._cold_manual_bingo_pulses = 0
        target = int(self._cold_manual_bingo_target)
        self._cold_last_action = "BINGO SET"
        self._cold_step_detail = f"Setting BINGO to {target} LB."
        self._cold_refresh_ui()
        self._manual_bingo(int(self._cold_sequence_token), target)

    def _manual_bingo(self, token: int, target: int) -> None:
        if not self._manual_valid(token):
            return
        current = parse_bingo_fuel(self._manual_feedback("bingo"))
        if current is None:
            self._manual_fail("BINGO NO FEEDBACK")
            return
        pulse = int(getattr(self, "_cold_manual_bingo_pulses", 0))
        self._manual_log(f"bingo current={current} target={target} pulse={pulse}")
        if abs(current - target) <= BINGO_TOLERANCE_LB:
            self._manual_enter_confirm(
                "bingo_confirm", "BINGO CONFIRM",
                f"BINGO set to {current} LB. Verify IFEI, then press START.",
            )
            return
        if pulse >= BINGO_MAX_PULSES:
            self._manual_fail("BINGO PULSE LIMIT")
            return
        up = current < target
        ident = "IFEI_UP_BTN" if up else "IFEI_DWN_BTN"
        before = current
        self._cold_manual_bingo_pulses = pulse + 1
        ok = dcs_bios.send_dcs_bios(ident, 1)
        self._manual_log(f"bingo primary command={ident} 1 pulse={pulse + 1} ok={ok}")

        def release_primary():
            if not self._manual_valid(token):
                return
            dcs_bios.send_dcs_bios(ident, 0)
            QTimer.singleShot(BINGO_FEEDBACK_TIMEOUT_MS, verify_primary)

        def verify_primary():
            if not self._manual_valid(token):
                return
            after = parse_bingo_fuel(self._manual_feedback("bingo"))
            if after is not None and after != before:
                self._manual_bingo(token, target)
            else:
                self._manual_bingo_bridge(token, target, up, before)

        if ok:
            QTimer.singleShot(BINGO_HOLD_MS, release_primary)
        else:
            self._manual_bingo_bridge(token, target, up, before)

    def _manual_bingo_bridge(self, token: int, target: int, up: bool, before: int) -> None:
        if not self._manual_valid(token):
            return
        command = 3003 if up else 3004
        ok = send_direct_clickable(33, command, 1.0, label="BINGO", hold_ms=BINGO_HOLD_MS, release_value=0.0)
        self._manual_log(f"bingo fallback dev=33 cmd={command} value=1 ok={ok}")

        def verify():
            if not self._manual_valid(token):
                return
            after = parse_bingo_fuel(self._manual_feedback("bingo"))
            if after is not None and after != before:
                self._manual_bingo(token, target)
            else:
                self._manual_fail("BINGO NO FEEDBACK CHANGE")

        QTimer.singleShot(BINGO_FEEDBACK_TIMEOUT_MS + BINGO_HOLD_MS, verify)

    def _cold_handle_click(self, pos):
        if pos == P_MANUAL_MINUS:
            self._manual_adjust_input(-1)
            return
        if pos == P_MANUAL_PLUS:
            self._manual_adjust_input(1)
            return
        previous_handle_click(self, pos)

    def _cold_arm_or_continue(self):
        phase = getattr(self, "_cold_manual_phase", "")
        if getattr(self, "_cold_state", None) == "wait_user" and phase == "radalt_input":
            self._cold_log("RADALT TARGET ACCEPTED")
            self._manual_start_radalt_apply()
            return
        if getattr(self, "_cold_state", None) == "wait_user" and phase == "bingo_input":
            self._cold_log("BINGO TARGET ACCEPTED")
            self._manual_start_bingo_apply()
            return
        previous_arm_or_continue(self)

    def _cold_refresh_ui(self):
        previous_refresh_ui(self)
        cells = getattr(self, "_cold_manual_input_cells", {})
        input_visible = (
            getattr(self, "_current_page", None) == PAGE
            and getattr(self, "_cold_state", None) == "wait_user"
            and getattr(self, "_cold_manual_phase", "") in ("radalt_input", "bingo_input")
        )
        for cell in cells.values():
            cell.setVisible(input_visible)
        if input_visible and cells.get("value"):
            if self._cold_manual_phase == "radalt_input":
                cells["value"].setText(f"{int(self._cold_manual_radalt_target)} FT")
            else:
                cells["value"].setText(f"{int(self._cold_manual_bingo_target)} LB")

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
                if kind == "manual_radalt_input":
                    self._manual_enter_input("radalt")
                    return
                if kind == "manual_bingo_input":
                    self._manual_enter_input("bingo")
                    return
        previous_run_next_step(self)

    UFCKeypadWindowClass._init_cold_start_page = _init_cold_start_page
    UFCKeypadWindowClass._cold_step_list = _cold_step_list
    UFCKeypadWindowClass._manual_feedback = _manual_feedback
    UFCKeypadWindowClass._manual_valid = _manual_valid
    UFCKeypadWindowClass._manual_log = _manual_log
    UFCKeypadWindowClass._manual_fail = _manual_fail
    UFCKeypadWindowClass._manual_enter_confirm = _manual_enter_confirm
    UFCKeypadWindowClass._manual_run_sai_unlock = _manual_run_sai_unlock
    UFCKeypadWindowClass._manual_enter_input = _manual_enter_input
    UFCKeypadWindowClass._manual_adjust_input = _manual_adjust_input
    UFCKeypadWindowClass._manual_start_radalt_apply = _manual_start_radalt_apply
    UFCKeypadWindowClass._manual_radalt_power = _manual_radalt_power
    UFCKeypadWindowClass._manual_radalt_power_bridge = _manual_radalt_power_bridge
    UFCKeypadWindowClass._manual_radalt = _manual_radalt
    UFCKeypadWindowClass._manual_radalt_bridge = _manual_radalt_bridge
    UFCKeypadWindowClass._manual_start_bingo_apply = _manual_start_bingo_apply
    UFCKeypadWindowClass._manual_bingo = _manual_bingo
    UFCKeypadWindowClass._manual_bingo_bridge = _manual_bingo_bridge
    UFCKeypadWindowClass._cold_handle_click = _cold_handle_click
    UFCKeypadWindowClass._cold_arm_or_continue = _cold_arm_or_continue
    UFCKeypadWindowClass._cold_refresh_ui = _cold_refresh_ui
    UFCKeypadWindowClass._cold_run_next_step = _cold_run_next_step
