"""Safety and data-integrity checks, independent of control logic."""

from __future__ import annotations

import math

from .config import ClearingTurnConfig
from .models import ExitReason, FlightFrame, SafetyResult


NUMERIC_FIELDS = (
    "timestamp", "heading_deg", "bank_deg", "roll_rate_deg_s", "pitch_deg",
    "ias_kts", "vertical_speed_fpm", "aoa_deg", "longitudinal_accel_g", "pilot_roll_input",
)


def validate_numeric_frame(frame: FlightFrame) -> SafetyResult:
    if any(not math.isfinite(float(getattr(frame, name))) for name in NUMERIC_FIELDS):
        return SafetyResult(ExitReason.INVALID_NUMERIC_DATA, is_fault=True)
    if not -1.0 <= frame.pilot_roll_input <= 1.0:
        return SafetyResult(ExitReason.INVALID_NUMERIC_DATA, is_fault=True)
    return SafetyResult()


def evaluate_active_safety(frame: FlightFrame, config: ClearingTurnConfig) -> SafetyResult:
    numeric = validate_numeric_frame(frame)
    if not numeric.ok:
        return numeric
    if frame.fcs_fault:
        return SafetyResult(ExitReason.FCS_FAULT)
    if frame.hydraulic_fault:
        return SafetyResult(ExitReason.HYDRAULIC_FAULT)
    if frame.engine_fault:
        return SafetyResult(ExitReason.ENGINE_FAULT)
    if not frame.navigation_valid:
        return SafetyResult(ExitReason.NAVIGATION_INVALID)
    if frame.vertical_speed_fpm < config.negative_vs_limit_fpm:
        return SafetyResult(ExitReason.NEGATIVE_CLIMB)
    if abs(frame.bank_deg) > config.max_allowed_bank_deg:
        return SafetyResult(ExitReason.EXCESSIVE_BANK)
    if not config.pitch_min_deg <= frame.pitch_deg <= config.pitch_max_deg:
        return SafetyResult(ExitReason.ABNORMAL_PITCH)
    if not config.aoa_min_deg <= frame.aoa_deg <= config.aoa_max_deg:
        return SafetyResult(ExitReason.EXCESSIVE_AOA)
    return SafetyResult()


def safe_to_engage(frame: FlightFrame, config: ClearingTurnConfig) -> bool:
    return (
        not frame.weight_on_wheels
        and frame.vertical_speed_fpm >= config.minimum_positive_vs_fpm
        and frame.ias_kts >= config.safe_ias_kts
        and abs(frame.bank_deg) <= config.safe_bank_entry_deg
        and config.safe_pitch_min_deg <= frame.pitch_deg <= config.safe_pitch_max_deg
        and frame.navigation_valid
        and not (frame.fcs_fault or frame.hydraulic_fault or frame.engine_fault)
        and validate_numeric_frame(frame).ok
    )
