# -*- coding: utf-8 -*-
"""Standalone verification for reusable launch-trim calculation modules."""
from __future__ import annotations

from ufc.asymmetric_launch_trim import (
    asymmetric_store_moment,
    carrier_launch_asymmetric_trim,
    differential_tail_target_deg,
)
from ufc.weight_trim import carrier_launch_weight_trim, carrier_launch_weight_trim_deg


def close(a: float, b: float, tolerance: float = 1e-6) -> bool:
    return abs(a - b) <= tolerance


def main() -> None:
    # Longitudinal trim bands and boundaries.
    assert carrier_launch_weight_trim_deg(36000) == 16.0
    assert carrier_launch_weight_trim_deg(44000) == 16.0
    assert carrier_launch_weight_trim_deg(44001) == 17.0
    assert carrier_launch_weight_trim_deg(48999) == 17.0
    assert carrier_launch_weight_trim_deg(49000) == 19.0
    assert carrier_launch_weight_trim(45000).band_name == "MEDIUM"

    # Symmetric stations cancel exactly.
    symmetric = asymmetric_store_moment({2: 1000, 8: 1000})
    assert close(symmetric.signed_ft_lbs, 0.0)
    assert symmetric.heavy_side is None

    # Right station 8: 1,000 lb x 11.2 ft = +11,200 ft-lb.
    right_heavy = asymmetric_store_moment({8: 1000})
    assert close(right_heavy.signed_ft_lbs, 11200.0)
    assert right_heavy.heavy_side == "right"
    assert right_heavy.unloaded_side == "left"

    # Left station 1: 500 lb x -19.5 ft = -9,750 ft-lb.
    left_heavy = asymmetric_store_moment({1: 500})
    assert close(left_heavy.signed_ft_lbs, -9750.0)
    assert left_heavy.heavy_side == "left"

    # Graph anchors and interpolation.
    assert close(differential_tail_target_deg(11000), 2.0)
    assert close(differential_tail_target_deg(14500), 4.0)
    assert close(differential_tail_target_deg(18000), 6.0)
    assert close(differential_tail_target_deg(22000), 6.0)
    assert differential_tail_target_deg(10000) is None
    assert differential_tail_target_deg(23000) is None

    # At >=37,000 lb, a valid graph point can produce an automatic recommendation.
    decision = carrier_launch_asymmetric_trim(40000, {8: 1000})
    assert decision.auto_eligible
    assert close(decision.differential_tail_deg or 0.0, 2.0 + (200.0 / 7000.0) * 4.0)
    assert decision.trim_direction == "left_wing_down"

    # At <=36,000 lb, the conservative 6,000 ft-lb launch limit gates automation.
    limited = carrier_launch_asymmetric_trim(36000, {8: 1000})
    assert not limited.auto_eligible
    assert limited.differential_tail_deg is None

    print("ALL TRIM MODEL CHECKS PASSED")


if __name__ == "__main__":
    main()
