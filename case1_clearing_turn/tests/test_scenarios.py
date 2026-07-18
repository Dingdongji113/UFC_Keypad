import tempfile
import unittest
from pathlib import Path

from case1_clearing_turn.models import AudioEvent
from case1_clearing_turn.simulator import ClearingTurnSimulator


class ScenarioTests(unittest.TestCase):
    def run_scenario(self, cat, launch, scenario):
        with tempfile.TemporaryDirectory() as directory:
            sim = ClearingTurnSimulator(
                catapult_id=cat, launch_heading_deg=launch, carrier_brc_deg=launch,
                scenario=scenario, log_directory=directory,
            )
            result = sim.run()
            self.assertTrue(Path(sim.logger.event_path).is_file())
            self.assertTrue(Path(sim.logger.telemetry_path).is_file())
            self.assertTrue(Path(sim.logger.summary_path).is_file())
            return result, sim.audio.events

    def test_normal_all_catapults(self):
        for cat, launch in [(1, 350), (2, 100), (3, 10), (4, 270)]:
            with self.subTest(cat=cat):
                result, audio = self.run_scenario(cat, launch, "normal")
                self.assertEqual(result.state, "COMPLETED")
                self.assertEqual(result.roll_command, 0.0)
                self.assertFalse(result.control_authority)
                self.assertEqual(audio.count(AudioEvent.CLEARING_TURN_COMPLETE.value), 1)

    def test_abort_scenarios(self):
        expected = {
            "pilot_takeover": "PILOT_TAKEOVER",
            "negative_climb": "NEGATIVE_CLIMB",
            "excessive_bank": "EXCESSIVE_BANK",
            "navigation_failure": "NAVIGATION_INVALID",
            "stale_input": "STALE_INPUT",
        }
        for scenario, reason in expected.items():
            with self.subTest(scenario=scenario):
                result, audio = self.run_scenario(2, 63, scenario)
                self.assertEqual(result.state, "ABORTED")
                self.assertEqual(result.exit_reason, reason)
                self.assertEqual(result.roll_command, 0.0)
                self.assertEqual(len(audio), 2)

    def test_audio_failure_does_not_change_result(self):
        result, audio = self.run_scenario(2, 63, "audio_failure")
        self.assertEqual(result.state, "COMPLETED")
        self.assertEqual(audio[-1], AudioEvent.CLEARING_TURN_COMPLETE.value)


if __name__ == "__main__":
    unittest.main()
