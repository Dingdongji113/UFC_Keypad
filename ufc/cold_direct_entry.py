# -*- coding: utf-8 -*-
"""Minimal cold-start setup/checklist page and DCS-session lifecycle override.

Current UI rule:
- DAY/NIGHT and LAND/CV are selected on a separate setup screen before the cold
  checklist is unlocked.
- Setup requires two START confirmations.
- The checklist screen has one large centered START button and one smaller RESET
  button in the lower right.
- PAUSE / SKIP / ABORT are intentionally removed from the cold-start page.
- Non-button text is rendered as plain labels with no boxes/frames.
- RESET requires two consecutive taps; it returns to setup while preserving the
  current checklist step/progress.
- DCS-BIOS timeout / mission exit resets all checklist progress.
"""
from __future__ import annotations

import time
from typing import Callable, Optional, Tuple

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QLabel

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
P_DAY = (300, 4)
P_NIGHT = (300, 5)
P_PROFILE = (300, 6)
P_RESET = (300, 7)

ENTRY_SETUP = "setup"
ENTRY_CHECKLIST = "checklist"
RESET_TAP_WINDOW_SEC = 1.5


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
        self._cold_setup_preserve_progress = False
        self._cold_reset_tap_count = 0
        self._cold_reset_tap_at = 0.0
        try:
            self._cold_log(f"PROGRESS RESET: {reason}")
        except Exception:
            pass

    def _cold_enter_setup(self, reason: str = "SETUP", preserve_progress: bool = False) -> None:
        """Enter the independent DAY/NIGHT + LAND/CV setup screen."""
        if preserve_progress:
            self._cold_sequence_token = getattr(self, "_cold_sequence_token", 0) + 1
            if getattr(self, "_cold_state", "idle") in ("running", "animating"):
                self._cold_state = "paused"
            self._cold_setup_preserve_progress = True
        else:
            self._cold_reset_progress(reason)
            self._cold_setup_preserve_progress = False
        self._cold_entry_stage = ENTRY_SETUP
        self._cold_entry_confirm_count = 0
        self._cold_exec_phase = "SETUP"
        self._cold_last_action = "SELECT SETUP"
        if preserve_progress:
            self._cold_step_detail = "Choose DAY/NIGHT and LAND/CV. START x2 returns to the same checklist step."
        else:
            self._cold_step_detail = "Choose DAY/NIGHT and LAND/CV. Press START twice to enter checklist."

    def _cold_enter_checklist(self, reason: str = "ENTRY CONFIRMED") -> None:
        """Unlock the actual checklist after two setup confirmations."""
        preserve_progress = bool(getattr(self, "_cold_setup_preserve_progress", False))
        if preserve_progress:
            self._cold_setup_preserve_progress = False
            self._cold_entry_stage = ENTRY_CHECKLIST
            self._cold_entry_confirm_count = 0
            state = getattr(self, "_cold_state", "idle")
            if state == "paused":
                self._cold_exec_phase = "PAUSED"
                self._cold_step_detail = "Setup updated. Press START to resume this step."
            elif state in ("wait_user", "select_display"):
                self._cold_exec_phase = "USER"
                self._cold_step_detail = "Setup updated. Press START to continue this step."
            elif state == "complete":
                self._cold_exec_phase = "DONE"
                self._cold_step_detail = "Setup updated. Checklist was already complete."
            else:
                self._cold_exec_phase = "READY"
                self._cold_step_detail = "Setup updated. Press START to continue."
            self._cold_last_action = getattr(self, "_cold_last_action", "READY")
            return
        self._cold_reset_progress(reason)
        self._cold_entry_stage = ENTRY_CHECKLIST
        self._cold_entry_confirm_count = 0
        self._cold_exec_phase = "READY"
        self._cold_last_action = "COLD START READY"
        self._cold_step_detail = "Press START twice to arm and run."

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
        self._cold_enter_setup(reason, preserve_progress=False)
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

    def _cold_plain_label(self, key: str, x: int, y: int, w: int, h: int,
                          font_size: int, bold: bool = False,
                          align: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignCenter) -> QLabel:
        label = QLabel("", self)
        label._page = PAGE
        label.setGeometry(x, y, w, h)
        label.setAlignment(align)
        label.setWordWrap(True)
        label.setStyleSheet("color: #d7f3df; background: transparent; border: none;")
        label_font = QFont("B612", font_size)
        label_font.setBold(bold)
        label.setFont(label_font)

        def _rescale_font(new_size, lbl=label, f=label_font):
            f.setPointSize(new_size)
            lbl.setFont(f)

        label.rescale_font = _rescale_font
        self._widget_origins.append((label, x, y, w, h, font_size))
        self._cold_status_cells[key] = label
        return label

    def _init_cold_start_page(self):
        """Create a no-frame text layout plus only the required buttons."""
        self._cold_cells = {}
        self._cold_status_cells = {}

        self._cold_plain_label("title", 8, 22, 1008, 58, 32, True)
        self._cold_plain_label("rpm", 8, 104, 1008, 72, 30, True)
        self._cold_plain_label("step", 8, 205, 1008, 94, 30, True)
        self._cold_plain_label("hint", 70, 318, 884, 96, 22, False)
        self._cold_plain_label("status", 8, 455, 1008, 44, 15, False)

        # Setup-only choices. These are intentionally separate from the checklist page.
        setup_buttons = [
            ("DAY", P_DAY, 168, 420, 150, 64),
            ("NIGHT", P_NIGHT, 330, 420, 170, 64),
            ("LAND/CV", P_PROFILE, 512, 420, 230, 64),
        ]
        for text, pos, x, y, w, h in setup_buttons:
            cell = self.place_cell(text, pos, x, y, w, h, font_size=16,
                                   register=False, page=PAGE, bold=True)
            self._cold_cells[pos] = cell

        start = self.place_cell("START", P_START, 312, 500, 400, 86,
                                font_size=26, register=False, page=PAGE, bold=True)
        self._cold_cells[P_START] = start

        reset = self.place_cell("RESET", P_RESET, 884, 545, 132, 42,
                                font_size=12, register=False, page=PAGE, bold=True)
        self._cold_cells[P_RESET] = reset
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
            self._cold_enter_setup("AUTO COLD ENTRY", preserve_progress=False)
            self._show_page(PAGE)
            self._cold_refresh_ui()
            self._cold_log(f"FIRST FRESH RPM L={left} R={right}: SETUP PAGE")

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
            self._cold_detected_mode = STARTUP_MODE_COLD
            self._cold_enter_setup("HIDDEN ENTRY", preserve_progress=False)
            self._show_page(PAGE)
            self._cold_refresh_ui()
            self._cold_log("ENTER COLD SETUP BY SETTINGS x3")
            return True
        return False

    def _cold_handle_click(self, pos):
        if pos in ((0, 0), (1, 0)):
            max_rpm = self._cold_max_rpm()
            if self._cold_state in ("complete", "aborted") or (max_rpm is not None and max_rpm >= self._cold_rpm_threshold):
                self._show_page("local_icp")
            else:
                self._cold_last_action = "LOCAL ICP LOCKED"
                self._cold_step_detail = "Cold-start manager has priority."
            self._cold_refresh_ui()
            return
        if pos == P_START:
            self._cold_arm_or_continue()
        elif pos == P_RESET:
            self._cold_handle_reset_tap()
        elif pos == P_DAY:
            self._cold_set_display_mode("day")
        elif pos == P_NIGHT:
            self._cold_set_display_mode("night")
        elif pos == P_PROFILE:
            self._cold_set_profile("carrier" if self._cold_profile == "land" else "land")
        self._cold_refresh_ui()

    def _cold_handle_reset_tap(self):
        now = time.time()
        if now - getattr(self, "_cold_reset_tap_at", 0.0) > RESET_TAP_WINDOW_SEC:
            self._cold_reset_tap_count = 0
        self._cold_reset_tap_count = int(getattr(self, "_cold_reset_tap_count", 0)) + 1
        self._cold_reset_tap_at = now
        if self._cold_reset_tap_count < 2:
            self._cold_last_action = "RESET 1/2"
            self._cold_step_detail = "Press RESET again to return to setup. Step progress will be kept."
            self._cold_log("RESET CONFIRM 1/2")
            return
        self._cold_reset_tap_count = 0
        self._cold_enter_setup("RESET TO SETUP", preserve_progress=True)
        self._cold_last_action = "SELECT SETUP"
        self._cold_log("RESET CONFIRM 2/2: SETUP PAGE, PROGRESS KEPT")

    def _cold_confirm_setup_or_continue(self) -> bool:
        """Handle the mandatory two confirmations before checklist entry."""
        if getattr(self, "_cold_entry_stage", ENTRY_SETUP) == ENTRY_CHECKLIST:
            return False
        if not self._cold_all_known_below_threshold():
            self._cold_enter_hold("ENGINE RPM NOT COLD")
            return True
        count = int(getattr(self, "_cold_entry_confirm_count", 0)) + 1
        self._cold_entry_confirm_count = count
        if count < 2:
            self._cold_exec_phase = "CONFIRM 1/2"
            self._cold_last_action = "CONFIRM SETUP"
            self._cold_step_detail = "Check DAY/NIGHT and LAND/CV, then press START again."
            self._cold_refresh_ui()
            self._cold_log("SETUP CONFIRM 1/2")
            return True
        self._cold_enter_checklist("SETUP CONFIRMED")
        self._cold_refresh_ui()
        self._cold_log("SETUP CONFIRM 2/2: CHECKLIST UNLOCKED")
        return True

    def _cold_arm_or_continue(self):
        if self._cold_confirm_setup_or_continue():
            return
        if self._cold_state in ("idle", "aborted", "complete"):
            if not self._cold_all_known_below_threshold():
                self._cold_enter_hold("ENGINE RPM NOT COLD")
                return
            self._cold_reset_progress("ARM")
            self._cold_entry_stage = ENTRY_CHECKLIST
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
            was_hold = self._cold_state == "hold"
            self._cold_state = "running"
            self._cold_exec_phase = "EXEC"
            if was_hold:
                self._cold_step_index += 1
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
            ("BRIGHTNESS", "display_brightness", "", "Apply selected DAY/NIGHT preset."),
            ("LOCAL ICP", "unlock", "", "Verify LOCAL ICP ready."),
            ("INS", "ins", "", "Set selected LAND/CV profile."),
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
        if getattr(self, "_cold_entry_stage", ENTRY_SETUP) != ENTRY_SETUP:
            self._cold_last_action = "SETUP LOCKED"
            self._cold_step_detail = "Tap RESET twice to change DAY/NIGHT without clearing steps."
            self._cold_refresh_ui()
            return
        self._cold_display_mode = mode
        self._cold_entry_confirm_count = 0
        cfg = load_config()
        cfg["cold_start_display_mode"] = mode
        save_config(cfg)
        self._cold_last_action = f"DISPLAY {mode.upper()}"
        self._cold_step_detail = "Selection changed. Press START twice to confirm setup."
        self._cold_log(self._cold_last_action)
        self._cold_refresh_ui()

    def _cold_set_profile(self, profile: str):
        profile = str(profile).lower()
        if profile not in ("land", "carrier"):
            return
        if getattr(self, "_cold_entry_stage", ENTRY_SETUP) != ENTRY_SETUP:
            self._cold_last_action = "SETUP LOCKED"
            self._cold_step_detail = "Tap RESET twice to change LAND/CV without clearing steps."
            self._cold_refresh_ui()
            return
        self._cold_profile = profile
        self._cold_entry_confirm_count = 0
        cfg = load_config()
        cfg["cold_start_profile"] = profile
        save_config(cfg)
        self._cold_last_action = f"PROFILE {profile.upper()}"
        self._cold_step_detail = "Selection changed. Press START twice to confirm setup."
        self._cold_log(self._cold_last_action)
        self._cold_refresh_ui()

    def _cold_status_lines(self):
        steps = self._cold_step_list()
        idx = getattr(self, "_cold_step_index", -1)
        total = len(steps)
        left, right = self._cold_get_fresh_rpms()
        l_txt = "---" if left is None else f"{left:05.1f}%"
        r_txt = "---" if right is None else f"{right:05.1f}%"
        phase = getattr(self, "_cold_exec_phase", "IDLE")
        action = getattr(self, "_cold_last_action", "READY")
        hint = getattr(self, "_cold_step_detail", "")
        profile = getattr(self, "_cold_profile", "land").upper()
        profile_txt = "CV" if profile == "CARRIER" else "LAND"
        display = getattr(self, "_cold_display_mode", "day").upper()
        if getattr(self, "_cold_entry_stage", ENTRY_SETUP) != ENTRY_CHECKLIST:
            confirm = int(getattr(self, "_cold_entry_confirm_count", 0))
            progress = "STEP KEPT" if getattr(self, "_cold_setup_preserve_progress", False) else "NEW CHECKLIST"
            return {
                "title": "COLD START SETUP",
                "rpm": f"L {l_txt}        R {r_txt}",
                "step": f"SELECT {display} / {profile_txt}",
                "hint": f"CONFIRM {confirm}/2: {hint}",
                "status": f"DAY/NIGHT + LAND/CV FIRST    {progress}",
            }
        if idx < 0:
            step_txt = "STEP --/--"
        else:
            step_txt = f"STEP {idx + 1:02d}/{total:02d}"
        return {
            "title": "F/A-18C COLD START",
            "rpm": f"L {l_txt}        R {r_txt}",
            "step": f"{step_txt}    {action}",
            "hint": f"{phase}: {hint}",
            "status": f"PROFILE {profile_txt}    DISPLAY {display}    PROGRESS NOT SAVED",
        }

    def _cold_set_cell(self, key: str, text: str):
        cell = getattr(self, "_cold_status_cells", {}).get(key)
        if not cell:
            return
        if isinstance(cell, QLabel):
            cell.setText(text)
            return
        cell._var_text = text
        cell.update()

    def _cold_refresh_ui(self):
        cells = getattr(self, "_cold_status_cells", {})
        if not cells:
            return
        lines = self._cold_status_lines()
        for key, text in lines.items():
            self._cold_set_cell(key, text)

        is_page = getattr(self, "_current_page", None) == PAGE
        in_setup = getattr(self, "_cold_entry_stage", ENTRY_SETUP) != ENTRY_CHECKLIST
        for pos in (P_DAY, P_NIGHT, P_PROFILE):
            cell = getattr(self, "_cold_cells", {}).get(pos)
            if cell:
                cell.setVisible(is_page and in_setup)
        reset = getattr(self, "_cold_cells", {}).get(P_RESET)
        if reset:
            reset.setVisible(is_page and not in_setup)
        start = getattr(self, "_cold_cells", {}).get(P_START)
        if start:
            start.setVisible(is_page)

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
    UFCKeypadWindowClass._cold_enter_setup = _cold_enter_setup
    UFCKeypadWindowClass._cold_enter_checklist = _cold_enter_checklist
    UFCKeypadWindowClass._cold_reset_session_state = _cold_reset_session_state
    UFCKeypadWindowClass._cold_get_fresh_rpms = _cold_get_fresh_rpms
    UFCKeypadWindowClass._cold_detect_startup_mode = _cold_detect_startup_mode_fresh
    UFCKeypadWindowClass._cold_all_known_below_threshold = _cold_all_fresh_known_below_threshold
    UFCKeypadWindowClass._cold_max_rpm = _cold_max_fresh_rpm
    UFCKeypadWindowClass._cold_plain_label = _cold_plain_label
    UFCKeypadWindowClass._init_cold_start_page = _init_cold_start_page
    UFCKeypadWindowClass._update_display = _update_display
    UFCKeypadWindowClass._check_dcs_timeout = _check_dcs_timeout
    UFCKeypadWindowClass._cold_on_dcs_signal = _cold_on_dcs_signal
    UFCKeypadWindowClass._cold_handle_settings_tap = _cold_handle_settings_tap
    UFCKeypadWindowClass._cold_handle_click = _cold_handle_click
    UFCKeypadWindowClass._cold_handle_reset_tap = _cold_handle_reset_tap
    UFCKeypadWindowClass._cold_confirm_setup_or_continue = _cold_confirm_setup_or_continue
    UFCKeypadWindowClass._cold_arm_or_continue = _cold_arm_or_continue
    UFCKeypadWindowClass._cold_step_list = _cold_step_list
    UFCKeypadWindowClass._cold_run_next_step = _cold_run_next_step
    UFCKeypadWindowClass._cold_enter_hold = _cold_enter_hold
    UFCKeypadWindowClass._cold_set_display_mode = _cold_set_display_mode
    UFCKeypadWindowClass._cold_set_profile = _cold_set_profile
    UFCKeypadWindowClass._cold_status_lines = _cold_status_lines
    UFCKeypadWindowClass._cold_set_cell = _cold_set_cell
    UFCKeypadWindowClass._cold_refresh_ui = _cold_refresh_ui
    UFCKeypadWindowClass._cold_play_startup_animation = _cold_play_startup_animation
