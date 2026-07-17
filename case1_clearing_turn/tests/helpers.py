from __future__ import annotations

from dataclasses import replace

from case1_clearing_turn.audio import MockAudioNotifier
from case1_clearing_turn.controller import ClearingTurnController
from case1_clearing_turn.models import ClearingTurnStartRequest, ClearingTurnState, FlightFrame


def frame(timestamp: float, **changes) -> FlightFrame:
    base = FlightFrame(
        timestamp=timestamp, heading_deg=63.0, bank_deg=0.0, roll_rate_deg_s=0.0,
        pitch_deg=8.0, ias_kts=170.0, vertical_speed_fpm=800.0, aoa_deg=7.0,
        weight_on_wheels=False, longitudinal_accel_g=1.0,
    )
    return replace(base, **changes)


def started_controller(cat: int = 2):
    audio = MockAudioNotifier()
    controller = ClearingTurnController(audio_notifier=audio)
    assert controller.start(ClearingTurnStartRequest(cat, 63.0, 63.0, True, True))
    return controller, audio


def drive_to_active(controller: ClearingTurnController) -> float:
    controller.update(frame(0.00, weight_on_wheels=True, ias_kts=110.0))
    controller.update(frame(0.02, weight_on_wheels=False, ias_kts=130.0, longitudinal_accel_g=2.0))
    timestamp = 0.04
    while controller.state != ClearingTurnState.FIRST_TURN and timestamp < 1.0:
        controller.update(frame(timestamp))
        timestamp += 0.02
    assert controller.state == ClearingTurnState.FIRST_TURN
    return timestamp


def finish_release(controller: ClearingTurnController, timestamp: float):
    output = None
    for _ in range(30):
        output = controller.update(frame(timestamp))
        timestamp += 0.02
        if controller.state in (ClearingTurnState.COMPLETED, ClearingTurnState.ABORTED, ClearingTurnState.FAULTED):
            break
    return output
