"""Public data models and stable event identifiers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ClearingTurnState(str, Enum):
    IDLE = "IDLE"
    ARMED = "ARMED"
    WAIT_LAUNCH = "WAIT_LAUNCH"
    WAIT_SAFE = "WAIT_SAFE"
    FIRST_TURN = "FIRST_TURN"
    REVERSING = "REVERSING"
    BRC_CAPTURE = "BRC_CAPTURE"
    EXITING = "EXITING"
    COMPLETED = "COMPLETED"
    ABORTED = "ABORTED"
    FAULTED = "FAULTED"


class AudioEvent(str, Enum):
    AUTO_TURN_ACTIVE = "AUTO_TURN_ACTIVE"
    CLEARING_TURN_COMPLETE = "CLEARING_TURN_COMPLETE"
    PILOT_CONTROL = "PILOT_CONTROL"
    AUTO_TURN_ABORT = "AUTO_TURN_ABORT"
    AUTO_CONTROL_FAULT = "AUTO_CONTROL_FAULT"


class ExitReason(str, Enum):
    NORMAL_COMPLETE = "NORMAL_COMPLETE"
    PILOT_TAKEOVER = "PILOT_TAKEOVER"
    CANCELLED = "CANCELLED"
    SAFE_CONDITION_TIMEOUT = "SAFE_CONDITION_TIMEOUT"
    NEGATIVE_CLIMB = "NEGATIVE_CLIMB"
    EXCESSIVE_BANK = "EXCESSIVE_BANK"
    ABNORMAL_PITCH = "ABNORMAL_PITCH"
    EXCESSIVE_AOA = "EXCESSIVE_AOA"
    FCS_FAULT = "FCS_FAULT"
    HYDRAULIC_FAULT = "HYDRAULIC_FAULT"
    ENGINE_FAULT = "ENGINE_FAULT"
    NAVIGATION_INVALID = "NAVIGATION_INVALID"
    CONTROLLER_OSCILLATION = "CONTROLLER_OSCILLATION"
    STATE_TIMEOUT = "STATE_TIMEOUT"
    STALE_INPUT = "STALE_INPUT"
    INVALID_NUMERIC_DATA = "INVALID_NUMERIC_DATA"
    INVALID_START_REQUEST = "INVALID_START_REQUEST"
    INTERNAL_ERROR = "INTERNAL_ERROR"


@dataclass(frozen=True)
class FlightFrame:
    timestamp: float
    heading_deg: float
    bank_deg: float
    roll_rate_deg_s: float
    pitch_deg: float
    ias_kts: float
    vertical_speed_fpm: float
    aoa_deg: float
    weight_on_wheels: bool
    longitudinal_accel_g: float
    pilot_roll_input: float = 0.0
    pilot_disconnect_pressed: bool = False
    paddle_pressed: bool = False
    fcs_fault: bool = False
    hydraulic_fault: bool = False
    engine_fault: bool = False
    navigation_valid: bool = True


@dataclass(frozen=True)
class ClearingTurnStartRequest:
    catapult_id: int
    launch_heading_deg: float
    carrier_brc_deg: float
    trim_check_passed: bool
    auto_trim_completed: bool


@dataclass(frozen=True)
class ClearingTurnOutput:
    state: str
    roll_command: float
    control_authority: bool
    active_target_heading_deg: Optional[float]
    desired_bank_deg: float
    heading_error_deg: float
    event: Optional[str]
    exit_reason: Optional[str]
    audio_event: Optional[str]
    status_text: str


@dataclass(frozen=True)
class SafetyResult:
    reason: Optional[ExitReason] = None
    is_fault: bool = False

    @property
    def ok(self) -> bool:
        return self.reason is None
