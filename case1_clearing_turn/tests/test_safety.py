import math
import unittest

from case1_clearing_turn.config import ClearingTurnConfig
from case1_clearing_turn.models import ExitReason
from case1_clearing_turn.safety import evaluate_active_safety, safe_to_engage, validate_numeric_frame
from case1_clearing_turn.tests.helpers import frame


class SafetyTests(unittest.TestCase):
    def setUp(self):
        self.config = ClearingTurnConfig()

    def test_safe_to_engage(self):
        self.assertTrue(safe_to_engage(frame(1.0), self.config))
        self.assertFalse(safe_to_engage(frame(1.0, weight_on_wheels=True), self.config))

    def test_safety_reasons(self):
        cases = [
            ({"vertical_speed_fpm": -500}, ExitReason.NEGATIVE_CLIMB),
            ({"bank_deg": 30}, ExitReason.EXCESSIVE_BANK),
            ({"pitch_deg": 30}, ExitReason.ABNORMAL_PITCH),
            ({"aoa_deg": 20}, ExitReason.EXCESSIVE_AOA),
            ({"fcs_fault": True}, ExitReason.FCS_FAULT),
            ({"hydraulic_fault": True}, ExitReason.HYDRAULIC_FAULT),
            ({"engine_fault": True}, ExitReason.ENGINE_FAULT),
            ({"navigation_valid": False}, ExitReason.NAVIGATION_INVALID),
        ]
        for changes, reason in cases:
            with self.subTest(reason=reason):
                self.assertEqual(evaluate_active_safety(frame(1.0, **changes), self.config).reason, reason)

    def test_nan_is_fault(self):
        result = validate_numeric_frame(frame(1.0, heading_deg=math.nan))
        self.assertEqual(result.reason, ExitReason.INVALID_NUMERIC_DATA)
        self.assertTrue(result.is_fault)


if __name__ == "__main__":
    unittest.main()
