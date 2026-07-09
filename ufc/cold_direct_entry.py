# -*- coding: utf-8 -*-
"""Cold-start direct-entry override.

Installed after ``patch_cold_start``.

Behavior:
- The first accepted DCS-BIOS signal proves the export path is alive, but it does
  not by itself reveal LOCAL ICP.
- Until engine RPM is known, the panel stays on the guarded cold-start page with
  a WAIT ENGINE RPM status instead of exposing LOCAL ICP.
- If either engine RPM is at/above threshold, play the UFC startup animation for
  at least five seconds, then return to LOCAL ICP.
- If both engine RPM values are known and both are below threshold, enter the
  cold-start manager immediately.

SETTINGS x3 remains as a backup manual entry path.
"""
from __future__ import annotations

from typing import Callable, Optional

from PyQt6.QtCore import QTimer

from ufc.cold_start import PAGE, STARTUP_MODE_COLD, STARTUP_MODE_NON_COLD, STARTUP_MODE_UNKNOWN
from ufc.startup import install_startup_overlay

MIN_STARTUP_ANIM_MS = 5000


def install_cold_direct_entry(UFCKeypadWindowClass) -> None:
    """Override cold-start first-signal handling and animation timing."""

    def _cold_on_dcs_signal(self, field_name, value):
        if not getattr(self, "_cold_dcs_seen", False):
            self._cold_dcs_seen = True
            self._cold_hide_wait_logo()
            self._cold_log(f"DCS-BIOS FIRST SIGNAL {field_name}")

        if getattr(self, "_cold_first_mode_decided", False):
            return

        mode = self._cold_detect_startup_mode()
        if mode == STARTUP_MODE_UNKNOWN:
            # Do not expose LOCAL ICP while RPM is still unknown.  This fixes the
            # cold-mission race where the first non-RPM DCS-BIOS packet removed
            # the US NAVY wait logo and revealed the main keyboard before both
            # engine RPM strings arrived.
            self._cold_last_action = "WAIT ENGINE RPM DATA"
            if getattr(self, "_current_page", None) != PAGE:
                self._show_page(PAGE)
            self._cold_refresh_ui()
            return

        self._cold_first_mode_decided = True
        if mode == STARTUP_MODE_NON_COLD:
            self._cold_log(f"FIRST RPM L={self._cold_left_rpm} R={self._cold_right_rpm}: LOCAL ICP")
            self._show_page("local_icp")
            self._cold_play_startup_animation(return_page="local_icp")
        elif mode == STARTUP_MODE_COLD:
            self._cold_last_action = "AUTO COLD START ENTRY"
            self._show_page(PAGE)
            self._cold_refresh_ui()
            self._cold_log(f"FIRST RPM L={self._cold_left_rpm} R={self._cold_right_rpm}: AUTO COLD PAGE")

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

    UFCKeypadWindowClass._cold_on_dcs_signal = _cold_on_dcs_signal
    UFCKeypadWindowClass._cold_play_startup_animation = _cold_play_startup_animation
