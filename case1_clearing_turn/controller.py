"""Clearing-turn state orchestration and suggested roll controller."""

from __future__ import annotations

import math
import uuid
from collections import deque
from dataclasses import asdict
from typing import Deque, Optional

from .audio import AudioManager, LoggingAudioNotifier
from .config import ClearingTurnConfig
from .heading import clamp, first_target_heading, normalize_heading, shortest_heading_error
from .interfaces import AudioNotifier, NullRollControlSink, RollControlSink
from .logger import NullRunLogger, RunLogger
from .models import (
    AudioEvent, ClearingTurnOutput, ClearingTurnStartRequest, ClearingTurnState,
    ExitReason, FlightFrame,
)
from .safety import evaluate_active_safety, safe_to_engage, validate_numeric_frame
from .state_machine import ALLOWED_TRANSITIONS, StateMachine


ACTIVE_STATES = {
    ClearingTurnState.FIRST_TURN,
    ClearingTurnState.REVERSING,
    ClearingTurnState.BRC_CAPTURE,
}


class ClearingTurnController:
    """Pure-Python controller whose output is advisory unless a sink is supplied."""

    def __init__(
        self,
        config: ClearingTurnConfig | None = None,
        *,
        audio_notifier: AudioNotifier | None = None,
        roll_sink: RollControlSink | None = None,
        run_logger: RunLogger | None = None,
    ):
        self.config = config or ClearingTurnConfig()
        self.config.validate()
        self.audio = AudioManager(audio_notifier or LoggingAudioNotifier())
        self.roll_sink = roll_sink or NullRollControlSink()
        self.logger = run_logger or NullRunLogger()
        self.machine = StateMachine(on_transition=self._on_transition)
        self._clear_runtime()

    @property
    def state(self) -> ClearingTurnState:
        return self.machine.state

    def _clear_runtime(self) -> None:
        self.request: Optional[ClearingTurnStartRequest] = None
        self.run_id: Optional[str] = None
        self.first_target: Optional[float] = None
        self.final_target: Optional[float] = None
        self.control_authority = False
        self.roll_command = 0.0
        self.desired_bank = 0.0
        self.heading_error = 0.0
        self.exit_reason: Optional[ExitReason] = None
        self._final_state: Optional[ClearingTurnState] = None
        self._release_duration = 0.0
        self._release_start_command = 0.0
        self._release_elapsed = 0.0
        self._safe_since: Optional[float] = None
        self._complete_since: Optional[float] = None
        self._previous_frame: Optional[FlightFrame] = None
        self._previous_ias: Optional[float] = None
        self._stale_elapsed = 0.0
        self._last_dt = self.config.default_dt_s
        self._integral = 0.0
        self._previous_command = 0.0
        self._command_sign_changes: Deque[float] = deque()
        self._max_bank = 0.0
        self._max_roll_command = 0.0
        self._start_timestamp = 0.0
        self._last_audio_event: Optional[str] = None
        self._last_event: Optional[str] = None
        self._takeover_source: Optional[str] = None

    def start(self, request: ClearingTurnStartRequest) -> bool:
        if self.state != ClearingTurnState.IDLE:
            return False
        if not self._valid_start(request):
            return False
        self._clear_runtime()
        self.audio.reset()
        self.request = request
        self.run_id = uuid.uuid4().hex
        self.first_target = first_target_heading(
            request.catapult_id, request.launch_heading_deg, self.config.first_turn_angle_deg
        )
        self.final_target = normalize_heading(request.carrier_brc_deg)
        self.logger.start(self.run_id)
        self.logger.event("run_started", request=asdict(request), first_target_heading_deg=self.first_target)
        self.machine.transition(ClearingTurnState.ARMED, 0.0)
        self.machine.transition(ClearingTurnState.WAIT_LAUNCH, 0.0)
        self._last_event = "ARMED"
        return True

    def reset(self) -> None:
        if self.state not in (ClearingTurnState.IDLE, ClearingTurnState.COMPLETED,
                              ClearingTurnState.ABORTED, ClearingTurnState.FAULTED):
            raise RuntimeError("cannot reset an active run")
        if self.state != ClearingTurnState.IDLE:
            self.machine.transition(ClearingTurnState.IDLE, 0.0)
        self.logger.close()
        self._clear_runtime()
        self.audio.reset()

    def cancel(self, timestamp: float = 0.0) -> None:
        if self.state in (ClearingTurnState.ARMED, ClearingTurnState.WAIT_LAUNCH):
            self.exit_reason = ExitReason.CANCELLED
            self.machine.transition(ClearingTurnState.ABORTED, timestamp)
            self._last_event = "CANCELLED"
        elif self.state in ACTIVE_STATES or self.state == ClearingTurnState.WAIT_SAFE:
            self._begin_exit(ExitReason.CANCELLED, ClearingTurnState.ABORTED,
                             self.config.safety_abort_release_time_s, timestamp)

    def update(self, frame: FlightFrame) -> ClearingTurnOutput:
        self._last_event = None
        self._last_audio_event = None
        try:
            self._update_impl(frame)
        except Exception as exc:
            self.logger.event("internal_exception", timestamp=frame.timestamp, error=repr(exc))
            self._force_fault(frame.timestamp, ExitReason.INTERNAL_ERROR)
        output = self._make_output()
        self.logger.telemetry(frame, output)
        return output

    def _update_impl(self, frame: FlightFrame) -> None:
        if self.state in (ClearingTurnState.IDLE, ClearingTurnState.COMPLETED,
                          ClearingTurnState.ABORTED, ClearingTurnState.FAULTED):
            return
        numeric = validate_numeric_frame(frame)
        if not numeric.ok:
            self._begin_exit(numeric.reason, ClearingTurnState.FAULTED,
                             self.config.fault_release_time_s, frame.timestamp)
            return
        dt = self._frame_dt(frame)
        if self.state == ClearingTurnState.EXITING:
            self._finish_exit(frame, dt)
            self._previous_frame = frame
            return
        if self._input_is_stale(frame, dt):
            self._begin_exit(ExitReason.STALE_INPUT, ClearingTurnState.ABORTED,
                             self.config.safety_abort_release_time_s, frame.timestamp)
            return

        if self.state in ACTIVE_STATES:
            source = self._takeover_trigger(frame)
            if source:
                self._takeover_source = source
                self._begin_exit(ExitReason.PILOT_TAKEOVER, ClearingTurnState.ABORTED,
                                 self.config.pilot_takeover_release_time_s, frame.timestamp)
                return

        if self.state in ACTIVE_STATES or self.state == ClearingTurnState.WAIT_SAFE:
            result = evaluate_active_safety(frame, self.config)
            if not result.ok:
                final = ClearingTurnState.FAULTED if result.is_fault else ClearingTurnState.ABORTED
                duration = self.config.fault_release_time_s if result.is_fault else self.config.safety_abort_release_time_s
                self._begin_exit(result.reason, final, duration, frame.timestamp)
                return

        timeout = (
            self.config.wait_safe_timeout_s
            if self.state == ClearingTurnState.WAIT_SAFE
            else self.config.max_state_duration_s.get(self.state.value)
        )
        if timeout is not None and self.machine.elapsed(frame.timestamp) > timeout:
            reason = ExitReason.SAFE_CONDITION_TIMEOUT if self.state == ClearingTurnState.WAIT_SAFE else ExitReason.STATE_TIMEOUT
            self._begin_exit(reason, ClearingTurnState.ABORTED,
                             self.config.safety_abort_release_time_s, frame.timestamp)
            return

        if self.state == ClearingTurnState.WAIT_LAUNCH:
            self._wait_launch(frame)
        elif self.state == ClearingTurnState.WAIT_SAFE:
            self._wait_safe(frame)
        elif self.state == ClearingTurnState.FIRST_TURN:
            self._first_turn(frame, dt)
        elif self.state == ClearingTurnState.REVERSING:
            self._reversing(frame, dt)
        elif self.state == ClearingTurnState.BRC_CAPTURE:
            self._brc_capture(frame, dt)

        self._previous_frame = frame
        self._previous_ias = frame.ias_kts
        self._max_bank = max(self._max_bank, abs(frame.bank_deg))
        self._max_roll_command = max(self._max_roll_command, abs(self.roll_command))

    def _wait_launch(self, frame: FlightFrame) -> None:
        previous = self._previous_frame
        speed_rise = 0.0 if self._previous_ias is None else frame.ias_kts - self._previous_ias
        launched = (
            previous is not None
            and previous.weight_on_wheels
            and not frame.weight_on_wheels
            and frame.longitudinal_accel_g >= self.config.launch_accel_threshold_g
            and speed_rise >= self.config.launch_airspeed_rise_kts
        )
        if launched:
            self._start_timestamp = frame.timestamp
            self.machine.transition(ClearingTurnState.WAIT_SAFE, frame.timestamp)
            self._last_event = "LAUNCH_DETECTED"

    def _wait_safe(self, frame: FlightFrame) -> None:
        if safe_to_engage(frame, self.config):
            self._safe_since = self._safe_since if self._safe_since is not None else frame.timestamp
            if frame.timestamp - self._safe_since >= self.config.safe_condition_hold_s:
                self.machine.transition(ClearingTurnState.FIRST_TURN, frame.timestamp)
                self.control_authority = True
                self._reset_pid()
                self._last_event = "CONTROL_ACQUIRED"
                self._last_audio_event = self.audio.emit_once([AudioEvent.AUTO_TURN_ACTIVE])
        else:
            self._safe_since = None

    def _first_turn(self, frame: FlightFrame, dt: float) -> None:
        self.heading_error = shortest_heading_error(self.first_target, frame.heading_deg)
        direction = 1.0 if self.request.catapult_id in (1, 2) else -1.0
        directional_error = direction * self.heading_error
        self.desired_bank = direction * min(
            self.config.first_turn_bank_deg, self.config.max_commanded_bank_deg,
            max(0.0, abs(self.heading_error) * self.config.first_heading_to_bank_gain),
        )
        self._control_bank(frame, dt)
        if directional_error <= self.config.reverse_lead_deg:
            self.machine.transition(ClearingTurnState.REVERSING, frame.timestamp)
            self._reset_pid()
            self._last_event = "FIRST_TARGET_REACHED"

    def _reversing(self, frame: FlightFrame, dt: float) -> None:
        self.heading_error = shortest_heading_error(self.final_target, frame.heading_deg)
        capture_limit = min(self.config.capture_bank_deg, self.config.max_commanded_bank_deg)
        self.desired_bank = clamp(
            self.heading_error * self.config.capture_heading_to_bank_gain,
            -capture_limit,
            capture_limit,
        )
        self._control_bank(frame, dt)
        desired_sign = 1.0 if self.heading_error > 0 else -1.0
        if abs(self.heading_error) < 0.1:
            desired_sign = 0.0
        established = desired_sign == 0.0 or (
            frame.bank_deg * desired_sign > 1.0 and frame.roll_rate_deg_s * desired_sign > 0.2
        )
        if established:
            self.machine.transition(ClearingTurnState.BRC_CAPTURE, frame.timestamp)
            self._reset_pid()
            self._last_event = "REVERSE_ROLL_ESTABLISHED"

    def _brc_capture(self, frame: FlightFrame, dt: float) -> None:
        self.heading_error = shortest_heading_error(self.final_target, frame.heading_deg)
        capture_limit = min(self.config.capture_bank_deg, self.config.max_commanded_bank_deg)
        self.desired_bank = clamp(
            self.heading_error * self.config.capture_heading_to_bank_gain,
            -capture_limit,
            capture_limit,
        )
        self._control_bank(frame, dt)
        complete = (
            abs(self.heading_error) <= self.config.complete_heading_tolerance_deg
            and abs(frame.bank_deg) <= self.config.complete_bank_tolerance_deg
            and abs(frame.roll_rate_deg_s) <= self.config.complete_roll_rate_tolerance_deg_s
        )
        if complete:
            self._complete_since = self._complete_since if self._complete_since is not None else frame.timestamp
            if frame.timestamp - self._complete_since >= self.config.complete_hold_s:
                self._begin_exit(ExitReason.NORMAL_COMPLETE, ClearingTurnState.COMPLETED,
                                 self.config.normal_release_time_s, frame.timestamp)
        else:
            self._complete_since = None

    def _control_bank(self, frame: FlightFrame, dt: float) -> None:
        bank_error = self.desired_bank - frame.bank_deg
        pid = self.config.pid
        candidate_integral = clamp(
            self._integral + bank_error * dt, -pid.integral_limit, pid.integral_limit
        )
        raw = pid.kp * bank_error + pid.ki * candidate_integral - pid.kd * frame.roll_rate_deg_s
        if abs(frame.roll_rate_deg_s) >= self.config.max_roll_rate_command_deg_s:
            if raw * frame.roll_rate_deg_s > 0:
                raw = 0.0
        saturated = clamp(raw, -1.0, 1.0)
        if raw == saturated or raw * bank_error < 0:
            self._integral = candidate_integral
        max_delta = pid.output_rate_limit_per_s * dt
        command = clamp(saturated, self._previous_command - max_delta, self._previous_command + max_delta)
        command = clamp(command, -1.0, 1.0)
        if command * self._previous_command < -0.0025:
            self._command_sign_changes.append(frame.timestamp)
        while self._command_sign_changes and frame.timestamp - self._command_sign_changes[0] > 2.0:
            self._command_sign_changes.popleft()
        if len(self._command_sign_changes) >= 8:
            self._begin_exit(ExitReason.CONTROLLER_OSCILLATION, ClearingTurnState.ABORTED,
                             self.config.safety_abort_release_time_s, frame.timestamp)
            return
        self.roll_command = command
        self._previous_command = command
        self.roll_sink.set_roll_command(command)

    def _begin_exit(self, reason: ExitReason | None, final_state: ClearingTurnState,
                    release_duration: float, timestamp: float) -> None:
        if reason is None:
            reason = ExitReason.INTERNAL_ERROR
        if self.state == ClearingTurnState.EXITING:
            return
        if self.state in (ClearingTurnState.ARMED, ClearingTurnState.WAIT_LAUNCH) and not self.control_authority:
            self.exit_reason = reason
            self.machine.transition(final_state, timestamp)
            self._last_event = "EXIT_WITHOUT_AUTHORITY"
            return
        self.exit_reason = reason
        self._final_state = final_state
        self._release_duration = max(0.0, release_duration)
        self._release_start_command = self.roll_command
        self._release_elapsed = 0.0
        self.machine.transition(ClearingTurnState.EXITING, timestamp)
        self._last_event = "RELEASE_STARTED"
        if self._release_duration == 0.0:
            self._finish_exit_at(timestamp)

    def _finish_exit(self, frame: FlightFrame, dt: float) -> None:
        self._release_elapsed += max(self.config.default_dt_s, dt)
        fraction = 1.0 if self._release_duration <= 0 else min(1.0, self._release_elapsed / self._release_duration)
        self.roll_command = self._release_start_command * (1.0 - fraction)
        self.desired_bank = 0.0
        self.roll_sink.set_roll_command(self.roll_command)
        if fraction >= 1.0 or abs(self.roll_command) <= 1e-6:
            self._finish_exit_at(frame.timestamp)

    def _finish_exit_at(self, timestamp: float) -> None:
        self.roll_command = 0.0
        self.desired_bank = 0.0
        self.control_authority = False
        self.roll_sink.release()
        event = self._exit_audio_event()
        self._last_audio_event = self.audio.emit_once([event]) if event else None
        final = self._final_state or ClearingTurnState.FAULTED
        self.machine.transition(final, timestamp)
        self._last_event = "CONTROL_RELEASED"
        self._write_summary(timestamp)

    def _force_fault(self, timestamp: float, reason: ExitReason) -> None:
        self.roll_command = 0.0
        self.desired_bank = 0.0
        self.control_authority = False
        self.exit_reason = reason
        self.roll_sink.release()
        self._last_audio_event = self.audio.emit_once([AudioEvent.AUTO_CONTROL_FAULT])
        if self.state == ClearingTurnState.EXITING:
            self.machine.transition(ClearingTurnState.FAULTED, timestamp)
        elif self.state not in (ClearingTurnState.IDLE, ClearingTurnState.COMPLETED,
                                ClearingTurnState.ABORTED, ClearingTurnState.FAULTED):
            # Route through EXITING when required by the explicit graph.
            if ClearingTurnState.EXITING in ALLOWED_TRANSITIONS[self.state]:
                self.machine.transition(ClearingTurnState.EXITING, timestamp)
                self.machine.transition(ClearingTurnState.FAULTED, timestamp)
            else:
                self.machine.transition(ClearingTurnState.FAULTED, timestamp)

    def _frame_dt(self, frame: FlightFrame) -> float:
        if self._previous_frame is None:
            return self.config.default_dt_s
        raw = frame.timestamp - self._previous_frame.timestamp
        if raw > 0:
            self._last_dt = min(raw, self.config.max_input_gap_s)
        return self._last_dt

    def _input_is_stale(self, frame: FlightFrame, dt: float) -> bool:
        if self._previous_frame is None:
            return False
        delta = frame.timestamp - self._previous_frame.timestamp
        if delta < 0 or delta > self.config.max_input_gap_s:
            return True
        self._stale_elapsed = self._stale_elapsed + dt if delta == 0 else 0.0
        return self._stale_elapsed >= self.config.stale_input_timeout_s

    def _takeover_trigger(self, frame: FlightFrame) -> Optional[str]:
        if frame.pilot_disconnect_pressed:
            return "DISCONNECT_BUTTON"
        if frame.paddle_pressed:
            return "PADDLE_SWITCH"
        if abs(frame.pilot_roll_input) >= self.config.takeover_threshold:
            return "ROLL_INPUT"
        return None

    def _reset_pid(self) -> None:
        self._integral = 0.0
        self._previous_command = self.roll_command

    def _valid_start(self, request: ClearingTurnStartRequest) -> bool:
        return (
            request.catapult_id in (1, 2, 3, 4)
            and request.auto_trim_completed
            and request.trim_check_passed
            and math.isfinite(request.launch_heading_deg)
            and math.isfinite(request.carrier_brc_deg)
            and 0.0 <= request.launch_heading_deg < 360.0
            and 0.0 <= request.carrier_brc_deg < 360.0
        )

    def _exit_audio_event(self) -> Optional[AudioEvent]:
        if self._final_state == ClearingTurnState.FAULTED:
            return AudioEvent.AUTO_CONTROL_FAULT
        if self.exit_reason == ExitReason.PILOT_TAKEOVER:
            return AudioEvent.PILOT_CONTROL
        if self._final_state == ClearingTurnState.COMPLETED:
            return AudioEvent.CLEARING_TURN_COMPLETE
        return AudioEvent.AUTO_TURN_ABORT

    def _on_transition(self, old: ClearingTurnState, new: ClearingTurnState, timestamp: float) -> None:
        self.logger.event(
            "state_transition", timestamp=timestamp, old_state=old.value, new_state=new.value,
            catapult_id=self.request.catapult_id if self.request else None,
            launch_heading_deg=self.request.launch_heading_deg if self.request else None,
            carrier_brc_deg=self.request.carrier_brc_deg if self.request else None,
            exit_reason=self.exit_reason.value if self.exit_reason else None,
        )

    def _write_summary(self, timestamp: float) -> None:
        self.logger.summary({
            "run_id": self.run_id,
            "result": (self._final_state or self.state).value,
            "exit_reason": self.exit_reason.value if self.exit_reason else None,
            "catapult_id": self.request.catapult_id if self.request else None,
            "launch_heading_deg": self.request.launch_heading_deg if self.request else None,
            "carrier_brc_deg": self.final_target,
            "first_target_heading_deg": self.first_target,
            "duration_s": max(0.0, timestamp - self._start_timestamp),
            "max_bank_deg": self._max_bank,
            "max_roll_command": self._max_roll_command,
            "audio_event": self._last_audio_event,
            "audio_played": bool(self._last_audio_event) and not self.audio.last_failed,
            "audio_failed": self.audio.last_failed,
            "takeover_source": self._takeover_source,
        })

    def _make_output(self) -> ClearingTurnOutput:
        target = None
        if self.state == ClearingTurnState.FIRST_TURN:
            target = self.first_target
        elif self.state in (ClearingTurnState.REVERSING, ClearingTurnState.BRC_CAPTURE):
            target = self.final_target
        status = self.state.value.replace("_", " ").title()
        if self.audio.last_failed and self._last_audio_event:
            status += " (audio_failed)"
        return ClearingTurnOutput(
            state=self.state.value,
            roll_command=clamp(self.roll_command, -1.0, 1.0),
            control_authority=self.control_authority,
            active_target_heading_deg=target,
            desired_bank_deg=self.desired_bank,
            heading_error_deg=self.heading_error,
            event=self._last_event,
            exit_reason=self.exit_reason.value if self.exit_reason else None,
            audio_event=self._last_audio_event,
            status_text=status,
        )
