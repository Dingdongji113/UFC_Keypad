# -*- coding: utf-8 -*-
"""Cold-start direct-entry override.

This small patch is installed after ``patch_cold_start``.  It changes the
first-DCS-BIOS/RPM decision behavior:

- First accepted DCS-BIOS signal always hides the US NAVY wait logo.
- If either engine RPM is at/above the threshold, play the UFC startup animation
  and return to LOCAL ICP.
- If both engine RPM values are known and both are below the threshold, enter the
  cold-start page immediately instead of waiting for SETTINGS x3.

SETTINGS x3 remains as a backup manual entry path, but normal cold missions now
open the cold-start manager automatically.
"""
from __future__ import annotations

from ufc.cold_start import PAGE, STARTUP_MODE_COLD, STARTUP_MODE_NON_COLD, STARTUP_MODE_UNKNOWN


def install_cold_direct_entry(UFCKeypadWindowClass) -> None:
    """Override cold-start first-signal handling on the patched window class."""

    def _cold_on_dcs_signal(self, field_name, value):
        if not getattr(self, "_cold_dcs_seen", False):
            self._cold_dcs_seen = True
            self._cold_hide_wait_logo()
            self._cold_log(f"DCS-BIOS FIRST SIGNAL {field_name}")

        if getattr(self, "_cold_first_mode_decided", False):
            return

        mode = self._cold_detect_startup_mode()
        if mode == STARTUP_MODE_UNKNOWN:
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

    UFCKeypadWindowClass._cold_on_dcs_signal = _cold_on_dcs_signal
