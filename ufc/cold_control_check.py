# -*- coding: utf-8 -*-
"""Optional automated post-lighting mechanism and flight-control check."""
from __future__ import annotations

import time
from typing import Callable, Dict, Optional

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QProgressBar

import ufc.dcs_bios as dcs_bios
from ufc.cold_direct_entry import PAGE, P_START
from ufc.cv_trim_auto import send_axis_override

P_CONTROL_LEFT = (92, 0)
P_CONTROL_RIGHT = (92, 2)

CONTROL_TIME_SCALE = 1.0
FEEDBACK_POLL_MS = 200
FEEDBACK_TIMEOUT_MS = 25000
CENTER_HOLD_MS = 500

PITCH_AFT = 1.0
PITCH_FORWARD = -1.0
ROLL_LEFT = -1.0
ROLL_RIGHT = 1.0
RUDDER_LEFT = -1.0
RUDDER_RIGHT = 1.0


def _ms(value: int) -> int:
    return max(1, round(int(value) * CONTROL_TIME_SCALE))


def install_cold_control_check(UFCKeypadWindowClass) -> None:
    if getattr(UFCKeypadWindowClass, "_cold_control_check_installed", False):
        return
    UFCKeypadWindowClass._cold_control_check_installed = True

    previous_init_page = UFCKeypadWindowClass._init_cold_start_page
    previous_step_list = UFCKeypadWindowClass._cold_step_list
    previous_run_next_step = UFCKeypadWindowClass._cold_run_next_step
    previous_handle_click = UFCKeypadWindowClass._cold_handle_click
    previous_arm_or_continue = UFCKeypadWindowClass._cold_arm_or_continue
    previous_refresh_ui = UFCKeypadWindowClass._cold_refresh_ui

    def _init_cold_start_page(self) -> None:
        previous_init_page(self)
        left = self.place_cell(
            "SKIP", P_CONTROL_LEFT, 190, 430, 190, 58,
            font_size=17, register=False, page=PAGE, bold=True,
        )
        prompt = self.place_cell(
            "", None, 392, 420, 240, 36,
            font_size=13, is_variable=True, register=False,
            no_feedback=True, page=PAGE, bold=True,
        )
        right = self.place_cell(
            "EXECUTE", P_CONTROL_RIGHT, 644, 430, 190, 58,
            font_size=15, register=False, page=PAGE, bold=True,
        )
        progress = QProgressBar(self)
        progress._page = PAGE
        progress.setGeometry(392, 460, 240, 24)
        progress.setRange(0, 100)
        progress.setValue(0)
        progress.setFormat("%p%")
        progress.setTextVisible(True)
        progress.setStyleSheet(
            "QProgressBar { color: #00ff66; background: #050805; border: 2px solid #00aa44; "
            "text-align: center; font: bold 11pt 'B612'; }"
            "QProgressBar::chunk { background: #00aa44; }"
        )
        self._widget_origins.append((progress, 392, 460, 240, 24, 11))
        self._cold_control_cells = {"left": left, "prompt": prompt, "right": right, "progress": progress}
        for cell in self._cold_control_cells.values():
            cell.setVisible(False)

    def _cold_step_list(self):
        steps = []
        inserted = False
        for step in previous_step_list(self):
            steps.append(step)
            if step[0] == "BLEED AIR":
                steps.append((
                    "CONTROL CHECK",
                    "control_check",
                    "",
                    "Optional automated probe, hook, launch bar, wing-fold and full-axis check.",
                ))
                inserted = True
        if not inserted:
            raise RuntimeError("BLEED AIR step not found for CONTROL CHECK insertion")
        return steps

    def _control_step_is_current(self) -> bool:
        steps = self._cold_step_list()
        index = int(getattr(self, "_cold_step_index", -1))
        return 0 <= index < len(steps) and steps[index][1] == "control_check"

    def _control_context_valid(self, generation: Optional[int] = None) -> bool:
        valid = (
            self._control_step_is_current()
            and getattr(self, "_current_page", None) == PAGE
            and getattr(self, "_cold_control_step_index", None) == getattr(self, "_cold_step_index", None)
            and getattr(self, "_cold_control_token", None) == getattr(self, "_cold_sequence_token", None)
        )
        if generation is not None:
            valid = valid and generation == getattr(self, "_cold_control_generation", None)
        return valid

    def _control_feedback(self, key: str) -> Optional[float]:
        value = (getattr(getattr(self, "dcs_bios", None), "latest", {}) or {}).get(key)
        try:
            return float(value)
        except (TypeError, ValueError):
            pass
        snapshot_method = getattr(self, "_cv_trim_snapshot", None)
        if callable(snapshot_method):
            snapshot = snapshot_method()
            if time.time() - float(getattr(snapshot, "timestamp", 0.0) or 0.0) <= 2.0:
                raw = getattr(snapshot, "raw", {}) or {}
                try:
                    return float(raw.get(key))
                except (TypeError, ValueError):
                    pass
        return None

    def _control_capture_initial(self) -> bool:
        values = {
            "probe": self._control_feedback("ext_refuel_probe"),
            "hook": self._control_feedback("ext_hook"),
            "launch": self._control_feedback("ext_launch_bar"),
            "wing": self._control_feedback("ext_wing_folding"),
        }
        if any(value is None or 0.25 < value < 0.75 for value in values.values()):
            return False
        self._cold_control_initial = {name: bool(value >= 0.5) for name, value in values.items()}
        return True

    def _control_send(self, identifier: str, value) -> bool:
        ok = dcs_bios.send_dcs_bios(identifier, value)
        self._cold_log(f"CONTROL CHECK {identifier} {value} {'OK' if ok else 'FAIL'}")
        return ok

    def _control_set_probe(self, extended: bool) -> None:
        self._control_send("PROBE_SW", 0 if extended else 1)

    def _control_set_hook(self, down: bool) -> None:
        self._control_send("HOOK_LEVER", 0 if down else 1)

    def _control_set_launch_bar(self, down: bool) -> None:
        self._control_send("LAUNCH_BAR_SW", 1 if down else 0)

    def _control_set_wing(self, folded: bool, generation: int) -> None:
        self._control_send("WING_FOLD_PULL", 1)

        def rotate() -> None:
            if self._control_context_valid(generation) and getattr(self, "_cold_control_phase", "") in ("running", "restoring"):
                self._control_send("WING_FOLD_ROTATE", 0 if folded else 2)

        QTimer.singleShot(_ms(150), rotate)

    def _control_lock_wing(self, folded: bool, generation: int,
                           done: Optional[Callable[[], None]] = None) -> None:
        if not self._control_context_valid(generation):
            return
        if folded:
            self._control_send("WING_FOLD_ROTATE", 0)
            self._control_send("WING_FOLD_PULL", 1)
            if done is not None:
                QTimer.singleShot(_ms(500), lambda: done() if self._control_context_valid(generation) else None)
        else:
            # Live verification: UNFOLD reaches the spread position, then the
            # handle must dwell at HOLD, be pushed in, and finally return to
            # the locked 0/0 indication.  Sending only HOLD leaves it visibly
            # unlatched for several seconds.
            self._control_send("WING_FOLD_ROTATE", 1)

            def push_in() -> None:
                if not self._control_context_valid(generation):
                    return
                self._control_send("WING_FOLD_PULL", 0)

                def lock_rotation() -> None:
                    if not self._control_context_valid(generation):
                        return
                    self._control_send("WING_FOLD_ROTATE", 0)
                    if done is not None:
                        QTimer.singleShot(_ms(500), lambda: done() if self._control_context_valid(generation) else None)

                QTimer.singleShot(_ms(3000), lock_rotation)

            QTimer.singleShot(_ms(1000), push_in)

    def _control_set_axis(self, pitch: float = 0.0, roll: float = 0.0, rudder: float = 0.0,
                          duration_ms: int = 1000, label: str = "CENTER") -> None:
        ok = send_axis_override(
            pitch, roll, rudder,
            duration_ms=_ms(duration_ms) + _ms(250),
            label=label,
        )
        self._cold_log(f"CONTROL CHECK AXIS {label} {'OK' if ok else 'FAIL'}")

    def _control_progress_segment(self, start: int, end: int, duration_ms: int, generation: int) -> None:
        started = time.monotonic()
        duration = max(1, _ms(duration_ms))

        def tick() -> None:
            if not self._control_context_valid(generation) or getattr(self, "_cold_control_phase", "") != "running":
                return
            elapsed = (time.monotonic() - started) * 1000
            ratio = min(1.0, elapsed / duration)
            self._cold_control_progress = round(start + (end - start) * ratio)
            self._cold_refresh_ui()
            if ratio < 1.0:
                QTimer.singleShot(_ms(100), tick)

        tick()

    def _control_after(self, delay_ms: int, generation: int, callback: Callable[[], None]) -> None:
        QTimer.singleShot(
            _ms(delay_ms),
            lambda: callback() if self._control_context_valid(generation)
            and getattr(self, "_cold_control_phase", "") == "running" else None,
        )

    def _control_wait_feedback(self, key: str, target: bool, generation: int,
                               success: Callable[[], None], failure_label: str) -> None:
        started = time.monotonic()
        timeout = _ms(FEEDBACK_TIMEOUT_MS)

        def poll() -> None:
            if not self._control_context_valid(generation) or getattr(self, "_cold_control_phase", "") != "running":
                return
            value = self._control_feedback(key)
            # Wing-fold position is a continuously moving exterior argument.
            # The generic 25/75-percent switch thresholds are suitable for the
            # other mechanisms, but they used to stop an unfolding wing at
            # 0.234 and put the handle in HOLD before the wing reached its
            # spread stop.  Require the actual end position before latching it.
            if key == "ext_wing_folding":
                reached = value is not None and ((value >= 0.98) if target else (value <= 0.02))
            else:
                reached = value is not None and ((value >= 0.75) if target else (value <= 0.25))
            if reached:
                success()
                return
            if (time.monotonic() - started) * 1000 >= timeout:
                self._control_abort(f"{failure_label} FEEDBACK TIMEOUT")
                return
            QTimer.singleShot(_ms(FEEDBACK_POLL_MS), poll)

        poll()

    def _control_set_status(self, action: str, detail: str) -> None:
        self._cold_last_action = action
        self._cold_step_detail = detail
        self._cold_refresh_ui()

    def _control_start_sequence(self) -> None:
        if not self._control_capture_initial():
            self._cold_control_phase = "aborted"
            self._cold_control_progress = 0
            self._cold_state = "wait_user"
            self._control_set_status("CONTROL DATA MISSING", "Mechanism feedback unavailable. CONTINUE skips this check.")
            return
        self._cold_control_generation += 1
        generation = self._cold_control_generation
        self._cold_control_phase = "running"
        self._cold_control_progress = 0
        self._cold_state = "running"
        self._cold_exec_phase = "CHECK"
        self._control_probe_extend(generation)

    def _control_probe_extend(self, generation: int) -> None:
        self._control_set_status("PROBE EXTEND", "Extending refueling probe; retract command in 5 seconds.")
        self._control_set_probe(True)
        self._control_progress_segment(0, 10, 5000, generation)
        self._control_after(5000, generation, lambda: self._control_probe_retract(generation))

    def _control_probe_retract(self, generation: int) -> None:
        self._control_set_status("PROBE RETRACT", "Retracting refueling probe and confirming stowed position.")
        self._control_set_probe(False)
        self._control_wait_feedback(
            "ext_refuel_probe", False, generation,
            lambda: self._control_hook_down(generation), "PROBE",
        )

    def _control_hook_down(self, generation: int) -> None:
        self._cold_control_progress = 12
        self._control_set_status("HOOK DOWN", "Lowering arresting hook; raise command in 5 seconds.")
        self._control_set_hook(True)
        self._control_progress_segment(12, 22, 5000, generation)
        self._control_after(5000, generation, lambda: self._control_hook_up(generation))

    def _control_hook_up(self, generation: int) -> None:
        self._control_set_status("HOOK UP", "Raising arresting hook and confirming stowed position.")
        self._control_set_hook(False)
        self._control_wait_feedback("ext_hook", False, generation, lambda: self._control_launch_down(generation), "HOOK")

    def _control_launch_down(self, generation: int) -> None:
        self._cold_control_progress = 24
        self._control_set_status("LAUNCH BAR DOWN", "Lowering launch bar; retract command in 5 seconds.")
        self._control_set_launch_bar(True)
        self._control_progress_segment(24, 34, 5000, generation)
        self._control_after(5000, generation, lambda: self._control_launch_up(generation))

    def _control_launch_up(self, generation: int) -> None:
        self._control_set_status("LAUNCH BAR RETRACT", "Retracting launch bar and confirming stowed position.")
        self._control_set_launch_bar(False)
        self._control_wait_feedback(
            "ext_launch_bar", False, generation,
            lambda: self._control_wing_opposite(generation), "LAUNCH BAR",
        )

    def _control_wing_opposite(self, generation: int) -> None:
        initial_folded = bool(self._cold_control_initial["wing"])
        opposite = not initial_folded
        self._cold_control_progress = 36
        action = "WING UNFOLD" if initial_folded else "WING FOLD"
        restore = "fold" if initial_folded else "unfold"
        self._control_set_status(action, f"Moving wings to opposite position; {restore} command in 20 seconds.")
        self._control_set_wing(opposite, generation)
        self._control_progress_segment(36, 56, 20000, generation)
        self._control_after(20000, generation, lambda: self._control_wing_restore(generation))

    def _control_wing_restore(self, generation: int) -> None:
        initial_folded = bool(self._cold_control_initial["wing"])
        self._control_set_status("WING RESTORE", "Returning wings to their initial position and confirming completion.")
        self._control_set_wing(initial_folded, generation)

        def restored() -> None:
            self._control_lock_wing(
                initial_folded,
                generation,
                lambda: self._control_mechanisms_complete(generation),
            )

        self._control_wait_feedback("ext_wing_folding", initial_folded, generation, restored, "WING")

    def _control_mechanisms_complete(self, generation: int) -> None:
        self._cold_control_progress = 65
        self._control_set_status("MECHANISMS COMPLETE", "All mechanism checks confirmed. Waiting 5 seconds before axis movement.")
        self._control_progress_segment(65, 72, 5000, generation)
        self._control_after(5000, generation, lambda: self._control_axis_aft(generation))

    def _control_axis_hold(self, generation: int, action: str, detail: str, start: int, end: int,
                           hold_ms: int, pitch: float = 0.0, roll: float = 0.0, rudder: float = 0.0,
                           next_step: Optional[Callable[[], None]] = None) -> None:
        self._control_set_status(action, detail)
        self._control_set_axis(pitch, roll, rudder, hold_ms, action)
        self._control_progress_segment(start, end, hold_ms, generation)

        def center() -> None:
            self._control_set_axis(0.0, 0.0, 0.0, CENTER_HOLD_MS, f"{action} CENTER")
            if next_step is not None:
                self._control_after(CENTER_HOLD_MS, generation, next_step)

        self._control_after(hold_ms, generation, center)

    def _control_axis_aft(self, generation: int) -> None:
        self._control_axis_hold(
            generation, "STICK FULL AFT", "Holding full aft for 3 seconds, then centering.", 72, 76, 3000,
            pitch=PITCH_AFT, next_step=lambda: self._control_axis_forward(generation),
        )

    def _control_axis_forward(self, generation: int) -> None:
        self._cold_control_progress = 77
        self._control_axis_hold(
            generation, "STICK FULL FORWARD", "Holding full forward for 3 seconds, then centering.", 77, 81, 3000,
            pitch=PITCH_FORWARD, next_step=lambda: self._control_axis_left(generation),
        )

    def _control_axis_left(self, generation: int) -> None:
        self._cold_control_progress = 82
        self._control_axis_hold(
            generation, "STICK FULL LEFT", "Holding full left for 3 seconds, then centering.", 82, 86, 3000,
            roll=ROLL_LEFT, next_step=lambda: self._control_axis_right(generation),
        )

    def _control_axis_right(self, generation: int) -> None:
        self._cold_control_progress = 87
        self._control_axis_hold(
            generation, "STICK FULL RIGHT", "Holding full right for 3 seconds, then centering.", 87, 91, 3000,
            roll=ROLL_RIGHT, next_step=lambda: self._control_rudder_left(generation),
        )

    def _control_rudder_left(self, generation: int) -> None:
        self._cold_control_progress = 92
        self._control_axis_hold(
            generation, "RUDDER FULL LEFT", "Holding full left rudder for 5 seconds, then centering.", 92, 95, 5000,
            rudder=RUDDER_LEFT, next_step=lambda: self._control_rudder_right(generation),
        )

    def _control_rudder_right(self, generation: int) -> None:
        self._cold_control_progress = 96
        self._control_axis_hold(
            generation, "RUDDER FULL RIGHT", "Holding full right rudder for 5 seconds, then centering.", 96, 99, 5000,
            rudder=RUDDER_RIGHT, next_step=lambda: self._control_finish(generation),
        )

    def _control_finish(self, generation: int) -> None:
        if not self._control_context_valid(generation):
            return
        self._control_set_axis(0.0, 0.0, 0.0, 1000, "FINAL CENTER")
        self._cold_control_progress = 100
        self._cold_control_phase = "done"
        self._cold_state = "wait_user"
        self._cold_exec_phase = "DONE"
        self._control_set_status("CONTROL CHECK COMPLETE", "Progress complete. Press CONTINUE for the next cold-start step.")

    def _control_restore_initial(self, generation: int, done: Callable[[bool], None]) -> None:
        initial: Dict[str, bool] = dict(getattr(self, "_cold_control_initial", {}) or {})
        self._control_set_axis(0.0, 0.0, 0.0, 1500, "ABORT CENTER")
        if not initial:
            done(False)
            return
        self._control_set_probe(initial.get("probe", False))
        self._control_set_hook(initial.get("hook", False))
        self._control_set_launch_bar(initial.get("launch", False))
        self._control_set_wing(initial.get("wing", False), generation)
        started = time.monotonic()

        def poll() -> None:
            if not self._control_context_valid(generation) or getattr(self, "_cold_control_phase", "") != "restoring":
                return
            current = {
                "probe": self._control_feedback("ext_refuel_probe"),
                "hook": self._control_feedback("ext_hook"),
                "launch": self._control_feedback("ext_launch_bar"),
                "wing": self._control_feedback("ext_wing_folding"),
            }
            restored = all(
                value is not None and ((value >= 0.75) if initial[name] else (value <= 0.25))
                for name, value in current.items()
            )
            timed_out = (time.monotonic() - started) * 1000 >= _ms(FEEDBACK_TIMEOUT_MS)
            if restored or timed_out:
                self._control_lock_wing(
                    initial.get("wing", False),
                    generation,
                    lambda: done(restored),
                )
                return
            QTimer.singleShot(_ms(FEEDBACK_POLL_MS), poll)

        poll()

    def _control_abort(self, reason: str = "USER ABORT") -> None:
        if not self._control_step_is_current():
            return
        self._cold_control_generation = int(getattr(self, "_cold_control_generation", 0)) + 1
        generation = self._cold_control_generation
        self._cold_control_phase = "restoring"
        self._cold_control_progress = 0
        self._cold_state = "wait_user"
        self._cold_exec_phase = "ABORT"
        self._control_set_status("ABORT / RESTORING", f"{reason}. Centering controls and restoring all mechanisms.")

        def restored(confirmed: bool) -> None:
            if not self._control_context_valid(generation):
                return
            self._cold_control_phase = "aborted"
            self._cold_control_progress = 0
            self._cold_state = "wait_user"
            self._cold_exec_phase = "ABORTED"
            if confirmed:
                detail = "Initial mechanism states restored and controls centered. Press CONTINUE."
            else:
                detail = "Restore feedback timed out. Controls are centered; verify mechanisms manually, then CONTINUE."
            self._control_set_status("CONTROL CHECK ABORTED", detail)

        self._control_restore_initial(generation, restored)

    def _control_skip(self) -> None:
        self._cold_control_phase = ""
        self._cold_state = "running"
        self._cold_step_index += 1
        self._cold_log("CONTROL CHECK SKIPPED")
        self._cold_run_next_step()

    def _control_enter(self) -> None:
        self._cold_control_step_index = self._cold_step_index
        self._cold_control_token = self._cold_sequence_token
        self._cold_control_generation = int(getattr(self, "_cold_control_generation", 0)) + 1
        self._cold_control_phase = "ask"
        self._cold_control_progress = 0
        self._cold_state = "wait_user"
        self._cold_exec_phase = "SELECT"
        self._control_set_status("CONTROL CHECK?", "SKIP continues immediately. EXECUTE starts the automatic mechanism and axis check.")

    def _cold_handle_click(self, pos) -> None:
        phase = getattr(self, "_cold_control_phase", "")
        if self._control_context_valid() and pos in (P_CONTROL_LEFT, P_CONTROL_RIGHT):
            if phase == "ask":
                if pos == P_CONTROL_LEFT:
                    self._control_skip()
                else:
                    self._control_start_sequence()
                return
            if phase == "running" and pos == P_CONTROL_LEFT:
                self._control_abort("USER ABORT")
                return
        previous_handle_click(self, pos)

    def _cold_arm_or_continue(self) -> None:
        phase = getattr(self, "_cold_control_phase", "")
        if self._control_context_valid() and phase in ("ask", "running", "restoring"):
            if phase == "ask":
                self._control_set_status("SELECT CONTROL CHECK", "Choose SKIP or EXECUTE using the on-screen buttons.")
            elif phase == "running":
                self._control_set_status(self._cold_last_action, "Check in progress. CONTINUE unlocks only at 100%.")
            else:
                self._control_set_status("ABORT / RESTORING", "Restoring initial mechanism states. Please wait.")
            return
        previous_arm_or_continue(self)

    def _cold_refresh_ui(self) -> None:
        previous_refresh_ui(self)
        cells = getattr(self, "_cold_control_cells", {})
        phase = getattr(self, "_cold_control_phase", "")
        current = self._control_context_valid()
        for cell in cells.values():
            cell.setVisible(False)
        if current and phase == "ask":
            cells["left"].setText("SKIP")
            cells["right"].setText("EXECUTE")
            cells["prompt"].setText("CONTROL CHECK?")
            cells["left"].setVisible(True)
            cells["right"].setVisible(True)
            cells["prompt"].setVisible(True)
        elif current and phase in ("running", "restoring"):
            cells["left"].setText("ABORT")
            cells["prompt"].setText("RESTORING" if phase == "restoring" else "CHECK RUNNING")
            cells["left"].setVisible(phase == "running")
            cells["prompt"].setVisible(True)
            cells["progress"].setValue(int(getattr(self, "_cold_control_progress", 0)))
            cells["progress"].setVisible(True)
        elif current and phase in ("done", "aborted"):
            cells["prompt"].setText("COMPLETE" if phase == "done" else "ABORTED")
            cells["prompt"].setVisible(True)
            cells["progress"].setValue(100 if phase == "done" else 0)
            cells["progress"].setVisible(True)

        primary = getattr(self, "_cold_cells", {}).get(P_START)
        if primary and current:
            unlocked = phase in ("done", "aborted")
            primary.setEnabled(unlocked)
            primary.setText("CONTINUE" if unlocked else "RUNNING" if phase in ("running", "restoring") else "SELECT")
        elif primary:
            primary.setEnabled(True)

    def _cold_run_next_step(self) -> None:
        if getattr(self, "_cold_state", None) == "running" and self._control_step_is_current():
            self._cold_total_steps = len(self._cold_step_list())
            self._control_enter()
            return
        previous_run_next_step(self)

    UFCKeypadWindowClass._init_cold_start_page = _init_cold_start_page
    UFCKeypadWindowClass._cold_step_list = _cold_step_list
    UFCKeypadWindowClass._control_step_is_current = _control_step_is_current
    UFCKeypadWindowClass._control_context_valid = _control_context_valid
    UFCKeypadWindowClass._control_feedback = _control_feedback
    UFCKeypadWindowClass._control_capture_initial = _control_capture_initial
    UFCKeypadWindowClass._control_send = _control_send
    UFCKeypadWindowClass._control_set_probe = _control_set_probe
    UFCKeypadWindowClass._control_set_hook = _control_set_hook
    UFCKeypadWindowClass._control_set_launch_bar = _control_set_launch_bar
    UFCKeypadWindowClass._control_set_wing = _control_set_wing
    UFCKeypadWindowClass._control_lock_wing = _control_lock_wing
    UFCKeypadWindowClass._control_set_axis = _control_set_axis
    UFCKeypadWindowClass._control_progress_segment = _control_progress_segment
    UFCKeypadWindowClass._control_after = _control_after
    UFCKeypadWindowClass._control_wait_feedback = _control_wait_feedback
    UFCKeypadWindowClass._control_set_status = _control_set_status
    UFCKeypadWindowClass._control_start_sequence = _control_start_sequence
    UFCKeypadWindowClass._control_probe_extend = _control_probe_extend
    UFCKeypadWindowClass._control_probe_retract = _control_probe_retract
    UFCKeypadWindowClass._control_hook_down = _control_hook_down
    UFCKeypadWindowClass._control_hook_up = _control_hook_up
    UFCKeypadWindowClass._control_launch_down = _control_launch_down
    UFCKeypadWindowClass._control_launch_up = _control_launch_up
    UFCKeypadWindowClass._control_wing_opposite = _control_wing_opposite
    UFCKeypadWindowClass._control_wing_restore = _control_wing_restore
    UFCKeypadWindowClass._control_mechanisms_complete = _control_mechanisms_complete
    UFCKeypadWindowClass._control_axis_hold = _control_axis_hold
    UFCKeypadWindowClass._control_axis_aft = _control_axis_aft
    UFCKeypadWindowClass._control_axis_forward = _control_axis_forward
    UFCKeypadWindowClass._control_axis_left = _control_axis_left
    UFCKeypadWindowClass._control_axis_right = _control_axis_right
    UFCKeypadWindowClass._control_rudder_left = _control_rudder_left
    UFCKeypadWindowClass._control_rudder_right = _control_rudder_right
    UFCKeypadWindowClass._control_finish = _control_finish
    UFCKeypadWindowClass._control_restore_initial = _control_restore_initial
    UFCKeypadWindowClass._control_abort = _control_abort
    UFCKeypadWindowClass._control_skip = _control_skip
    UFCKeypadWindowClass._control_enter = _control_enter
    UFCKeypadWindowClass._cold_handle_click = _cold_handle_click
    UFCKeypadWindowClass._cold_arm_or_continue = _cold_arm_or_continue
    UFCKeypadWindowClass._cold_refresh_ui = _cold_refresh_ui
    UFCKeypadWindowClass._cold_run_next_step = _cold_run_next_step
