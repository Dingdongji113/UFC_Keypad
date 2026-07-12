# -*- coding: utf-8 -*-
"""F/A-18 asymmetric-store carrier-launch trim calculations.

This is a pure, currently uncalled feature module.  It does not read DCS,
modify UI state, or send trim commands.

The module intentionally treats undocumented/ambiguous regions conservatively:
- below 11,000 ft-lb: no automatic differential-tail target is returned;
- above 22,000 ft-lb: outside the published graph;
- <= 36,000 lb launch-board weight: more than 6,000 ft-lb is rejected;
- >= 37,000 lb: more than 22,000 ft-lb is rejected;
- 36,000-37,000 lb is treated as an unresolved transition region.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Mapping, Optional


# Signed lateral arms in feet.  Left stations are negative, right positive.
# Derived from the NATOPS asymmetry-calculation table (moment per 100 lb).
STATION_ARM_FT = {
    1: -19.5,
    2: -11.2,
    3: -7.3,
    4: -3.7,
    6: 3.7,
    7: 7.3,
    8: 11.2,
    9: 19.5,
}


@dataclass(frozen=True)
class AsymmetricMoment:
    """Signed and absolute asymmetric store moment."""

    signed_ft_lbs: float
    absolute_ft_lbs: float
    heavy_side: Optional[str]
    unloaded_side: Optional[str]


@dataclass(frozen=True)
class AsymmetricLaunchTrimDecision:
    """Conservative result for asymmetric carrier-launch lateral trim."""

    moment: AsymmetricMoment
    launch_weight_lbs: float
    differential_tail_deg: Optional[float]
    trim_direction: Optional[str]
    auto_eligible: bool
    reason: str


def asymmetric_store_moment(station_weights_lbs: Mapping[int, float]) -> AsymmetricMoment:
    """Calculate signed asymmetric store moment from station total weights.

    Values should include the complete station load that contributes to lateral
    moment: store, rack/adapter, and relevant fuel mass where applicable.
    Missing supported stations are treated as zero.  Station 5 is centerline and
    therefore intentionally omitted.
    """
    signed = 0.0
    for station, weight_value in station_weights_lbs.items():
        station_num = int(station)
        if station_num == 5:
            continue
        if station_num not in STATION_ARM_FT:
            raise ValueError(f"unsupported F/A-18 station: {station_num}")
        weight = float(weight_value)
        if not math.isfinite(weight) or weight < 0.0:
            raise ValueError(f"invalid station {station_num} weight: {weight_value!r}")
        signed += weight * STATION_ARM_FT[station_num]

    absolute = abs(signed)
    if absolute < 1e-9:
        heavy_side = None
        unloaded_side = None
    elif signed > 0.0:
        heavy_side = "right"
        unloaded_side = "left"
    else:
        heavy_side = "left"
        unloaded_side = "right"

    return AsymmetricMoment(signed, absolute, heavy_side, unloaded_side)


def differential_tail_target_deg(moment_ft_lbs: float) -> Optional[float]:
    """Digitize the supplied asymmetric-store launch-trim graph.

    Returns None outside the positively defined graph segment.  The 11,000 to
    18,000 ft-lb segment is linearly interpolated from 2 to 6 degrees; 18,000 to
    22,000 ft-lb is capped at 6 degrees.
    """
    moment = abs(float(moment_ft_lbs))
    if not math.isfinite(moment):
        raise ValueError(f"invalid asymmetric moment: {moment_ft_lbs!r}")
    if 11000.0 <= moment < 18000.0:
        return 2.0 + ((moment - 11000.0) / 7000.0) * 4.0
    if 18000.0 <= moment <= 22000.0:
        return 6.0
    return None


def carrier_launch_asymmetric_trim(
    launch_weight_lbs: float,
    station_weights_lbs: Mapping[int, float],
) -> AsymmetricLaunchTrimDecision:
    """Calculate a conservative carrier-launch lateral-trim recommendation.

    `trim_direction` follows the graph wording: unloaded wing down.  This is a
    conceptual direction only; it is not mapped to DCS LEFT/RIGHT command names.
    """
    weight = float(launch_weight_lbs)
    if not math.isfinite(weight) or weight <= 0.0:
        raise ValueError(f"invalid launch weight: {launch_weight_lbs!r}")

    moment = asymmetric_store_moment(station_weights_lbs)
    absolute = moment.absolute_ft_lbs

    if absolute < 1e-9:
        return AsymmetricLaunchTrimDecision(
            moment, weight, 0.0, None, True, "symmetric loadout",
        )

    # Conservative launch-limit gate.
    if weight <= 36000.0 and absolute > 6000.0:
        return AsymmetricLaunchTrimDecision(
            moment, weight, None, None, False,
            "asymmetric moment exceeds 6,000 ft-lb limit at or below 36,000 lb",
        )
    if 36000.0 < weight < 37000.0:
        return AsymmetricLaunchTrimDecision(
            moment, weight, None, None, False,
            "36,000-37,000 lb launch-limit transition requires source confirmation",
        )
    if weight >= 37000.0 and absolute > 22000.0:
        return AsymmetricLaunchTrimDecision(
            moment, weight, None, None, False,
            "asymmetric moment exceeds 22,000 ft-lb carrier-launch limit",
        )

    target = differential_tail_target_deg(absolute)
    direction = f"{moment.unloaded_side}_wing_down" if moment.unloaded_side else None

    if target is None:
        if absolute < 11000.0:
            reason = "graph does not define an automatic target below 11,000 ft-lb"
        else:
            reason = "moment lies outside the 11,000-22,000 ft-lb graph range"
        return AsymmetricLaunchTrimDecision(
            moment, weight, None, direction, False, reason,
        )

    return AsymmetricLaunchTrimDecision(
        moment, weight, target, direction, True, "graph target available",
    )
