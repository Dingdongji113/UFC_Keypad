# -*- coding: utf-8 -*-
"""Two-stage CV launch trim controller.

Large errors use a long trim hold for rapid travel. Once the stabilator is close
to the target, the controller switches to short pulses and requires two fresh
telemetry samples inside tolerance before advancing the cold-start checklist.
"""
from __future__ import annotations

import time
from typing import Callable, Tuple

from PyQt6.QtCore import QTimer

from ufc.cv_trim_auto import (
    TRIM_MAX_PULSES,
    TRIM_TOLERANCE_DEG,
    send_cv_trim_pulse,
)


TRIM_FAST_THRESHOLD_DEG = 1.5
TRIM_FAST_PULSE_MS = 600
TRIM_FINE_PULSE_MS = 100
TRIM_SAMPLE_POLL_MS = 50
TRIM_SAMPLE_WAIT_MS = 500
TRIM_CONFIRM_SAMPLES = 2


def cv_trim_control_phase(error_deg: float) -> Tuple[str, int]:
    """Return ``(phase, pulse_ms)`` for the current trim error."""
    magnitude = abs(float(error_deg))
    if magnitude <= TRIM_TOLERANCE_DEG:
        return "verify", 0
    if magnitude > TRIM_FAST_THRESHOLD_DEG:
        return "fast", TRIM_FAST_PULSE_MS
    return "fine", TRIM_FINE_PULSE_MS


def install_cv_trim_two_stage(UFCKeypadWindowClass) -> None:
    """Replace the fixed-pulse CAT TRIM loop with fast-then-fine control."""
    if getattr(UFCKeypadWindowClass, "_cv_trim_two_stage_installed", False):
        return
    UFCKeypadWindowClass._cv_trim_two_stage_installed = True

    def _cold_run_cat_trim_auto(self, advance_if_running: Callable[[], None]) -> None:
        self._cold_exec_phase = "AUTO"
        self._cold_last_action = "CAT TRIM FAST"
        self._cold_trim_pulse_count = 0
        self._cold_trim_confirm_count = 0
        self._cold_trim_confirm_timestamp = 0.0
        self._cold_trim_run_generation = int(getattr(self, "_cold_trim_run_generation", 0)) + 1
        generation = self._cold_trim_run_generation
        self._cold_refresh_ui()

        def _context_valid() -> bool:
            if generation != getattr(self, "_cold_trim_run_generation", None):
                return False
            if getattr(self, "_cold_state", None) != "running":
                return False
            steps = self._cold_step_list()
            index = int(getattr(self, "_cold_step_index", -1))
            return 0 <= index < len(steps) and steps[index][1] == "cat_trim_auto"

        def _fallback_missing_data() -> None:
            self._cold_state = "wait_user"
            self._cold_exec_phase = "USER"
            self._cold_last_action = "CAT TRIM DATA?"
            self._cold_step_detail = (
                "No fresh CV trim telemetry. Check dcs_export/UFC_Keypad_CVTrim.lua and "
                "cv_trim_debug.log. Set catapult trim manually and press START if needed."
            )
            self._cold_log("CAT TRIM telemetry missing; fallback to user confirmation")
            self._cold_refresh_ui()

        def _wait_for_fresh_sample(previous_timestamp: float, not_before: float) -> None:
            deadline = float(not_before) + TRIM_SAMPLE_WAIT_MS / 1000.0

            def _poll() -> None:
                nonlocal deadline
                if not _context_valid():
                    return
                snap = self._cv_trim_snapshot()
                now = time.monotonic()
                fresh = float(getattr(snap, "timestamp", 0.0) or 0.0) > float(previous_timestamp)
                if now >= not_before and fresh:
                    _tick()
                    return

                age = time.time() - snap.timestamp if snap.timestamp else 999.0
                if age > 2.0:
                    # Re-enter the main loop only to trigger the established
                    # missing-telemetry fallback. Never command from stale data.
                    _tick()
                    return

                if now >= deadline:
                    deadline = now + TRIM_SAMPLE_WAIT_MS / 1000.0
                QTimer.singleShot(TRIM_SAMPLE_POLL_MS, _poll)

            QTimer.singleShot(TRIM_SAMPLE_POLL_MS, _poll)

        def _tick() -> None:
            if not _context_valid():
                return

            snap = self._cv_trim_snapshot()
            age = time.time() - snap.timestamp if snap.timestamp else 999.0
            if snap.weight_lbs is None or snap.trim_deg is None or age > 2.0:
                _fallback_missing_data()
                return

            target = self._cv_trim_target_deg(snap.weight_lbs)
            current = float(snap.trim_deg)
            error = target - current
            phase, pulse_ms = cv_trim_control_phase(error)

            if phase == "verify":
                last_timestamp = float(getattr(self, "_cold_trim_confirm_timestamp", 0.0) or 0.0)
                if snap.timestamp > last_timestamp:
                    self._cold_trim_confirm_timestamp = snap.timestamp
                    self._cold_trim_confirm_count = int(getattr(self, "_cold_trim_confirm_count", 0)) + 1
                confirm_count = int(getattr(self, "_cold_trim_confirm_count", 0))
                self._cold_exec_phase = "VERIFY"
                self._cold_last_action = "CAT TRIM VERIFY"
                self._cold_step_detail = (
                    f"Weight {snap.weight_lbs:.0f} lb, target {target:.0f} deg, "
                    f"current {current:.1f} deg. Verify {confirm_count}/{TRIM_CONFIRM_SAMPLES}."
                )
                self._cold_refresh_ui()
                if confirm_count >= TRIM_CONFIRM_SAMPLES:
                    self._cold_log(
                        f"CAT TRIM complete weight={snap.weight_lbs:.0f} "
                        f"current={current:.2f} target={target:.2f} "
                        f"confirm={confirm_count}"
                    )
                    advance_if_running()
                    return
                _wait_for_fresh_sample(snap.timestamp, time.monotonic())
                return

            # Any sample outside tolerance invalidates the consecutive-confirmation count.
            self._cold_trim_confirm_count = 0
            self._cold_trim_confirm_timestamp = 0.0

            pulse_count = int(getattr(self, "_cold_trim_pulse_count", 0))
            if pulse_count >= TRIM_MAX_PULSES:
                self._cold_state = "wait_user"
                self._cold_exec_phase = "USER"
                self._cold_last_action = "CAT TRIM LIMIT"
                self._cold_step_detail = "Auto trim pulse limit reached. Verify trim manually, then START."
                self._cold_refresh_ui()
                return

            direction = "up" if error > 0 else "down"
            phase_label = "FAST" if phase == "fast" else "FINE"
            self._cold_exec_phase = phase_label
            self._cold_last_action = f"CAT TRIM {phase_label}"
            self._cold_step_detail = (
                f"Weight {snap.weight_lbs:.0f} lb, target {target:.0f} deg, "
                f"current {current:.1f} deg. {phase_label} {pulse_ms} ms."
            )
            self._cold_refresh_ui()

            ok = send_cv_trim_pulse(direction, pulse_ms=pulse_ms)
            self._cold_trim_pulse_count = pulse_count + 1
            self._cold_log(
                f"CAT TRIM {phase.lower()} pulse {direction} {pulse_ms}ms ok={ok} "
                f"current={current:.2f} target={target:.2f} error={error:.2f}"
            )

            # Do not issue another command until the current hold has released and
            # at least one newer telemetry packet is available. This avoids
            # overlapping the Lua bridge's single pending trim release.
            not_before = time.monotonic() + pulse_ms / 1000.0
            _wait_for_fresh_sample(snap.timestamp, not_before)

        QTimer.singleShot(0, _tick)

    UFCKeypadWindowClass._cold_run_cat_trim_auto = _cold_run_cat_trim_auto
