# -*- coding: utf-8 -*-
"""Cold-start direct-entry and DCS-session lifecycle override.

Installed after ``patch_cold_start``.

Behavior:
- The first accepted DCS-BIOS signal proves the export path is alive, but it does
  not by itself reveal LOCAL ICP.
- Until fresh engine RPM from the current DCS session is known, the panel stays
  on the guarded cold-start page with a WAIT ENGINE RPM status instead of
  exposing LOCAL ICP.
- If either fresh engine RPM is at/above threshold, play the UFC startup
  animation for at least five seconds, then return to LOCAL ICP.
- If both fresh engine RPM values are known and both are below threshold, enter
  the cold-start manager immediately.
- When DCS-BIOS times out, show the US NAVY wait logo instead of leaving a black
  blank panel, and reset all RPM decision state so stale RPM from the previous
  mission cannot drive the next mission.

SETTINGS x3 remains as a backup manual entry path, but it also uses fresh RPM
only.
"""
from __future__ import annotations

from typing import Callable, Optional, Tuple

from PyQt6.QtCore import QTimer

from ufc.cold_start import (
    LEFT_RPM_INTERNAL,
    PAGE,
    RIGHT_RPM_INTERNAL,
    STARTUP_MODE_COLD,
    STARTUP_MODE_NON_COLD,
    STARTUP_MODE_UNKNOWN,
)
from ufc.startup import install_startup_overlay

MIN_STARTUP_ANIM_MS = 5000


def install_cold_direct_entry(UFCKeypadWindowClass) -> None:
    """Override first-signal handling, session reset, and animation timing."""
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
        self._cold_last_action = "WAITING FOR DCS-BIOS"
        # Remove stale RPM cache.  Non-RPM UFC cached values may remain useful,
        # but old engine RPM must never decide the next mission state.
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

    def _update_display(self, field_name, value):
        if field_name == LEFT_RPM_INTERNAL:
            self._cold_left_rpm_fresh = True
        elif field_name == RIGHT_RPM_INTERNAL:
            self._cold_right_rpm_fresh = True
        previous_update_display(self, field_name, value)

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
            self._cold_log(f"DCS-BIOS FIRST SIGNAL {field_name}")

        if getattr(self, "_cold_first_mode_decided", False):
            return

        mode = self._cold_detect_startup_mode()
        if mode == STARTUP_MODE_UNKNOWN:
            # Do not expose LOCAL ICP while fresh RPM from the current DCS
            # session is still unknown.  This prevents old 0/0 RPM values from a
            # previous cold mission from forcing the next hot mission into the
            # cold-start page.
            self._cold_last_action = "WAIT ENGINE RPM DATA"
            if getattr(self, "_current_page", None) != PAGE:
                self._show_page(PAGE)
            self._cold_refresh_ui()
            return

        self._cold_first_mode_decided = True
        if mode == STARTUP_MODE_NON_COLD:
            left, right = self._cold_get_fresh_rpms()
            self._cold_log(f"FIRST FRESH RPM L={left} R={right}: LOCAL ICP")
            self._show_page("local_icp")
            self._cold_play_startup_animation(return_page="local_icp")
        elif mode == STARTUP_MODE_COLD:
            left, right = self._cold_get_fresh_rpms()
            self._cold_last_action = "AUTO COLD START ENTRY"
            self._show_page(PAGE)
            self._cold_refresh_ui()
            self._cold_log(f"FIRST FRESH RPM L={left} R={right}: AUTO COLD PAGE")

    def _cold_handle_settings_tap(self) -> bool:
        if not self._cold_all_known_below_threshold():
            self._cold_hidden_tap_count = 0
            return False
        import time
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
        hold_seconds = MIN_STARTUP_ANIM_MS / 1000.0

        # The overlay has its own auto-finish timer driven by ready_hold_seconds.
        # Delaying only our callback is not enough; the overlay would still close
        # itself after its default short ready hold.  Raise its internal hold time
        # before marking it ONLINE/READY.
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

        def _after_overlay():
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

        QTimer.singleShot(hold_ms, _after_overlay)

    UFCKeypadWindowClass._cold_reset_session_state = _cold_reset_session_state
    UFCKeypadWindowClass._cold_get_fresh_rpms = _cold_get_fresh_rpms
    UFCKeypadWindowClass._cold_detect_startup_mode = _cold_detect_startup_mode_fresh
    UFCKeypadWindowClass._cold_all_known_below_threshold = _cold_all_fresh_known_below_threshold
    UFCKeypadWindowClass._cold_max_rpm = _cold_max_fresh_rpm
    UFCKeypadWindowClass._update_display = _update_display
    UFCKeypadWindowClass._check_dcs_timeout = _check_dcs_timeout
    UFCKeypadWindowClass._cold_on_dcs_signal = _cold_on_dcs_signal
    UFCKeypadWindowClass._cold_handle_settings_tap = _cold_handle_settings_tap
    UFCKeypadWindowClass._cold_play_startup_animation = _cold_play_startup_animation
