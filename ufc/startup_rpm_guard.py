# -*- coding: utf-8 -*-
"""Guard cold/hot startup classification against uninitialized RPM snapshots.

The real-time RPM fallback can briefly emit 0/0 immediately after DCS-BIOS sync,
before the IFEI RPM string addresses have received their current cockpit values.
The old entry logic accepted that first pair immediately and permanently selected
the cold-start setup page, so a running engine reported as 65% a moment later was
ignored because the startup mode had already been locked.

This final patch keeps hot detection immediate, but requires a stable low-RPM
window before selecting cold start.  It also provides a narrowly scoped recovery:
if the setup page was entered from a false low snapshot and a running engine is
then observed before the checklist is armed, the app returns to LOCAL ICP.
"""
from __future__ import annotations

import time
from typing import Optional

from ufc.cold_direct_entry import ENTRY_SETUP
from ufc.cold_start import (
    STARTUP_MODE_COLD,
    STARTUP_MODE_NON_COLD,
    STARTUP_MODE_UNKNOWN,
)


# A true cold cockpit can tolerate a short detection delay.  This is long enough
# for the current IFEI RPM strings to replace the receiver's initial zero-filled
# parser memory, while hot detection remains immediate.
COLD_CONFIRM_HOLD_SEC = 2.5
COLD_CONFIRM_MIN_SAMPLES = 4


def install_startup_rpm_guard(UFCKeypadWindowClass) -> None:
    """Install delayed cold confirmation and pre-checklist hot recovery."""
    if getattr(UFCKeypadWindowClass, "_startup_rpm_guard_installed", False):
        return
    UFCKeypadWindowClass._startup_rpm_guard_installed = True

    previous_setup_state = UFCKeypadWindowClass._cold_start_setup_state
    previous_reset_session = UFCKeypadWindowClass._cold_reset_session_state
    previous_detect_mode = UFCKeypadWindowClass._cold_detect_startup_mode
    previous_on_signal = UFCKeypadWindowClass._cold_on_dcs_signal

    def _cold_rpm_guard_reset(self) -> None:
        self._cold_rpm_candidate_since = None
        self._cold_rpm_candidate_samples = 0
        self._cold_rpm_candidate_logged = False
        self._cold_rpm_hot_recovery_done = False

    def _cold_start_setup_state(self) -> None:
        previous_setup_state(self)
        self._cold_rpm_guard_reset()

    def _cold_reset_session_state(self, reason: str) -> None:
        self._cold_rpm_guard_reset()
        previous_reset_session(self, reason)
        # previous_reset_session enters the setup state and may touch shared
        # startup fields, so explicitly leave the guard in a clean state.
        self._cold_rpm_guard_reset()

    def _cold_detect_startup_mode(self) -> str:
        raw_mode = previous_detect_mode(self)
        now = time.monotonic()

        # A single engine at or above the configured threshold is authoritative.
        # Never delay hot/running-aircraft detection.
        if raw_mode == STARTUP_MODE_NON_COLD:
            if getattr(self, "_cold_rpm_candidate_since", None) is not None:
                try:
                    left, right = self._cold_get_fresh_rpms()
                    self._cold_log(
                        f"RPM GUARD: cold candidate cancelled by running engine "
                        f"L={left} R={right} threshold={self._cold_rpm_threshold}"
                    )
                except Exception:
                    pass
            self._cold_rpm_candidate_since = None
            self._cold_rpm_candidate_samples = 0
            self._cold_rpm_candidate_logged = False
            self._cold_detected_mode = STARTUP_MODE_NON_COLD
            return STARTUP_MODE_NON_COLD

        # Both channels must be fresh and below threshold before a cold candidate
        # can even begin.  One missing RPM channel remains UNKNOWN.
        if raw_mode != STARTUP_MODE_COLD:
            self._cold_rpm_candidate_since = None
            self._cold_rpm_candidate_samples = 0
            self._cold_rpm_candidate_logged = False
            self._cold_detected_mode = STARTUP_MODE_UNKNOWN
            return STARTUP_MODE_UNKNOWN

        candidate_since: Optional[float] = getattr(self, "_cold_rpm_candidate_since", None)
        if candidate_since is None:
            self._cold_rpm_candidate_since = now
            self._cold_rpm_candidate_samples = 1
            if not getattr(self, "_cold_rpm_candidate_logged", False):
                try:
                    left, right = self._cold_get_fresh_rpms()
                    self._cold_log(
                        f"RPM GUARD: low-RPM candidate L={left} R={right}; "
                        f"confirming for {COLD_CONFIRM_HOLD_SEC:.1f}s"
                    )
                except Exception:
                    pass
                self._cold_rpm_candidate_logged = True
            self._cold_detected_mode = STARTUP_MODE_UNKNOWN
            return STARTUP_MODE_UNKNOWN

        samples = int(getattr(self, "_cold_rpm_candidate_samples", 0)) + 1
        self._cold_rpm_candidate_samples = samples
        elapsed = now - candidate_since
        if elapsed >= COLD_CONFIRM_HOLD_SEC and samples >= COLD_CONFIRM_MIN_SAMPLES:
            self._cold_detected_mode = STARTUP_MODE_COLD
            try:
                left, right = self._cold_get_fresh_rpms()
                self._cold_log(
                    f"RPM GUARD: cold confirmed L={left} R={right} "
                    f"after {elapsed:.2f}s/{samples} samples"
                )
            except Exception:
                pass
            return STARTUP_MODE_COLD

        self._cold_detected_mode = STARTUP_MODE_UNKNOWN
        return STARTUP_MODE_UNKNOWN

    def _cold_on_dcs_signal(self, field_name, value) -> None:
        previous_on_signal(self, field_name, value)

        # Recovery is deliberately limited to the untouched setup page.  Once the
        # checklist has been armed or started, increasing RPM is expected and must
        # not force a page change during the engine-start sequence.
        if not getattr(self, "_cold_first_mode_decided", False):
            return
        if getattr(self, "_cold_detected_mode", None) != STARTUP_MODE_COLD:
            return
        if getattr(self, "_cold_entry_stage", None) != ENTRY_SETUP:
            return
        if getattr(self, "_cold_state", None) not in ("idle", "aborted"):
            return
        if getattr(self, "_cold_rpm_hot_recovery_done", False):
            return

        max_rpm = self._cold_max_rpm()
        threshold = float(getattr(self, "_cold_rpm_threshold", 60.0))
        if max_rpm is None or max_rpm < threshold:
            return

        self._cold_rpm_hot_recovery_done = True
        self._cold_detected_mode = STARTUP_MODE_NON_COLD
        self._cold_exec_phase = "HOT"
        self._cold_last_action = "UFC STARTUP"
        self._cold_step_detail = "Engine online. Starting LOCAL ICP."
        try:
            left, right = self._cold_get_fresh_rpms()
            self._cold_log(
                f"RPM GUARD: late running-engine recovery L={left} R={right}; LOCAL ICP"
            )
        except Exception:
            pass
        self._show_page("local_icp")
        self._cold_play_startup_animation(return_page="local_icp")

    UFCKeypadWindowClass._cold_rpm_guard_reset = _cold_rpm_guard_reset
    UFCKeypadWindowClass._cold_start_setup_state = _cold_start_setup_state
    UFCKeypadWindowClass._cold_reset_session_state = _cold_reset_session_state
    UFCKeypadWindowClass._cold_detect_startup_mode = _cold_detect_startup_mode
    UFCKeypadWindowClass._cold_on_dcs_signal = _cold_on_dcs_signal
