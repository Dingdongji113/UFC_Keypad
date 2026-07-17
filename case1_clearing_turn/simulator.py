"""Deterministic lateral-dynamics simulator and command-line demonstration."""

from __future__ import annotations

import argparse
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import List

from .audio import MockAudioNotifier
from .config import ClearingTurnConfig, ModuleConfig
from .controller import ClearingTurnController
from .heading import normalize_heading
from .interfaces import SimulatorRollControlSink
from .logger import RunLogger
from .models import ClearingTurnStartRequest, ClearingTurnState, FlightFrame


SCENARIOS = (
    "normal", "pilot_takeover", "negative_climb", "excessive_bank",
    "navigation_failure", "stale_input", "audio_failure",
)


@dataclass
class SimState:
    timestamp: float
    heading_deg: float
    bank_deg: float = 0.0
    roll_rate_deg_s: float = 0.0
    ias_kts: float = 120.0
    vertical_speed_fpm: float = 0.0
    wow: bool = True
    accel_g: float = 0.2


class ClearingTurnSimulator:
    def __init__(self, *, catapult_id: int, launch_heading_deg: float, carrier_brc_deg: float,
                 scenario: str = "normal", seed: int = 1, dt: float = 0.02,
                 log_directory: str | Path = "clearing_turn_logs",
                 config: ClearingTurnConfig | None = None):
        if scenario not in SCENARIOS:
            raise ValueError(f"unknown scenario: {scenario}")
        self.dt = dt
        self.scenario = scenario
        self.random = random.Random(seed)
        self.state = SimState(0.0, normalize_heading(launch_heading_deg))
        self.sink = SimulatorRollControlSink()
        self.audio = MockAudioNotifier(fail=scenario == "audio_failure")
        self.logger = RunLogger(log_directory)
        self.controller = ClearingTurnController(
            config, audio_notifier=self.audio, roll_sink=self.sink, run_logger=self.logger
        )
        request = ClearingTurnStartRequest(
            catapult_id=catapult_id,
            launch_heading_deg=normalize_heading(launch_heading_deg),
            carrier_brc_deg=normalize_heading(carrier_brc_deg),
            trim_check_passed=True,
            auto_trim_completed=True,
        )
        if not self.controller.start(request):
            raise ValueError("start request was rejected")
        self.outputs = []
        self._injected = False
        self._frozen_timestamp = None

    def _launch_profile(self) -> None:
        t = self.state.timestamp
        if t < 0.10:
            self.state.wow = True
            self.state.ias_kts = 120.0
            self.state.vertical_speed_fpm = 0.0
            self.state.accel_g = 0.2
        elif t < 0.14:
            self.state.wow = False
            self.state.ias_kts = 140.0
            self.state.vertical_speed_fpm = 200.0
            self.state.accel_g = 2.0
        else:
            self.state.wow = False
            self.state.ias_kts = min(300.0, 170.0 + (t - 0.14) * 10.0)
            self.state.vertical_speed_fpm = 800.0
            self.state.accel_g = 1.0

    def _frame(self) -> FlightFrame:
        active = self.controller.state in {
            ClearingTurnState.FIRST_TURN, ClearingTurnState.REVERSING, ClearingTurnState.BRC_CAPTURE
        }
        pilot_input = 0.0
        negative_vs = False
        excessive_bank = False
        nav_valid = True
        if active and not self._injected and self.controller.machine.elapsed(self.state.timestamp) > 0.8:
            if self.scenario == "pilot_takeover":
                pilot_input = 0.25
                self._injected = True
            elif self.scenario == "negative_climb":
                negative_vs = True
                self._injected = True
            elif self.scenario == "excessive_bank":
                excessive_bank = True
                self._injected = True
            elif self.scenario == "navigation_failure":
                nav_valid = False
                self._injected = True
            elif self.scenario == "stale_input":
                self._frozen_timestamp = self.state.timestamp
                self._injected = True
        timestamp = self._frozen_timestamp if self._frozen_timestamp is not None else self.state.timestamp
        return FlightFrame(
            timestamp=timestamp,
            heading_deg=self.state.heading_deg,
            bank_deg=30.0 if excessive_bank else self.state.bank_deg,
            roll_rate_deg_s=self.state.roll_rate_deg_s,
            pitch_deg=8.0,
            ias_kts=self.state.ias_kts,
            vertical_speed_fpm=-500.0 if negative_vs else self.state.vertical_speed_fpm,
            aoa_deg=7.0,
            weight_on_wheels=self.state.wow,
            longitudinal_accel_g=self.state.accel_g,
            pilot_roll_input=pilot_input,
            navigation_valid=nav_valid,
        )

    def _integrate(self) -> None:
        command = self.sink.value
        noise = self.random.gauss(0.0, 0.02)
        roll_accel = command * 45.0 - self.state.roll_rate_deg_s * 3.2 + noise
        self.state.roll_rate_deg_s += roll_accel * self.dt
        self.state.roll_rate_deg_s = max(-8.0, min(8.0, self.state.roll_rate_deg_s))
        self.state.bank_deg += self.state.roll_rate_deg_s * self.dt
        self.state.heading_deg = normalize_heading(
            self.state.heading_deg + self.state.bank_deg * 0.30 * self.dt
        )

    def run(self, max_time_s: float = 35.0):
        terminal = {ClearingTurnState.COMPLETED, ClearingTurnState.ABORTED, ClearingTurnState.FAULTED}
        wall_sim_time = 0.0
        while wall_sim_time <= max_time_s and self.controller.state not in terminal:
            self._launch_profile()
            output = self.controller.update(self._frame())
            self.outputs.append(output)
            self._integrate()
            self.state.timestamp += self.dt
            wall_sim_time += self.dt
        self.logger.close()
        return self.outputs[-1]


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Standalone F/A-18C Case I clearing-turn simulator")
    parser.add_argument("--cat", type=int, choices=(1, 2, 3, 4), required=True)
    parser.add_argument("--launch-heading", type=float, required=True)
    parser.add_argument("--brc", type=float, required=True)
    parser.add_argument("--scenario", choices=SCENARIOS, default="normal")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--log-dir", type=Path, default=Path("clearing_turn_logs"))
    args = parser.parse_args(argv)
    config = ModuleConfig.from_json(args.config).clearing_turn if args.config else ClearingTurnConfig()
    simulator = ClearingTurnSimulator(
        catapult_id=args.cat, launch_heading_deg=args.launch_heading, carrier_brc_deg=args.brc,
        scenario=args.scenario, seed=args.seed, log_directory=args.log_dir, config=config,
    )
    result = simulator.run()
    last_state = None
    for output in simulator.outputs:
        if output.state != last_state or output.audio_event:
            print(
                f"{output.state:12s} command={output.roll_command:+.3f} "
                f"target={output.active_target_heading_deg!s:>6s} audio={output.audio_event or '-'}"
            )
            last_state = output.state
    summary_path = simulator.logger.summary_path
    print(json.dumps({
        "result": result.state,
        "exit_reason": result.exit_reason,
        "audio_events": simulator.audio.events,
        "summary": str(summary_path) if summary_path else None,
    }, indent=2))
    return 0 if result.state in ("COMPLETED", "ABORTED", "FAULTED") else 1


if __name__ == "__main__":
    raise SystemExit(main())
