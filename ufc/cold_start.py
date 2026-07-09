# -*- coding: utf-8 -*-
"""F/A-18C cold-start manager patch.

Current logic:
- The normal startup animation is no longer a program-boot splash.
- On incoming DCS-BIOS data, the app first looks at left engine RPM.
- If left RPM >= threshold, the aircraft is considered already running: play the
  startup animation once, then stay on the LOCAL ICP main keyboard.
- If left RPM < threshold, the aircraft is considered cold: do not play the
  startup animation yet.  The hidden cold-start page can be opened only by
  tapping SETTINGS three times while left RPM is still below the threshold.
- During the cold-start flow, the startup animation is played after the right
  engine has been confirmed stable; when the animation finishes, the flow
  returns to the cold-start page and continues with the left engine.

The page name remains ``cold_start`` for compatibility, but it is no longer a
SYSTEMS menu item.  It is an independent guarded page.
"""
from __future__ import annotations

import re
import time
from typing import Any, Callable, Dict, List, Optional

from PyQt6.QtCore import Qt, QTimer

from ufc.config import load_config, save_config
from ufc.dcs_bios import send_dcs_bios
from ufc.startup import install_startup_overlay


PAGE = "cold_start"
SETTINGS_POS = (0, 5)
STARTUP_MODE_COLD = "cold_start"
STARTUP_MODE_NON_COLD = "non_cold"
STARTUP_MODE_UNKNOWN = "unknown"
LEFT_RPM_FIELD = "IFEI_RPM_L"
LEFT_RPM_INTERNAL = "left_engine_rpm"

P_START = (300, 0)
P_PAUSE = (300, 1)
P_ABORT = (300, 2)
P_SKIP = (300, 3)
P_DAY = (300, 4)
P_NIGHT = (300, 5)
P_PROFILE = (300, 6)

DEFAULT_DISPLAY_PRESETS = {
    "day": {"lddi": 80, "rddi": 80, "ampcd": 80, "hud": 70},
    "night": {"lddi": 25, "rddi": 25, "ampcd": 20, "hud": 25},
}

DEFAULT_CONTROLS = {
    "battery_on": {"id": "BATTERY_SW", "value": 0},
    "apu_start": {"id": "APU_CONTROL_SW", "value": 1},
    "right_engine_crank": {"id": "ENGINE_CRANK_SW", "value": 2},
    "left_engine_crank": {"id": "ENGINE_CRANK_SW", "value": 0},
    "apu_off": {"id": "APU_CONTROL_SW", "value": 0},
    "canopy_close": {
        "sequence": [
            {"id": "CANOPY_SW", "value": 2, "delay_ms": 6000},
            {"id": "CANOPY_SW", "value": 1, "delay_ms": 80},
        ]
    },
    "bleed_air_cycle": {
        "sequence": [
            {"id": "BLEED_AIR_PULL", "value": 1, "delay_ms": 150},
            {"id": "BLEED_AIR_KNOB", "value": 0, "delay_ms": 120},
            {"id": "BLEED_AIR_KNOB", "value": 1, "delay_ms": 120},
            {"id": "BLEED_AIR_KNOB", "value": 2, "delay_ms": 120},
            {"id": "BLEED_AIR_KNOB", "value": 3, "delay_ms": 120},
            {"id": "BLEED_AIR_KNOB", "value": 1, "delay_ms": 120},
        ]
    },
    "trim_reset": {
        "sequence": [
            {"id": "TO_TRIM_BTN", "value": 1, "delay_ms": 80},
            {"id": "TO_TRIM_BTN", "value": 0, "delay_ms": 80},
        ]
    },
    "fcs_reset": {
        "sequence": [
            {"id": "FCS_RESET_BTN", "value": 1, "delay_ms": 80},
            {"id": "FCS_RESET_BTN", "value": 0, "delay_ms": 80},
        ]
    },
    "ecm_receive": {"id": "ECM_MODE_SW", "value": 1},
    "ins_land": {"id": "INS_SW", "value": 2},
    "ins_carrier": {"id": "INS_SW", "value": 1},
    "display_lddi_select": {"id": "LEFT_DDI_BRT_SELECT", "day_value": 2, "night_value": 1},
    "display_rddi_select": {"id": "RIGHT_DDI_BRT_SELECT", "day_value": 2, "night_value": 1},
    "display_ampcd_select": {"id": "", "day_value": 1, "night_value": 0},
    "display_hud_select": {"id": "", "day_value": 1, "night_value": 0},
    "display_lddi": {"id": "LEFT_DDI_BRT_CTL", "value_type": "analog"},
    "display_rddi": {"id": "RIGHT_DDI_BRT_CTL", "value_type": "analog"},
    "display_ampcd": {"id": "AMPCD_BRT_CTL", "value_type": "analog"},
    "display_hud": {"id": "HUD_SYM_BRT", "value_type": "analog"},
}


def _pct_to_bios(percent: int) -> int:
    percent = max(0, min(100, int(percent)))
    return round(percent / 100 * 65535)


def _is_empty(value: Any) -> bool:
    return value is None or value == ""


def _parse_rpm_value(value: Any) -> Optional[float]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _merge_control(default: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    result = default.copy()

    default_sequence = default.get("sequence")
    override_sequence = override.get("sequence")
    if isinstance(default_sequence, list) or isinstance(override_sequence, list):
        base_sequence = default_sequence if isinstance(default_sequence, list) else []
        user_sequence = override_sequence if isinstance(override_sequence, list) else []
        merged_sequence: List[Dict[str, Any]] = []
        max_len = max(len(base_sequence), len(user_sequence))
        for i in range(max_len):
            base = base_sequence[i].copy() if i < len(base_sequence) and isinstance(base_sequence[i], dict) else {}
            user = user_sequence[i] if i < len(user_sequence) and isinstance(user_sequence[i], dict) else {}
            merged = base.copy()
            for k, v in user.items():
                if _is_empty(v) and not _is_empty(base.get(k)):
                    continue
                merged[k] = v
            merged_sequence.append(merged)
        result["sequence"] = merged_sequence

    for k, v in override.items():
        if k == "sequence":
            continue
        if _is_empty(v) and not _is_empty(default.get(k)):
            continue
        result[k] = v
    return result


def _merged_config() -> Dict[str, Any]:
    cfg = load_config()
    controls = {key: value.copy() for key, value in DEFAULT_CONTROLS.items()}
    for key, value in (cfg.get("cold_start_controls", {}) or {}).items():
        if isinstance(value, dict):
            controls[key] = _merge_control(controls.get(key, {}), value)
        else:
            controls[key] = value

    presets = {
        "day": DEFAULT_DISPLAY_PRESETS["day"].copy(),
        "night": DEFAULT_DISPLAY_PRESETS["night"].copy(),
    }
    user_presets = cfg.get("display_brightness_presets", {}) or {}
    for mode in ("day", "night"):
        if isinstance(user_presets.get(mode), dict):
            presets[mode].update(user_presets[mode])

    cfg.setdefault("cold_start_profile", "land")
    cfg.setdefault("cold_start_display_mode", "day")
    cfg.setdefault("cold_start_left_rpm_threshold", 60)
    cfg["cold_start_controls"] = controls
    cfg["display_brightness_presets"] = presets
    return cfg


def patch_cold_start(UFCKeypadWindowClass):
    """Install guarded cold-start page and animation timing logic."""
    if getattr(UFCKeypadWindowClass, "_cold_start_patch_installed", False):
        return
    UFCKeypadWindowClass._cold_start_patch_installed = True

    orig_init_ui = UFCKeypadWindowClass.init_ui
    orig_on_cell_click = UFCKeypadWindowClass.on_cell_click
    orig_update_display = UFCKeypadWindowClass._update_display

    def init_ui(self):
        orig_init_ui(self)
        self._cold_start_setup_state()
        self._init_cold_start_page()
        # This page is intentionally not exposed through SYSTEMS option 4.
        self._show_page(self._current_page)

    def on_cell_click(self, pos):
        if getattr(self, "_current_page", None) == PAGE:
            self._cold_handle_click(pos)
            return

        if getattr(self, "_current_page", None) == "local_icp" and pos == SETTINGS_POS:
            if self._cold_handle_settings_tap():
                return

        # SYSTEMS option 4 is reserved again; cold-start is independent.
        orig_on_cell_click(self, pos)

    def _update_display(self, field_name, value):
        if field_name == LEFT_RPM_INTERNAL:
            self._cold_left_rpm = _parse_rpm_value(value)
            self._cold_on_dcs_signal(field_name, value)
            if getattr(self, "_current_page", None) == PAGE:
                self._cold_detect_startup_mode()
                self._cold_refresh_ui()
            return

        orig_update_display(self, field_name, value)
        self._cold_on_dcs_signal(field_name, value)

    UFCKeypadWindowClass.init_ui = init_ui
    UFCKeypadWindowClass.on_cell_click = on_cell_click
    UFCKeypadWindowClass._update_display = _update_display

    UFCKeypadWindowClass._cold_start_setup_state = _cold_start_setup_state
    UFCKeypadWindowClass._init_cold_start_page = _init_cold_start_page
    UFCKeypadWindowClass._cold_on_dcs_signal = _cold_on_dcs_signal
    UFCKeypadWindowClass._cold_handle_settings_tap = _cold_handle_settings_tap
    UFCKeypadWindowClass._cold_play_startup_animation = _cold_play_startup_animation
    UFCKeypadWindowClass._cold_handle_click = _cold_handle_click
    UFCKeypadWindowClass._cold_arm_or_continue = _cold_arm_or_continue
    UFCKeypadWindowClass._cold_step_list = _cold_step_list
    UFCKeypadWindowClass._cold_run_next_step = _cold_run_next_step
    UFCKeypadWindowClass._cold_detect_startup_mode = _cold_detect_startup_mode
    UFCKeypadWindowClass._cold_get_left_rpm = _cold_get_left_rpm
    UFCKeypadWindowClass._cold_poll_detection = _cold_poll_detection
    UFCKeypadWindowClass._cold_enter_hold = _cold_enter_hold
    UFCKeypadWindowClass._cold_abort = _cold_abort
    UFCKeypadWindowClass._cold_pause = _cold_pause
    UFCKeypadWindowClass._cold_skip = _cold_skip
    UFCKeypadWindowClass._cold_set_display_mode = _cold_set_display_mode
    UFCKeypadWindowClass._cold_set_profile = _cold_set_profile
    UFCKeypadWindowClass._cold_entries_from_config = _cold_entries_from_config
    UFCKeypadWindowClass._cold_send_configured = _cold_send_configured
    UFCKeypadWindowClass._cold_send_configured_async = _cold_send_configured_async
    UFCKeypadWindowClass._cold_run_sequence_entries = _cold_run_sequence_entries
    UFCKeypadWindowClass._cold_apply_display_brightness = _cold_apply_display_brightness
    UFCKeypadWindowClass._cold_unlock_local_icp = _cold_unlock_local_icp
    UFCKeypadWindowClass._cold_status_lines = _cold_status_lines
    UFCKeypadWindowClass._cold_refresh_ui = _cold_refresh_ui
    UFCKeypadWindowClass._cold_set_cell = _cold_set_cell
    UFCKeypadWindowClass._cold_log = _cold_log


def _cold_start_setup_state(self):
    cfg = _merged_config()
    self._cold_state = "idle"
    self._cold_step_index = -1
    self._cold_hold_reason = ""
    self._cold_display_mode = str(cfg.get("cold_start_display_mode", "day")).lower()
    if self._cold_display_mode not in ("day", "night"):
        self._cold_display_mode = "day"
    self._cold_profile = str(cfg.get("cold_start_profile", "land")).lower()
    if self._cold_profile not in ("land", "carrier"):
        self._cold_profile = "land"
    try:
        self._cold_rpm_threshold = float(cfg.get("cold_start_left_rpm_threshold", 60))
    except (TypeError, ValueError):
        self._cold_rpm_threshold = 60.0

    self._cold_left_rpm = None
    self._cold_detected_mode = STARTUP_MODE_UNKNOWN
    self._cold_first_mode_decided = False
    self._cold_start_anim_played = False
    self._cold_hidden_tap_count = 0
    self._cold_hidden_tap_at = 0.0

    self._cold_right_engine_online = False
    self._cold_left_engine_online = False
    self._cold_apu_off = False
    self._cold_display_brightness_applied = False
    self._cold_normal_ufc_locked = True
    self._cold_sequence_token = 0
    self._cold_cells = {}
    self._cold_status_cells = {}
    self._cold_last_action = "COLD ACCESS: SETTINGS x3 WHEN L RPM < 60"
    self._cold_total_steps = 0

    self._cold_detect_timer = QTimer(self)
    self._cold_detect_timer.timeout.connect(self._cold_poll_detection)
    self._cold_detect_timer.start(1000)


def _init_cold_start_page(self):
    self.place_cell("I/P", (0, 0), 8, 7, 140, 90, font_size=20,
                    register=False, no_feedback=True, page=PAGE)
    self.place_cell("LOCAL ICP", (1, 0), 164, 7, 180, 90, font_size=18,
                    register=False, no_feedback=True, page=PAGE)
    title = self.place_cell("COLD START\nMANAGER", None, 360, 7, 656, 90,
                            font_size=26, is_variable=True, register=False,
                            no_feedback=True, page=PAGE)
    self._cold_status_cells["title"] = title

    rows = [
        ("state", 114, 90),
        ("engines", 221, 90),
        ("action", 328, 90),
        ("mode", 435, 90),
    ]
    for key, y, h in rows:
        c = self.place_cell("", None, 8, y, 1008, h, font_size=22,
                            is_variable=True, register=False, no_feedback=True,
                            page=PAGE, var_align=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._cold_status_cells[key] = c

    y5, h5 = 542, 50
    buttons = [
        ("START", P_START, 8, 140),
        ("PAUSE", P_PAUSE, 156, 140),
        ("ABORT", P_ABORT, 304, 140),
        ("SKIP", P_SKIP, 452, 120),
        ("DAY", P_DAY, 580, 110),
        ("NIGHT", P_NIGHT, 698, 130),
        ("LAND/CV", P_PROFILE, 836, 180),
    ]
    for text, pos, x, w in buttons:
        cell = self.place_cell(text, pos, x, y5, w, h5, font_size=13,
                               register=False, page=PAGE, bold=True)
        self._cold_cells[pos] = cell

    self._cold_refresh_ui()


def _cold_on_dcs_signal(self, field_name, value):
    """First DCS-BIOS data decides whether startup animation is immediate or deferred."""
    if getattr(self, "_cold_first_mode_decided", False):
        return

    mode = self._cold_detect_startup_mode()
    if mode == STARTUP_MODE_UNKNOWN:
        return

    self._cold_first_mode_decided = True
    if mode == STARTUP_MODE_NON_COLD:
        self._cold_log(f"FIRST DATA RPM={self._cold_left_rpm} NON-COLD: PLAY STARTUP ANIM")
        self._show_page("local_icp")
        self._cold_play_startup_animation(return_page="local_icp")
    else:
        self._cold_log(f"FIRST DATA RPM={self._cold_left_rpm} COLD: DEFER STARTUP ANIM")


def _cold_handle_settings_tap(self) -> bool:
    mode = self._cold_detect_startup_mode()
    if mode != STARTUP_MODE_COLD:
        self._cold_hidden_tap_count = 0
        return False

    now = time.time()
    if now - getattr(self, "_cold_hidden_tap_at", 0.0) > 1.2:
        self._cold_hidden_tap_count = 0
    self._cold_hidden_tap_count += 1
    self._cold_hidden_tap_at = now

    if self._cold_hidden_tap_count >= 3:
        self._cold_hidden_tap_count = 0
        self._cold_detected_mode = STARTUP_MODE_COLD
        self._cold_last_action = "HIDDEN COLD START ENTRY"
        self._show_page(PAGE)
        self._cold_refresh_ui()
        self._cold_log("ENTER COLD PAGE BY SETTINGS x3")
        return True
    return False


def _cold_play_startup_animation(self, return_page: Optional[str] = None, after: Optional[Callable[[], None]] = None):
    overlay = install_startup_overlay(self)
    try:
        overlay.on_dcs_signal("startup_manager", "ready")
    except Exception:
        pass

    hold_ms = int((getattr(overlay, "ready_hold_seconds", 0.9) + 0.25) * 1000)

    def _after_overlay():
        if return_page:
            self._show_page(return_page)
        if after is not None:
            after()

    QTimer.singleShot(hold_ms, _after_overlay)


def _cold_poll_detection(self):
    if getattr(self, "_current_page", None) == PAGE:
        self._cold_detect_startup_mode()
        self._cold_refresh_ui()


def _cold_get_left_rpm(self) -> Optional[float]:
    rpm = _parse_rpm_value(getattr(self, "_cold_left_rpm", None))
    if rpm is not None:
        return rpm
    latest = getattr(getattr(self, "dcs_bios", None), "latest", {}) or {}
    for key in (LEFT_RPM_FIELD, LEFT_RPM_INTERNAL):
        rpm = _parse_rpm_value(latest.get(key))
        if rpm is not None:
            return rpm
    return None


def _cold_detect_startup_mode(self) -> str:
    rpm = self._cold_get_left_rpm()
    self._cold_left_rpm = rpm
    if rpm is None:
        self._cold_detected_mode = STARTUP_MODE_UNKNOWN
        return self._cold_detected_mode
    self._cold_detected_mode = STARTUP_MODE_COLD if rpm < self._cold_rpm_threshold else STARTUP_MODE_NON_COLD
    return self._cold_detected_mode


def _cold_handle_click(self, pos):
    if pos in ((0, 0), (1, 0)):
        self._show_page("local_icp")
        return
    if pos == P_START:
        self._cold_arm_or_continue()
    elif pos == P_PAUSE:
        self._cold_pause()
    elif pos == P_ABORT:
        self._cold_abort()
    elif pos == P_SKIP:
        self._cold_skip()
    elif pos == P_DAY:
        self._cold_set_display_mode("day")
    elif pos == P_NIGHT:
        self._cold_set_display_mode("night")
    elif pos == P_PROFILE:
        self._cold_set_profile("carrier" if self._cold_profile == "land" else "land")
    self._cold_refresh_ui()


def _cold_arm_or_continue(self):
    if self._cold_state in ("idle", "aborted", "complete"):
        mode = self._cold_detect_startup_mode()
        if mode == STARTUP_MODE_UNKNOWN:
            self._cold_enter_hold("WAIT LEFT RPM DATA")
            return
        if mode != STARTUP_MODE_COLD:
            self._cold_enter_hold("DENIED: L RPM >= 60")
            return
        self._cold_state = "armed"
        self._cold_step_index = -1
        self._cold_right_engine_online = False
        self._cold_left_engine_online = False
        self._cold_apu_off = False
        self._cold_display_brightness_applied = False
        self._cold_normal_ufc_locked = True
        self._cold_start_anim_played = False
        self._cold_last_action = "COLD START ARMED / PRESS START AGAIN"
        self._cold_log(f"ARMED COLD RPM={self._cold_left_rpm}")
        return

    if self._cold_state == "armed":
        self._cold_state = "running"
        self._cold_step_index = 0
        self._cold_log("RUN COLD START")
        self._cold_run_next_step()
        return

    if self._cold_state == "paused":
        self._cold_state = "running"
        self._cold_log("RESUME")
        self._cold_run_next_step()
        return

    if self._cold_state == "hold":
        self._cold_state = "running"
        self._cold_log("CONTINUE")
        self._cold_step_index += 1
        self._cold_run_next_step()
        return

    if self._cold_state == "wait_user":
        self._cold_state = "running"
        self._cold_log("USER CONFIRM")
        self._cold_step_index += 1
        self._cold_run_next_step()
        return

    if self._cold_state == "select_display":
        self._cold_state = "running"
        self._cold_step_index += 1
        self._cold_run_next_step()
        return


def _cold_step_list(self):
    return [
        ("BATTERY ON", "send", "battery_on"),
        ("APU START", "send", "apu_start"),
        ("CONFIRM APU READY", "user", "APU READY? PRESS START"),
        ("RIGHT ENGINE CRANK", "send", "right_engine_crank"),
        ("SET RIGHT THROTTLE IDLE", "user", "SET R THROTTLE IDLE, THEN START"),
        ("CONFIRM RIGHT ENGINE STABLE", "flag_right", "R ENGINE STABLE CONFIRMED"),
        ("LEFT ENGINE CRANK", "send", "left_engine_crank"),
        ("SET LEFT THROTTLE IDLE", "user", "SET L THROTTLE IDLE, THEN START"),
        ("CONFIRM LEFT ENGINE STABLE", "flag_left", "L ENGINE STABLE CONFIRMED"),
        ("APU OFF", "apu_off", "apu_off"),
        ("CLOSE CANOPY", "supervised", "canopy_close"),
        ("BLEED AIR PULL ROTATE 360", "supervised", "bleed_air_cycle"),
        ("TRIM RESET", "supervised", "trim_reset"),
        ("FCS RESET", "supervised", "fcs_reset"),
        ("ECM RECEIVE", "supervised", "ecm_receive"),
        ("MANUAL IFF ON", "user", "OPEN IFF MANUALLY, THEN START"),
        ("SELECT DISPLAY MODE", "select_display", "SELECT DAY OR NIGHT"),
        ("APPLY DISPLAY BRIGHTNESS", "display_brightness", ""),
        ("LOCAL ICP READY", "unlock", ""),
        ("INS MODE", "ins", ""),
        ("COMPLETE", "complete", ""),
    ]


def _cold_run_next_step(self):
    if self._cold_state != "running":
        return

    steps = self._cold_step_list()
    self._cold_total_steps = len(steps) - 1

    if self._cold_step_index >= len(steps):
        self._cold_state = "complete"
        self._cold_last_action = "COLD START COMPLETE"
        self._cold_refresh_ui()
        return

    title, kind, payload = steps[self._cold_step_index]
    self._cold_last_action = title
    self._cold_refresh_ui()

    if kind == "send":
        self._cold_send_configured_async(payload, lambda: _cold_advance_if_running(self))
    elif kind == "supervised":
        self._cold_last_action = f"SUPERVISE {title}"
        self._cold_refresh_ui()
        self._cold_send_configured_async(payload, lambda: _cold_advance_if_running(self))
    elif kind == "user":
        self._cold_state = "wait_user"
        self._cold_last_action = str(payload)
    elif kind == "flag_right":
        self._cold_right_engine_online = True
        self._cold_last_action = "R ENGINE STABLE / PLAY UFC STARTUP ANIM"
        self._cold_state = "animating"
        self._cold_refresh_ui()

        def _after_right_anim():
            self._show_page(PAGE)
            self._cold_start_anim_played = True
            self._cold_state = "running"
            self._cold_step_index += 1
            self._cold_run_next_step()

        self._cold_play_startup_animation(return_page=PAGE, after=_after_right_anim)
    elif kind == "flag_left":
        self._cold_left_engine_online = True
        self._cold_last_action = "BOTH ENGINES STABLE"
        QTimer.singleShot(500, lambda: _cold_advance_if_running(self))
    elif kind == "apu_off":
        def _after_apu_off():
            self._cold_apu_off = True
            _cold_advance_if_running(self)
        self._cold_send_configured_async(payload, _after_apu_off)
    elif kind == "select_display":
        self._cold_state = "select_display"
        self._cold_last_action = "SELECT DAY OR NIGHT, THEN START"
    elif kind == "display_brightness":
        self._cold_apply_display_brightness()
        QTimer.singleShot(700, lambda: _cold_advance_if_running(self))
    elif kind == "unlock":
        self._cold_unlock_local_icp()
        QTimer.singleShot(700, lambda: _cold_advance_if_running(self))
    elif kind == "ins":
        self._cold_send_configured_async(
            "ins_carrier" if self._cold_profile == "carrier" else "ins_land",
            lambda: _cold_advance_if_running(self),
        )
    elif kind == "complete":
        self._cold_state = "complete"
        self._cold_last_action = "COLD START COMPLETE"
        self._cold_refresh_ui()


def _cold_advance_if_running(self):
    if getattr(self, "_cold_state", None) == "running":
        self._cold_step_index += 1
        self._cold_run_next_step()


def _cold_enter_hold(self, reason: str):
    self._cold_sequence_token += 1
    self._cold_state = "hold"
    self._cold_hold_reason = reason
    self._cold_last_action = f"HOLD: {reason}"
    self._cold_log(self._cold_last_action)
    self._cold_refresh_ui()


def _cold_abort(self):
    self._cold_sequence_token += 1
    self._cold_state = "aborted"
    self._cold_last_action = "ABORTED"
    self._cold_log("ABORTED")
    self._cold_refresh_ui()


def _cold_pause(self):
    if self._cold_state in ("running", "wait_user", "select_display", "animating"):
        self._cold_sequence_token += 1
        self._cold_state = "paused"
        self._cold_last_action = "PAUSED"
        self._cold_log("PAUSED")
        self._cold_refresh_ui()


def _cold_skip(self):
    if self._cold_state in ("running", "wait_user", "hold", "select_display", "paused"):
        self._cold_sequence_token += 1
        self._cold_state = "running"
        self._cold_step_index += 1
        self._cold_log("SKIP")
        self._cold_run_next_step()


def _cold_set_display_mode(self, mode: str):
    mode = str(mode).lower()
    if mode not in ("day", "night"):
        return
    self._cold_display_mode = mode
    cfg = load_config()
    cfg["cold_start_display_mode"] = mode
    save_config(cfg)
    self._cold_last_action = f"DISPLAY MODE {mode.upper()}"
    self._cold_log(self._cold_last_action)


def _cold_set_profile(self, profile: str):
    profile = str(profile).lower()
    if profile not in ("land", "carrier"):
        return
    self._cold_profile = profile
    cfg = load_config()
    cfg["cold_start_profile"] = profile
    save_config(cfg)
    self._cold_last_action = f"PROFILE {profile.upper()}"
    self._cold_log(self._cold_last_action)


def _cold_entries_from_config(self, key: str) -> List[Dict[str, Any]]:
    cfg = _merged_config()
    item = cfg.get("cold_start_controls", {}).get(key, {})
    if not isinstance(item, dict):
        self._cold_log(f"{key}: INVALID CONFIG")
        self._cold_last_action = f"{self._cold_last_action} / BAD CFG"
        return []

    raw_sequence = item.get("sequence")
    if isinstance(raw_sequence, list):
        entries: List[Dict[str, Any]] = []
        for raw in raw_sequence:
            if not isinstance(raw, dict):
                continue
            repeat = max(1, int(raw.get("repeat", 1) or 1))
            for _ in range(repeat):
                entries.append({
                    "id": raw.get("id", ""),
                    "value": raw.get("value", raw.get("command", "")),
                    "delay_ms": max(0, int(raw.get("delay_ms", 0) or 0)),
                })
        return entries

    return [{
        "id": item.get("id", ""),
        "value": item.get("value", item.get("command", "")),
        "delay_ms": max(0, int(item.get("delay_ms", 500) or 0)),
    }]


def _cold_send_configured(self, key: str) -> bool:
    sent = False
    for entry in self._cold_entries_from_config(key):
        ident = str(entry.get("id", "") or "").strip()
        if not ident:
            self._cold_log(f"{key}: NO ID")
            self._cold_last_action = f"{self._cold_last_action} / NO ID"
            continue
        value = entry.get("value", "")
        ok = send_dcs_bios(ident, value)
        sent = sent or ok
        self._cold_log(f"{key}: {ident} {value} {'OK' if ok else 'FAIL'}")
        if not ok:
            self._cold_enter_hold(f"{key} SEND FAILED")
            return False
    return sent


def _cold_send_configured_async(self, key: str, done: Callable[[], None]) -> None:
    entries = self._cold_entries_from_config(key)
    self._cold_sequence_token += 1
    token = self._cold_sequence_token
    if not entries:
        QTimer.singleShot(0, done)
        return
    self._cold_run_sequence_entries(key, entries, 0, token, done)


def _cold_run_sequence_entries(self, key: str, entries: List[Dict[str, Any]], index: int, token: int, done: Callable[[], None]) -> None:
    if token != getattr(self, "_cold_sequence_token", None):
        return
    if getattr(self, "_cold_state", None) != "running":
        return
    if index >= len(entries):
        done()
        return

    entry = entries[index]
    ident = str(entry.get("id", "") or "").strip()
    delay_ms = max(0, int(entry.get("delay_ms", 0) or 0))
    if not ident:
        self._cold_log(f"{key}: NO ID")
        self._cold_last_action = f"{self._cold_last_action} / NO ID"
        self._cold_refresh_ui()
        QTimer.singleShot(delay_ms, lambda: self._cold_run_sequence_entries(key, entries, index + 1, token, done))
        return

    value = entry.get("value", "")
    ok = send_dcs_bios(ident, value)
    self._cold_log(f"{key}: {ident} {value} {'OK' if ok else 'FAIL'}")
    if not ok:
        self._cold_enter_hold(f"{key} SEND FAILED")
        return
    QTimer.singleShot(delay_ms, lambda: self._cold_run_sequence_entries(key, entries, index + 1, token, done))


def _cold_apply_display_brightness(self):
    cfg = _merged_config()
    presets = cfg.get("display_brightness_presets", DEFAULT_DISPLAY_PRESETS)
    preset = presets.get(self._cold_display_mode, DEFAULT_DISPLAY_PRESETS["day"])
    controls = cfg.get("cold_start_controls", {})

    labels = {"lddi": "LDDI", "rddi": "RDDI", "ampcd": "AMPCD", "hud": "HUD"}
    results = []

    for target in ("lddi", "rddi", "ampcd", "hud"):
        item = controls.get(f"display_{target}_select", {})
        ident = str(item.get("id", "") or "").strip() if isinstance(item, dict) else ""
        if not ident:
            continue
        value = item.get(f"{self._cold_display_mode}_value", item.get("value", ""))
        ok = send_dcs_bios(ident, value)
        results.append(f"{labels[target]} SEL {'OK' if ok else 'FAIL'}")

    for target in ("lddi", "rddi", "ampcd", "hud"):
        percent = int(preset.get(target, 0))
        item = controls.get(f"display_{target}", {})
        ident = str(item.get("id", "") or "").strip() if isinstance(item, dict) else ""
        value_type = item.get("value_type", "analog") if isinstance(item, dict) else "analog"
        if not ident:
            results.append(f"{labels[target]} {percent}% NO ID")
            continue
        value = _pct_to_bios(percent) if value_type == "analog" else percent
        ok = send_dcs_bios(ident, value)
        results.append(f"{labels[target]} {percent}% {'OK' if ok else 'FAIL'}")
    self._cold_display_brightness_applied = True
    self._cold_last_action = " / ".join(results)


def _cold_unlock_local_icp(self):
    self._cold_normal_ufc_locked = not (
        self._cold_right_engine_online
        and self._cold_left_engine_online
        and self._cold_apu_off
        and self._cold_display_brightness_applied
    )
    if self._cold_normal_ufc_locked:
        self._cold_enter_hold("UFC LOCK CONDITIONS NOT MET")
        return
    self._cold_last_action = "UFC ONLINE / LOCAL ICP READY"


def _cold_status_lines(self):
    state = getattr(self, "_cold_state", "idle").upper()
    idx = getattr(self, "_cold_step_index", -1)
    total = getattr(self, "_cold_total_steps", 0)
    step_txt = "--" if idx < 0 else f"{idx:02d}/{total:02d}"
    profile = getattr(self, "_cold_profile", "land").upper()
    mode = getattr(self, "_cold_display_mode", "day").upper()
    detected = getattr(self, "_cold_detected_mode", STARTUP_MODE_UNKNOWN)
    rpm = getattr(self, "_cold_left_rpm", None)
    rpm_txt = "---" if rpm is None else f"{rpm:.0f}%"
    start_mode_txt = {
        STARTUP_MODE_COLD: "COLD ACCESS OK",
        STARTUP_MODE_NON_COLD: "MAIN ONLY",
        STARTUP_MODE_UNKNOWN: "DETECTING",
    }.get(detected, "DETECTING")
    r_eng = "STABLE" if getattr(self, "_cold_right_engine_online", False) else "OFF/START"
    l_eng = "STABLE" if getattr(self, "_cold_left_engine_online", False) else "OFF/START"
    apu = "OFF" if getattr(self, "_cold_apu_off", False) else "ON/REQ"
    ufc = "READY" if not getattr(self, "_cold_normal_ufc_locked", True) else (
        "STANDBY" if getattr(self, "_cold_right_engine_online", False) else "LOCKED"
    )
    return {
        "state": f"STATE {state:<12} STEP {step_txt:<6} PROFILE {profile}",
        "engines": f"L RPM {rpm_txt:<5} {start_mode_txt:<14} THRESH {self._cold_rpm_threshold:.0f}%",
        "action": f"ACTION {getattr(self, '_cold_last_action', 'READY')}",
        "mode": f"R ENG {r_eng:<9} L ENG {l_eng:<9} APU {apu:<8} UFC {ufc} DISPLAY {mode}",
    }


def _cold_refresh_ui(self):
    cells = getattr(self, "_cold_status_cells", {})
    if not cells:
        return
    lines = self._cold_status_lines()
    for key, text in lines.items():
        self._cold_set_cell(key, text)


def _cold_set_cell(self, key: str, text: str):
    cell = getattr(self, "_cold_status_cells", {}).get(key)
    if not cell:
        return
    cell._var_text = text
    cell.update()


def _cold_log(self, message: str):
    ts = time.strftime("%H:%M:%S", time.localtime())
    try:
        self._key_press_log.append((ts, f"COLD:{message}"))
        if len(self._key_press_log) > 50:
            self._key_press_log.pop(0)
        self.keyLogUpdated.emit(ts, f"COLD:{message}")
    except Exception:
        pass
