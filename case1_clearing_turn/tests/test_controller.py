import math
import unittest

from case1_clearing_turn.audio import MockAudioNotifier
from case1_clearing_turn.controller import ClearingTurnController
from case1_clearing_turn.models import (
    AudioEvent, ClearingTurnStartRequest, ClearingTurnState, ExitReason,
)
from case1_clearing_turn.tests.helpers import drive_to_active, finish_release, frame, started_controller


class ControllerTests(unittest.TestCase):
    def test_start_validation(self):
        invalid = [
            ClearingTurnStartRequest(5, 63, 63, True, True),
            ClearingTurnStartRequest(2, 63, 63, False, True),
            ClearingTurnStartRequest(2, 63, 63, True, False),
            ClearingTurnStartRequest(2, 360, 63, True, True),
            ClearingTurnStartRequest(2, 63, math.nan, True, True),
        ]
        for request in invalid:
            with self.subTest(request=request):
                self.assertFalse(ClearingTurnController().start(request))

    def test_launch_requires_combined_signature(self):
        controller, _ = started_controller()
        controller.update(frame(0.0, weight_on_wheels=True, ias_kts=100))
        controller.update(frame(0.02, ias_kts=120, longitudinal_accel_g=1.0))
        self.assertEqual(controller.state, ClearingTurnState.WAIT_LAUNCH)
        controller.update(frame(0.04, weight_on_wheels=True, ias_kts=120))
        controller.update(frame(0.06, ias_kts=140, longitudinal_accel_g=2.0))
        self.assertEqual(controller.state, ClearingTurnState.WAIT_SAFE)

    def test_control_acquisition_audio(self):
        controller, audio = started_controller()
        drive_to_active(controller)
        self.assertTrue(controller.control_authority)
        self.assertEqual(audio.events, [AudioEvent.AUTO_TURN_ACTIVE.value])

    def test_takeover_sources_and_release(self):
        for change, source in [
            ({"pilot_roll_input": 0.2}, "ROLL_INPUT"),
            ({"pilot_disconnect_pressed": True}, "DISCONNECT_BUTTON"),
            ({"paddle_pressed": True}, "PADDLE_SWITCH"),
        ]:
            controller, audio = started_controller()
            timestamp = drive_to_active(controller)
            controller.update(frame(timestamp, **change))
            output = finish_release(controller, timestamp + 0.02)
            self.assertEqual(output.state, ClearingTurnState.ABORTED.value)
            self.assertEqual(output.exit_reason, ExitReason.PILOT_TAKEOVER.value)
            self.assertFalse(output.control_authority)
            self.assertEqual(output.roll_command, 0.0)
            self.assertEqual(audio.events.count(AudioEvent.PILOT_CONTROL.value), 1)
            self.assertEqual(controller._takeover_source, source)

    def test_invalid_numeric_fault_has_priority(self):
        controller, audio = started_controller()
        timestamp = drive_to_active(controller)
        controller.update(frame(timestamp, heading_deg=math.nan, pilot_roll_input=0.5))
        output = finish_release(controller, timestamp + 0.02)
        self.assertEqual(output.state, ClearingTurnState.FAULTED.value)
        self.assertEqual(output.audio_event, AudioEvent.AUTO_CONTROL_FAULT.value)
        self.assertNotIn(AudioEvent.PILOT_CONTROL.value, audio.events)

    def test_takeover_beats_normal_completion(self):
        controller, audio = started_controller()
        timestamp = drive_to_active(controller)
        controller.machine.transition(ClearingTurnState.REVERSING, timestamp)
        controller.machine.transition(ClearingTurnState.BRC_CAPTURE, timestamp)
        controller._complete_since = timestamp - 1.0
        controller.update(frame(timestamp + 0.02, pilot_roll_input=0.2))
        output = finish_release(controller, timestamp + 0.04)
        self.assertEqual(output.exit_reason, ExitReason.PILOT_TAKEOVER.value)
        self.assertEqual(audio.events[-1], AudioEvent.PILOT_CONTROL.value)


if __name__ == "__main__":
    unittest.main()
