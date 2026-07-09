# -*- coding: utf-8 -*-
"""Cold-start direct-entry and DCS-session lifecycle override.

Installed after ``patch_cold_start``.

This module is the first step toward the redesigned startup state machine:
- The first accepted DCS-BIOS signal proves the export path is alive, but it does
  not by itself reveal LOCAL ICP.
- Until fresh engine RPM from the current DCS session is known, the panel stays
  on the guarded startup manager with a WAIT ENGINE RPM status.
- The cold-start page displays live/fresh L/R RPM values only; checklist
  confirmations no longer fake engine RPM to 60%.
- APU START is followed by a mandatory 5-second stabilization interval before
  the right-engine start path can continue.
- Automatic execution, timed waits, animation, and user-action holds have clear
  status labels on the cold-start page.
- When DCS-BIOS times out, show the US NAVY wait logo and reset RPM decision
  state so stale RPM from the previous mission cannot drive the next mission.
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
from ufc.dcs_bios import send_dcs_bios
from ufc.startup import install_startup_overlay

MIN_STARTUP_ANIM_MS = 5000
APU_TO_RIGHT_CRANK_MS = 5000


def install_cold_direct_entry(UFCKeypadWindowClass) -> None:
    """Override first-signal handling, session reset, execution UI, and animation timing."""
    if getattr(UFCKeypadWindowClass, "_cold_direct_entry_installed", False):
        return
    UFCKeypadWindowClass._cold_direct_entry_installed = True

    previous_update_display = UFCKeypadWindowClass._update_display
    previous_check_dcs_timeout = UFCKeypadWindowClass._check_dcs_timeout

    def _cold_reset_session_state(self, reason: str):
        """Reset state that must not leak across DCS missions/sessions."""
        self._cold_first_mode_decided = False
        self._cold_dcs_seen = False
        self._cold_detected_mode = STARTUP_MODE_UNKNOWN
        self._cold_left_rpm = None
        self._cold_right_rpm = None
        self._cold_left_rpm_fresh = False
        self._cold_right_rpm_fresh = False
        self._cold_exec_phase = "WAIT_DCS"
        self._cold_step_detail = "US NAVY / WAITING FOR DCS-BIOS"
        self._cold_ui_powered = False
        self._cold_last_action = "WAITING FOR DCS-BIOS"
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
        """Redesigned checklist-style cold-start page."""
        self.place_cell("I/P", (0, 0), 8, 7, 140, 72, font_size=19,
                        register=False, no_feedback=True, page=PAGE)
        self.place_cell("LOCAL ICP", (1, 0), 156, 7, 180, 72, font_size=16,
                        register=False, no_feedback=True, page=PAGE)

        title = self.place_cell("F/A-18C\nCOLD START MANAGER", None, 344, 7, 672, 72,
                                font_size=23, is_variable=True, register=False,
                                no_feedback=True, page=PAGE)
        self._cold_status_cells["title"] = title

        layout = [
            ("phase", 88, 66, 24),
            ("aircraft", 160, 70, 21),
            ("engines", 236, 66, 22),
            ("action", 310, 74, 28),
            ("detail", 390, 84, 20),
            ("meta", 482, 50, 17),
        ]
        for key, y, h, font_size in layout:
            c = self.place_cell("", None, 8, y, 1008, h, font_size=font_size,
                                is_variable=True, register=False, no_feedback=True,
                                page=PAGE,
                                var_align=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self._cold_status_cells[key] = c

        y5, h5 = 542, 50
        buttons = [
            ("START / CONT", (300, 0), 8, 170),
            ("PAUSE", (300, 1), 186, 116),
            ("ABORT", (300, 2), 310, 116),
            ("SKIP", (300, 3), 434, 100),
            ("DAY", (300, 4), 542, 92),
            ("NIGHT", (300, 5), 642, 112),
            ("LAND / CV", (300, 6), 762, 254),
        ]
        for text, pos, x, w in buttons:
            cell = self.place_cell(text, pos, x, y5, w, h5, font_size=12,
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
            self._cold_exec_phase = "CHECKING"
            self._cold_step_detail = "DCS-BIOS ONLINE / CHECKING AIRCRAFT STATE"
            self._cold_log(f"DCS-BIOS FIRST SIGNAL {field_name}")

        if getattr(self, "_cold_first_mode_decided", False):
            return

        mode = self._cold_detect_startup_mode()
        if mode == STARTUP_MODE_UNKNOWN:
            self._cold_exec_phase = "CHECKING"
            self._cold_last_action = "WAIT ENGINE RPM DATA"
            self._cold_step_detail = "Waiting for fresh IFEI_RPM_L and IFEI_RPM_R from current mission."
            if getattr(self, "_current_page", None) != PAGE:
                self._show_page(PAGE)
            self._cold_refresh_ui()
            return

        self._cold_first_mode_decided = True
        if mode == STARTUP_MODE_NON_COLD:
            left, right = self._cold_get_fresh_rpms()
            self._cold_exec_phase = "HOT START"
            self._cold_step_detail = "At least one engine is above 60%; LOCAL ICP will come online after startup animation."
            self._cold_log(f"FIRST FRESH RPM L={left} R={right}: LOCAL ICP")
            self._show_page("local_icp")
            self._cold_play_startup_animation(return_page="local_icp")
        elif mode == STARTUP_MODE_COLD:
            left, right = self._cold_get_fresh_rpms()
            self._cold_exec_phase = "COLD / DARK"
            self._cold_last_action = "AUTO COLD START ENTRY"
            self._cold_step_detail = "Aircraft is cold. Press START / CONT twice to arm and run the checklist."
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
            self._cold_detected_mode = STARTUP_MODE_COLD
            self._cold_exec_phase = "COLD / DARK"
            self._cold_last_action = "HIDDEN COLD START ENTRY"
            self._cold_step_detail = "Manual hidden entry accepted. Press START / CONT twice to arm and run."
            self._show_page(PAGE)
            self._cold_refresh_ui()
            self._cold_log("ENTER COLD PAGE BY SETTINGS x3")
            return True
        return False

    def _cold_arm_or_continue(self):
        if self._cold_state in ("idle", "aborted", "complete"):
            if not self._cold_all_known_below_threshold():
                self._cold_enter_hold("DENIED: ENGINE RPM NOT COLD")
                return
            self._cold_state = "armed"
            self._cold_step_index = -1
            self._cold_right_engine_online = False
            self._cold_left_engine_online = False
            self._cold_apu_off = False
            self._cold_display_brightness_applied = False
            self._cold_normal_ufc_locked = True
            self._cold_start_anim_played = False
            self._cold_ui_powered = False
            self._cold_exec_phase = "ARMED"
            self._cold_last_action = "COLD START ARMED"
            self._cold_step_detail = "Checklist armed. Press START / CONT again to begin automatic execution."
            self._cold_log(f"ARMED COLD L={self._cold_left_rpm} R={self._cold_right_rpm}")
            self._cold_refresh_ui()
            return
        if self._cold_state == "armed":
            self._cold_state = "running"
            self._cold_step_index = 0
            self._cold_exec_phase = "EXECUTING"
            self._cold_log("RUN COLD START")
            self._cold_run_next_step()
            return
        if self._cold_state == "paused":
            self._cold_state = "running"
            self._cold_exec_phase = "EXECUTING"
            self._cold_log("RESUME")
            self._cold_run_next_step()
            return
        if self._cold_state == "hold":
            self._cold_state = "running"
            self._cold_exec_phase = "EXECUTING"
            self._cold_log("CONTINUE")
            self._cold_step_index += 1
            self._cold_run_next_step()
            return
        if self._cold_state == "wait_user":
            self._cold_state = "running"
            self._cold_exec_phase = "EXECUTING"
            self._cold_log("USER CONFIRM")
            self._cold_step_index += 1
            self._cold_run_next_step()
            return
        if self._cold_state == "select_display":
            self._cold_state = "running"
            self._cold_exec_phase = "EXECUTING"
            self._cold_step_index += 1
            self._cold_run_next_step()
            return

    def _cold_step_list(self):
        return [
            ("BATTERY ON", "send", "battery_on"),
            ("APU START", "send", "apu_start"),
            ("APU STABILIZE 5 SEC", "timer", APU_TO_RIGHT_CRANK_MS),
            ("CONFIRM APU READY", "user", "Confirm APU is ready. Press START / CONT when complete."),
            ("RIGHT ENGINE CRANK", "send", "right_engine_crank"),
            ("SET RIGHT THROTTLE IDLE", "user", "Set right throttle to IDLE, then press START / CONT."),
            ("CONFIRM RIGHT ENGINE STABLE", "flag_right", "Right engine stable confirmed."),
            ("LEFT ENGINE CRANK", "send", "left_engine_crank"),
            ("SET LEFT THROTTLE IDLE", "user", "Set left throttle to IDLE, then press START / CONT."),
            ("CONFIRM LEFT ENGINE STABLE", "flag_left", "Left engine stable confirmed."),
            ("APU OFF", "apu_off", "apu_off"),
            ("CLOSE CANOPY", "supervised", "canopy_close"),
            ("BLEED AIR PULL ROTATE 360", "supervised", "bleed_air_cycle"),
            ("TRIM RESET", "supervised", "trim_reset"),
            ("FCS RESET", "supervised", "fcs_reset"),
            ("ECM RECEIVE", "supervised", "ecm_receive"),
            ("MANUAL IFF ON", "user", "Open IFF manually, then press START / CONT."),
            ("SELECT DISPLAY MODE", "select_display", "Select DAY or NIGHT, then press START / CONT."),
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
            self._cold_exec_phase = "COMPLETE"
            self._cold_last_action = "COLD START COMPLETE"
            self._cold_step_detail = "Checklist complete. LOCAL ICP is available."
            self._cold_refresh_ui()
            return

        title, kind, payload = steps[self._cold_step_index]
        self._cold_last_action = title
        self._cold_exec_phase = "EXECUTING"
        self._cold_step_detail = "Executing automatic startup step."
        self._cold_refresh_ui()

        def advance_if_running():
            if getattr(self, "_cold_state", None) == "running":
                self._cold_step_index += 1
                self._cold_run_next_step()

        if kind == "send":
            self._cold_exec_phase = "EXECUTING"
            self._cold_step_detail = f"Sending DCS-BIOS command for {title}."
            self._cold_refresh_ui()
            self._cold_send_configured_async(payload, advance_if_running)
        elif kind == "timer":
            self._cold_exec_phase = "WAIT"
            self._cold_step_detail = f"Mandatory wait: {int(payload / 1000)} seconds after APU START before right-engine start path."
            self._cold_refresh_ui()
            QTimer.singleShot(int(payload), advance_if_running)
        elif kind == "supervised":
            self._cold_exec_phase = "SUPERVISED EXEC"
            self._cold_step_detail = f"Program is executing {title}; monitor cockpit response."
            self._cold_refresh_ui()
            self._cold_send_configured_async(payload, advance_if_running)
        elif kind == "user":
            self._cold_state = "wait_user"
            self._cold_exec_phase = "USER ACTION REQUIRED"
            self._cold_step_detail = str(payload)
            self._cold_refresh_ui()
        elif kind == "flag_right":
            self._cold_right_engine_online = True
            self._cold_exec_phase = "UFC BOOT"
            self._cold_last_action = "RIGHT ENGINE STABLE / UFC STARTUP"
            self._cold_step_detail = "Right engine stable confirmed. Playing UFC startup animation; RPM display remains live telemetry."
            self._cold_state = "animating"
            self._cold_refresh_ui()

            def after_right_anim():
                self._show_page(PAGE)
                self._cold_start_anim_played = True
                self._cold_ui_powered = True
                self._cold_exec_phase = "UFC ONLINE"
                self._cold_step_detail = "UFC online after right-engine confirmation. Continue left-engine start."
                self._cold_state = "running"
                self._cold_step_index += 1
                self._cold_run_next_step()

            self._cold_play_startup_animation(return_page=PAGE, after=after_right_anim)
        elif kind == "flag_left":
            self._cold_left_engine_online = True
            self._cold_exec_phase = "CONFIRMED"
            self._cold_last_action = "BOTH ENGINES STABLE"
            self._cold_step_detail = "Left engine stable confirmed. RPM display remains live telemetry."
            self._cold_refresh_ui()
            QTimer.singleShot(500, advance_if_running)
        elif kind == "apu_off":
            self._cold_exec_phase = "EXECUTING"
            self._cold_step_detail = "Sending APU OFF command."
            self._cold_refresh_ui()

            def after_apu_off():
                self._cold_apu_off = True
                advance_if_running()

            self._cold_send_configured_async(payload, after_apu_off)
        elif kind == "select_display":
            self._cold_state = "select_display"
            self._cold_exec_phase = "USER ACTION REQUIRED"
            self._cold_step_detail = str(payload)
            self._cold_refresh_ui()
        elif kind == "display_brightness":
            self._cold_exec_phase = "EXECUTING"
            self._cold_step_detail = "Applying DDI / AMPCD / HUD display brightness preset."
            self._cold_refresh_ui()
            self._cold_apply_display_brightness()
            QTimer.singleShot(700, advance_if_running)
        elif kind == "unlock":
            self._cold_exec_phase = "VERIFY"
            self._cold_step_detail = "Verifying LOCAL ICP unlock conditions."
            self._cold_refresh_ui()
            self._cold_unlock_local_icp()
            QTimer.singleShot(700, advance_if_running)
        elif kind == "ins":
            self._cold_exec_phase = "EXECUTING"
            self._cold_step_detail = f"Setting INS mode for {self._cold_profile.upper()} profile."
            self._cold_refresh_ui()
            self._cold_send_configured_async(
                "ins_carrier" if self._cold_profile == "carrier" else "ins_land",
                advance_if_running,
            )
        elif kind == "complete":
            self._cold_state = "complete"
            self._cold_exec_phase = "COMPLETE"
            self._cold_last_action = "COLD START COMPLETE"
            self._cold_step_detail = "Checklist complete. LOCAL ICP is available."
            self._cold_refresh_ui()

    def _cold_pause(self):
        if self._cold_state in ("running", "wait_user", "select_display", "animating"):
            self._cold_sequence_token += 1
            self._cold_state = "paused"
            self._cold_exec_phase = "PAUSED"
            self._cold_last_action = "PAUSED"
            self._cold_step_detail = "Startup manager paused. Press START / CONT to resume."
            self._cold_log("PAUSED")
            self._cold_refresh_ui()

    def _cold_enter_hold(self, reason: str):
        self._cold_sequence_token += 1
        self._cold_state = "hold"
        self._cold_hold_reason = reason
        self._cold_exec_phase = "HOLD"
        self._cold_last_action = f"HOLD: {reason}"
        self._cold_step_detail = f"Startup manager is holding: {reason}. Press START / CONT to continue if safe."
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
        self._cold_last_action = f"DISPLAY MODE {mode.upper()}"
        self._cold_step_detail = f"Display mode selected: {mode.upper()}."
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
        self._cold_step_detail = f"Startup profile selected: {profile.upper()}."
        self._cold_log(self._cold_last_action)

    def _cold_status_lines(self):
        state = getattr(self, "_cold_state", "idle").upper()
        idx = getattr(self, "_cold_step_index", -1)
        total = getattr(self, "_cold_total_steps", 0)
        step_txt = "--" if idx < 0 else f"{idx:02d}/{total:02d}"
        profile = getattr(self, "_cold_profile", "land").upper()
        display = getattr(self, "_cold_display_mode", "day").upper()
        left, right = self._cold_get_fresh_rpms()
        l_txt = "---" if left is None else f"{left:05.1f}%"
        r_txt = "---" if right is None else f"{right:05.1f}%"
        detected = getattr(self, "_cold_detected_mode", STARTUP_MODE_UNKNOWN)
        mode_txt = {
            STARTUP_MODE_COLD: "COLD / DARK",
            STARTUP_MODE_NON_COLD: "LOCAL ICP AVAILABLE",
            STARTUP_MODE_UNKNOWN: "CHECKING AIRCRAFT",
        }.get(detected, "CHECKING AIRCRAFT")
        phase = getattr(self, "_cold_exec_phase", "IDLE")
        ufc_stage = "UFC ONLINE / BRIGHT" if getattr(self, "_cold_ui_powered", False) or getattr(self, "_cold_start_anim_played", False) else "UFC OFFLINE / DARK"
        r_eng = "CONFIRMED" if getattr(self, "_cold_right_engine_online", False) else "NOT CONFIRMED"
        l_eng = "CONFIRMED" if getattr(self, "_cold_left_engine_online", False) else "NOT CONFIRMED"
        apu = "OFF" if getattr(self, "_cold_apu_off", False) else "ON/REQ"
        return {
            "title": "F/A-18C  COLD START MANAGER",
            "phase": f"{phase:<22} | {mode_txt:<21} | {ufc_stage}",
            "aircraft": f"AIRCRAFT STATE  R ENG {r_eng:<13} L ENG {l_eng:<13} APU {apu}",
            "engines": f"LIVE IFEI RPM    L {l_txt:<8}    R {r_txt:<8}    THRESHOLD {self._cold_rpm_threshold:.0f}%",
            "action": f"CURRENT ACTION   {getattr(self, '_cold_last_action', 'READY')}",
            "detail": f"DETAIL           {getattr(self, '_cold_step_detail', '')}",
            "meta": f"STATE {state:<12} STEP {step_txt:<6} PROFILE {profile:<7} DISPLAY {display}",
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
    UFCKeypadWindowClass._cold_enter_hold = _cold_enter_hold
    UFCKeypadWindowClass._cold_set_display_mode = _cold_set_display_mode
    UFCKeypadWindowClass._cold_set_profile = _cold_set_profile
    UFCKeypadWindowClass._cold_status_lines = _cold_status_lines
    UFCKeypadWindowClass._cold_refresh_ui = _cold_refresh_ui
    UFCKeypadWindowClass._cold_play_startup_animation = _cold_play_startup_animation
