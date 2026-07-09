# -*- coding: utf-8 -*-
"""Minimal cold-start page and DCS-session lifecycle override.

Design goals for this layer:
- The cold-start page is a concise checklist screen, not a diagnostic dashboard.
- L/R engine RPM display is live/fresh IFEI telemetry only.
- APU START is followed by a mandatory 5-second interval before the right-engine
  start path can continue.
- Automatic execution, wait states, and user confirmations are shown clearly.
- DCS-BIOS timeout / mission exit resets all checklist progress. Step index and
  current action are not persisted across missions.
"""
from __future__ import annotations

import time
from typing import Callable, Optional, Tuple

from PyQt6.QtCore import Qt, QTimer

from ufc.cold_start import (
    LEFT_RPM_INTERNAL,
    PAGE,
    RIGHT_RPM_INTERNAL,
    STARTUP_MODE_COLD,
    STARTUP_MODE_NON_COLD,
    STARTUP_MODE_UNKNOWN,
)
from ufc.config import load_config, save_config
from ufc.startup import install_startup_overlay

MIN_STARTUP_ANIM_MS = 5000
APU_TO_RIGHT_CRANK_MS = 5000

P_START = (300, 0)
P_PAUSE = (300, 1)
P_SKIP = (300, 3)
P_ABORT = (300, 2)
P_DAY = (300, 4)
P_NIGHT = (300, 5)
P_PROFILE = (300, 6)


def install_cold_direct_entry(UFCKeypadWindowClass) -> None:
    """Override cold-start entry, page, state reset, and execution UI."""
    if getattr(UFCKeypadWindowClass, "_cold_direct_entry_installed", False):
        return
    UFCKeypadWindowClass._cold_direct_entry_installed = True

    previous_update_display = UFCKeypadWindowClass._update_display
    previous_check_dcs_timeout = UFCKeypadWindowClass._check_dcs_timeout

    def _cold_reset_progress(self, reason: str = "RESET") -> None:
        """Clear transient checklist progress. Nothing here is persisted."""
        self._cold_state = "idle"
        self._cold_step_index = -1
        self._cold_total_steps = 0
        self._cold_hold_reason = ""
        self._cold_sequence_token = getattr(self, "_cold_sequence_token", 0) + 1
        self._cold_right_engine_online = False
        self._cold_left_engine_online = False
        self._cold_apu_off = False
        self._cold_display_brightness_applied = False
        self._cold_normal_ufc_locked = True
        self._cold_start_anim_played = False
        self._cold_ui_powered = False
        self._cold_exec_phase = "IDLE"
        self._cold_last_action = "READY"
        self._cold_step_detail = "Press START twice to run cold-start checklist."
        try:
            self._cold_log(f"PROGRESS RESET: {reason}")
        except Exception:
            pass

    def _cold_reset_session_state(self, reason: str) -> None:
        """Clear mission/session state after DCS-BIOS timeout or mission switch."""
        self._cold_first_mode_decided = False
        self._cold_dcs_seen = False
        self._cold_detected_mode = STARTUP_MODE_UNKNOWN
        self._cold_left_rpm = None
        self._cold_right_rpm = None
        self._cold_left_rpm_fresh = False
        self._cold_right_rpm_fresh = False
        self._cold_hidden_tap_count = 0
        self._cold_hidden_tap_at = 0.0
        self._cold_reset_progress(reason)
        self._cold_exec_phase = "WAIT DCS"
        self._cold_last_action = "WAITING FOR DCS-BIOS"
        self._cold_step_detail = "US NAVY / waiting for DCS-BIOS."
        latest = getattr(getattr(self, "dcs_bios", None), "latest", {}) or {}
        for key in ("IFEI_RPM_L", "IFEI_RPM_R", LEFT_RPM_INTERNAL, RIGHT_RPM_INTERNAL):
            latest.pop(key, None)
        try:
            self._cold_log(f"SESSION RESET: {reason}")
        except Exception:
            pass

    def _cold_get_fresh_rpms(self) -> Tuple[Optional[float], Optional[float]]:
        left = getattr(self, "_cold_left_rpm", None) if getattr(self, "_cold_left_rpm_fresh", False) else None
        right = getattr(self, "_cold_right_rpm", None) if getattr(self, "_cold_right_rpm_fresh", False) else None
        return left, right

    def _cold_detect_startup_mode_fresh(self) -> str:
        left, right = self._cold_get_fresh_rpms()
        values = [v for v in (left, right) if v is not None]
        if values and max(values) >= self._cold_rpm_threshold:
            self._cold_detected_mode = STARTUP_MODE_NON_COLD
        elif left is not None and right is not None and left < self._cold_rpm_threshold and right < self._cold_rpm_threshold:
            self._cold_detected_mode = STARTUP_MODE_COLD
        else:
            self._cold_detected_mode = STARTUP_MODE_UNKNOWN
        return self._cold_detected_mode

    def _cold_all_fresh_known_below_threshold(self) -> bool:
        left, right = self._cold_get_fresh_rpms()
        return (
            left is not None
            and right is not None
            and left < self._cold_rpm_threshold
            and right < self._cold_rpm_threshold
        )

    def _cold_max_fresh_rpm(self) -> Optional[float]:
        values = [v for v in self._cold_get_fresh_rpms() if v is not None]
        return max(values) if values else None

    def _init_cold_start_page(self):
        """Create a minimal cold-start checklist page."""
        self._cold_cells = {}
        self._cold_status_cells = {}

        title = self.place_cell("F/A-18C COLD START", None, 8, 12, 1008, 76,
                                font_size=30, is_variable=True, register=False,
                                no_feedback=True, page=PAGE)
        self._cold_status_cells["title"] = title

        rpm = self.place_cell("", None, 8, 106, 1008, 82,
                              font_size=28, is_variable=True, register=False,
                              no_feedback=True, page=PAGE,
                              var_align=Qt.AlignmentFlag.AlignCenter)
        self._cold_status_cells["rpm"] = rpm

        step = self.place_cell("", None, 8, 212, 1008, 110,
                               font_size=27, is_variable=True, register=False,
                               no_feedback=True, page=PAGE,
                               var_align=Qt.AlignmentFlag.AlignCenter)
        self._cold_status_cells["step"] = step

        hint = self.place_cell("", None, 8, 342, 1008, 94,
                               font_size=22, is_variable=True, register=False,
                               no_feedback=True, page=PAGE,
                               var_align=Qt.AlignmentFlag.AlignCenter)
        self._cold_status_cells["hint"] = hint

        status = self.place_cell("", None, 8, 456, 1008, 44,
                                 font_size=15, is_variable=True, register=False,
                                 no_feedback=True, page=PAGE,
                                 var_align=Qt.AlignmentFlag.AlignCenter)
        self._cold_status_cells["status"] = status

        y, h = 526, 62
        buttons = [
            ("START", P_START, 8, 176),
            ("PAUSE", P_PAUSE, 192, 118),
            ("SKIP", P_SKIP, 318, 108),
            ("ABORT", P_ABORT, 434, 128),
            ("DAY", P_DAY, 570, 96),
            ("NIGHT", P_NIGHT, 674, 116),
            ("LAND/CV", P_PROFILE, 798, 218),
        ]
        for text, pos, x, w in buttons:
            cell = self.place_cell(text, pos, x, y, w, h, font_size=13,
                                   register=False, page=PAGE, bold=True)
            self._cold_cells[pos] = cell
        self._cold_refresh_ui()

    def _update_display(self, field_name, value):
        if field_name == LEFT_RPM_INTERNAL:
            self._cold_left_rpm_fresh = True
        elif field_name == RIGHT_RPM_INTERNAL:
            self._cold_right_rpm_fresh = True
        previous_update_display(self, field_name, value)
        if field_name in (LEFT_RPM_INTERNAL, RIGHT_RPM_INTERNAL) and getattr(self, "_current_page", None) == PAGE:
            self._cold_refresh_ui()

    def _check_dcs_timeout(self):
        was_disconnected = getattr(self, "_dcs_disconnected", False)
        previous_check_dcs_timeout(self)
        now_disconnected = getattr(self, "_dcs_disconnected", False)
        if now_disconnected and not was_disconnected:
            self._cold_reset_session_state("DCS-BIOS TIMEOUT")
            self._cold_install_wait_logo()
            self._cold_refresh_ui()

    def _cold_on_dcs_signal(self, field_name, value):
        if not getattr(self, "_cold_dcs_seen", False):
            self._cold_dcs_seen = True
            self._cold_hide_wait_logo()
            self._cold_exec_phase = "CHECK"
            self._cold_last_action = "CHECK AIRCRAFT"
            self._cold_step_detail = "Waiting for fresh engine RPM."
            self._cold_log(f"DCS-BIOS FIRST SIGNAL {field_name}")

        if getattr(self, "_cold_first_mode_decided", False):
            return

        mode = self._cold_detect_startup_mode()
        if mode == STARTUP_MODE_UNKNOWN:
            self._cold_exec_phase = "CHECK"
            self._cold_last_action = "WAIT RPM"
            self._cold_step_detail = "Need fresh L/R RPM from this mission."
            if getattr(self, "_current_page", None) != PAGE:
                self._show_page(PAGE)
            self._cold_refresh_ui()
            return

        self._cold_first_mode_decided = True
        if mode == STARTUP_MODE_NON_COLD:
            left, right = self._cold_get_fresh_rpms()
            self._cold_exec_phase = "HOT"
            self._cold_last_action = "UFC STARTUP"
            self._cold_step_detail = "Engine online. Starting LOCAL ICP."
            self._cold_log(f"FIRST FRESH RPM L={left} R={right}: LOCAL ICP")
            self._show_page("local_icp")
            self._cold_play_startup_animation(return_page="local_icp")
        else:
            left, right = self._cold_get_fresh_rpms()
            self._cold_reset_progress("AUTO COLD ENTRY")
            self._cold_exec_phase = "COLD"
            self._cold_last_action = "COLD START READY"
            self._cold_step_detail = "Press START twice."
            self._show_page(PAGE)
            self._cold_refresh_ui()
            self._cold_log(f"FIRST FRESH RPM L={left} R={right}: AUTO COLD PAGE")

    def _cold_handle_settings_tap(self) -> bool:
        if not self._cold_all_known_below_threshold():
            self._cold_hidden_tap_count = 0
            return False
        now = time.time()
        if now - getattr(self, "_cold_hidden_tap_at", 0.0) > 1.2:
            self._cold_hidden_tap_count = 0
        self._cold_hidden_tap_count += 1
        self._cold_hidden_tap_at = now
        if self._cold_hidden_tap_count >= 3:
            self._cold_hidden_tap_count = 0
            self._cold_reset_progress("HIDDEN ENTRY")
            self._cold_detected_mode = STARTUP_MODE_COLD
            self._cold_exec_phase = "COLD"
            self._cold_last_action = "COLD START READY"
            self._cold_step_detail = "Press START twice."
            self._show_page(PAGE)
            self._cold_refresh_ui()
            self._cold_log("ENTER COLD PAGE BY SETTINGS x3")
            return True
        return False

    def _cold_arm_or_continue(self):
        if self._cold_state in ("idle", "aborted", "complete"):
            if not self._cold_all_known_below_threshold():
                self._cold_enter_hold("ENGINE RPM NOT COLD")
                return
            self._cold_reset_progress("ARM")
            self._cold_state = "armed"
            self._cold_exec_phase = "ARMED"
            self._cold_last_action = "ARMED"
            self._cold_step_detail = "Press START again."
            self._cold_log(f"ARMED COLD L={self._cold_left_rpm} R={self._cold_right_rpm}")
            self._cold_refresh_ui()
            return
        if self._cold_state == "armed":
            self._cold_state = "running"
            self._cold_step_index = 0
            self._cold_exec_phase = "EXEC"
            self._cold_log("RUN COLD START")
            self._cold_run_next_step()
            return
        if self._cold_state in ("paused", "hold"):
            self._cold_state = "running"
            self._cold_exec_phase = "EXEC"
            self._cold_step_index += 1 if self._cold_state == "hold" else 0
            self._cold_log("CONTINUE")
            self._cold_run_next_step()
            return
        if self._cold_state in ("wait_user", "select_display"):
            self._cold_state = "running"
            self._cold_exec_phase = "EXEC"
            self._cold_log("USER CONFIRM")
            self._cold_step_index += 1
            self._cold_run_next_step()
            return

    def _cold_step_list(self):
        return [
            ("BATTERY ON", "send", "battery_on", "Auto command."),
            ("APU START", "send", "apu_start", "Auto command."),
            ("APU WAIT", "timer", APU_TO_RIGHT_CRANK_MS, "Wait 5 seconds before right engine."),
            ("APU READY?", "user", "", "Confirm APU ready, then START."),
            ("RIGHT CRANK", "send", "right_engine_crank", "Auto command."),
            ("RIGHT IDLE", "user", "", "Set right throttle IDLE, then START."),
            ("RIGHT STABLE?", "flag_right", "", "Confirm right engine stable."),
            ("LEFT CRANK", "send", "left_engine_crank", "Auto command."),
            ("LEFT IDLE", "user", "", "Set left throttle IDLE, then START."),
            ("LEFT STABLE?", "flag_left", "", "Confirm left engine stable."),
            ("APU OFF", "apu_off", "apu_off", "Auto command."),
            ("CANOPY CLOSE", "supervised", "canopy_close", "Program executes; monitor cockpit."),
            ("BLEED AIR", "supervised", "bleed_air_cycle", "Program executes; monitor cockpit."),
            ("TRIM RESET", "supervised", "trim_reset", "Program executes; monitor cockpit."),
            ("FCS RESET", "supervised", "fcs_reset", "Program executes; monitor cockpit."),
            ("ECM REC", "supervised", "ecm_receive", "Program executes; monitor cockpit."),
            ("IFF MANUAL", "user", "", "Open IFF manually, then START."),
            ("DISPLAY MODE", "select_display", "", "Select DAY/NIGHT, then START."),
            ("BRIGHTNESS", "display_brightness", "", "Apply display preset."),
            ("LOCAL ICP", "unlock", "", "Verify LOCAL ICP ready."),
            ("INS", "ins", "", "Set INS profile."),
            ("COMPLETE", "complete", "", "Done."),
        ]

    def _cold_run_next_step(self):
        if self._cold_state != "running":
            return
        steps = self._cold_step_list()
        self._cold_total_steps = len(steps)
        if self._cold_step_index >= len(steps):
            self._cold_state = "complete"
            self._cold_exec_phase = "DONE"
            self._cold_last_action = "COMPLETE"
            self._cold_step_detail = "Cold start complete."
            self._cold_refresh_ui()
            return

        title, kind, payload, hint = steps[self._cold_step_index]
        self._cold_last_action = title
        self._cold_step_detail = hint
        self._cold_exec_phase = "EXEC"
        self._cold_refresh_ui()

        def advance_if_running():
            if getattr(self, "_cold_state", None) == "running":
                self._cold_step_index += 1
                self._cold_run_next_step()

        if kind in ("send", "supervised"):
            self._cold_exec_phase = "EXEC"
            self._cold_refresh_ui()
            self._cold_send_configured_async(payload, advance_if_running)
        elif kind == "timer":
            self._cold_exec_phase = "WAIT"
            self._cold_refresh_ui()
            QTimer.singleShot(int(payload), advance_if_running)
        elif kind == "user":
            self._cold_state = "wait_user"
            self._cold_exec_phase = "USER"
            self._cold_refresh_ui()
        elif kind == "flag_right":
            self._cold_right_engine_online = True
            self._cold_state = "animating"
            self._cold_exec_phase = "UFC BOOT"
            self._cold_last_action = "UFC STARTUP"
            self._cold_step_detail = "Playing 5s UFC animation."
            self._cold_refresh_ui()

            def after_right_anim():
                self._show_page(PAGE)
                self._cold_start_anim_played = True
                self._cold_ui_powered = True
                self._cold_state = "running"
                self._cold_step_index += 1
                self._cold_run_next_step()

            self._cold_play_startup_animation(return_page=PAGE, after=after_right_anim)
        elif kind == "flag_left":
            self._cold_left_engine_online = True
            self._cold_exec_phase = "EXEC"
            self._cold_step_detail = "Left engine confirmed."
            self._cold_refresh_ui()
            QTimer.singleShot(500, advance_if_running)
        elif kind == "apu_off":
            def after_apu_off():
                self._cold_apu_off = True
                advance_if_running()
            self._cold_send_configured_async(payload, after_apu_off)
        elif kind == "select_display":
            self._cold_state = "select_display"
            self._cold_exec_phase = "USER"
            self._cold_refresh_ui()
        elif kind == "display_brightness":
            self._cold_apply_display_brightness()
            QTimer.singleShot(700, advance_if_running)
        elif kind == "unlock":
            self._cold_unlock_local_icp()
            QTimer.singleShot(700, advance_if_running)
        elif kind == "ins":
            self._cold_send_configured_async(
                "ins_carrier" if self._cold_profile == "carrier" else "ins_land",
                advance_if_running,
            )
        elif kind == "complete":
            self._cold_state = "complete"
            self._cold_exec_phase = "DONE"
            self._cold_last_action = "COMPLETE"
            self._cold_step_detail = "Cold start complete."
            self._cold_refresh_ui()

    def _cold_pause(self):
        if self._cold_state in ("running", "wait_user", "select_display", "animating"):
            self._cold_sequence_token += 1
            self._cold_state = "paused"
            self._cold_exec_phase = "PAUSE"
            self._cold_last_action = "PAUSED"
            self._cold_step_detail = "Press START to resume."
            self._cold_log("PAUSED")
            self._cold_refresh_ui()

    def _cold_abort(self):
        self._cold_reset_progress("ABORT")
        self._cold_state = "aborted"
        self._cold_exec_phase = "ABORT"
        self._cold_last_action = "ABORTED"
        self._cold_step_detail = "Progress cleared. Press START twice to run again."
        self._cold_log("ABORTED")
        self._cold_refresh_ui()

    def _cold_enter_hold(self, reason: str):
        self._cold_sequence_token += 1
        self._cold_state = "hold"
        self._cold_hold_reason = reason
        self._cold_exec_phase = "HOLD"
        self._cold_last_action = f"HOLD: {reason}"
        self._cold_step_detail = "Press START to continue if safe."
        self._cold_log(self._cold_last_action)
        self._cold_refresh_ui()

    def _cold_set_display_mode(self, mode: str):
        mode = str(mode).lower()
        if mode not in ("day", "night"):
            return
        self._cold_display_mode = mode
        cfg = load_config()
        cfg["cold_start_display_mode"] = mode
        save_config(cfg)
        self._cold_last_action = f"DISPLAY {mode.upper()}"
        self._cold_step_detail = "Display mode selected."
        self._cold_log(self._cold_last_action)
        self._cold_refresh_ui()

    def _cold_set_profile(self, profile: str):
        profile = str(profile).lower()
        if profile not in ("land", "carrier"):
            return
        self._cold_profile = profile
        cfg = load_config()
        cfg["cold_start_profile"] = profile
        save_config(cfg)
        self._cold_last_action = f"PROFILE {profile.upper()}"
        self._cold_step_detail = "Startup profile selected."
        self._cold_log(self._cold_last_action)
        self._cold_refresh_ui()

    def _cold_status_lines(self):
        steps = self._cold_step_list()
        idx = getattr(self, "_cold_step_index", -1)
        total = len(steps)
        left, right = self._cold_get_fresh_rpms()
        l_txt = "---" if left is None else f"{left:05.1f}%"
        r_txt = "---" if right is None else f"{right:05.1f}%"
        if idx < 0:
            step_txt = "STEP --/--"
        else:
            step_txt = f"STEP {idx + 1:02d}/{total:02d}"
        phase = getattr(self, "_cold_exec_phase", "IDLE")
        action = getattr(self, "_cold_last_action", "READY")
        hint = getattr(self, "_cold_step_detail", "")
        profile = getattr(self, "_cold_profile", "land").upper()
        display = getattr(self, "_cold_display_mode", "day").upper()
        return {
            "title": "F/A-18C COLD START",
            "rpm": f"L {l_txt}        R {r_txt}",
            "step": f"{step_txt}    {action}",
            "hint": f"{phase}: {hint}",
            "status": f"PROFILE {profile}    DISPLAY {display}    PROGRESS NOT SAVED",
        }

    def _cold_refresh_ui(self):
        cells = getattr(self, "_cold_status_cells", {})
        if not cells:
            return
        lines = self._cold_status_lines()
        for key, text in lines.items():
            self._cold_set_cell(key, text)

    def _cold_play_startup_animation(self, return_page: Optional[str] = None, after: Optional[Callable[[], None]] = None):
        overlay = install_startup_overlay(self)
        hold_seconds = MIN_STARTUP_ANIM_MS / 1000.0
        try:
            overlay.ready_hold_seconds = max(float(getattr(overlay, "ready_hold_seconds", 0.0)), hold_seconds)
        except Exception:
            pass
        try:
            overlay.on_dcs_signal("startup_manager", "ready")
        except Exception:
            pass
        overlay_hold_ms = int((getattr(overlay, "ready_hold_seconds", hold_seconds) + 0.25) * 1000)
        hold_ms = max(MIN_STARTUP_ANIM_MS, overlay_hold_ms)

        def after_overlay_finish():
            try:
                overlay.finish()
            except Exception:
                try:
                    overlay.hide()
                    overlay.deleteLater()
                except Exception:
                    pass
            if return_page:
                self._show_page(return_page)
            if after is not None:
                after()

        QTimer.singleShot(hold_ms, after_overlay_finish)

    UFCKeypadWindowClass._cold_reset_progress = _cold_reset_progress
    UFCKeypadWindowClass._cold_reset_session_state = _cold_reset_session_state
    UFCKeypadWindowClass._cold_get_fresh_rpms = _cold_get_fresh_rpms
    UFCKeypadWindowClass._cold_detect_startup_mode = _cold_detect_startup_mode_fresh
    UFCKeypadWindowClass._cold_all_known_below_threshold = _cold_all_fresh_known_below_threshold
    UFCKeypadWindowClass._cold_max_rpm = _cold_max_fresh_rpm
    UFCKeypadWindowClass._init_cold_start_page = _init_cold_start_page
    UFCKeypadWindowClass._update_display = _update_display
    UFCKeypadWindowClass._check_dcs_timeout = _check_dcs_timeout
    UFCKeypadWindowClass._cold_on_dcs_signal = _cold_on_dcs_signal
    UFCKeypadWindowClass._cold_handle_settings_tap = _cold_handle_settings_tap
    UFCKeypadWindowClass._cold_arm_or_continue = _cold_arm_or_continue
    UFCKeypadWindowClass._cold_step_list = _cold_step_list
    UFCKeypadWindowClass._cold_run_next_step = _cold_run_next_step
    UFCKeypadWindowClass._cold_pause = _cold_pause
    UFCKeypadWindowClass._cold_abort = _cold_abort
    UFCKeypadWindowClass._cold_enter_hold = _cold_enter_hold
    UFCKeypadWindowClass._cold_set_display_mode = _cold_set_display_mode
    UFCKeypadWindowClass._cold_set_profile = _cold_set_profile
    UFCKeypadWindowClass._cold_status_lines = _cold_status_lines
    UFCKeypadWindowClass._cold_refresh_ui = _cold_refresh_ui
    UFCKeypadWindowClass._cold_play_startup_animation = _cold_play_startup_animation
