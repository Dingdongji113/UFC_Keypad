"""Heading math shared by the controller and simulator."""

from __future__ import annotations

import math


def normalize_heading(deg: float) -> float:
    if not math.isfinite(deg):
        raise ValueError("heading must be finite")
    return deg % 360.0


def shortest_heading_error(target: float, current: float) -> float:
    """Return signed shortest error in [-180, 180). Positive means right."""
    return (normalize_heading(target) - normalize_heading(current) + 180.0) % 360.0 - 180.0


def first_target_heading(catapult_id: int, launch_heading_deg: float, angle_deg: float = 20.0) -> float:
    if catapult_id not in (1, 2, 3, 4):
        raise ValueError("catapult_id must be 1, 2, 3, or 4")
    direction = 1.0 if catapult_id in (1, 2) else -1.0
    return normalize_heading(launch_heading_deg + direction * angle_deg)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
