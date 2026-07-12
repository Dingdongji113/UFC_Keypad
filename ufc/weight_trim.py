# -*- coding: utf-8 -*-
"""F/A-18 carrier-launch longitudinal trim calculation.

Pure calculation module only.  It does not import PyQt, open sockets, read DCS
telemetry, or send cockpit commands, so it can be reused by later workflows.
"""
from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class WeightTrimDecision:
    """Longitudinal catapult-trim decision derived from aircraft weight."""

    weight_lbs: float
    target_deg_nose_up: float
    band_name: str


def carrier_launch_weight_trim(weight_lbs: float) -> WeightTrimDecision:
    """Return the carrier-launch longitudinal trim target.

    Current project baseline:
      - <= 44,000 lb: 16 degrees nose-up
      - 44,000 < weight < 49,000 lb: 17 degrees nose-up
      - >= 49,000 lb: 19 degrees nose-up

    Raises:
        ValueError: if weight is non-finite or not positive.
    """
    weight = float(weight_lbs)
    if not math.isfinite(weight) or weight <= 0.0:
        raise ValueError(f"invalid aircraft weight: {weight_lbs!r}")

    if weight <= 44000.0:
        return WeightTrimDecision(weight, 16.0, "LIGHT")
    if weight < 49000.0:
        return WeightTrimDecision(weight, 17.0, "MEDIUM")
    return WeightTrimDecision(weight, 19.0, "HEAVY")


def carrier_launch_weight_trim_deg(weight_lbs: float) -> float:
    """Compatibility helper returning only the target angle."""
    return carrier_launch_weight_trim(weight_lbs).target_deg_nose_up
