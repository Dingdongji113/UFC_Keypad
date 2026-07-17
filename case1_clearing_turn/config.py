"""Central, dependency-free configuration loading and validation."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Mapping


@dataclass
class PIDConfig:
    kp: float = 0.055
    ki: float = 0.010
    kd: float = 0.018
    integral_limit: float = 15.0
    output_rate_limit_per_s: float = 3.5


@dataclass
class AudioConfig:
    enabled: bool = True
    test_mode: bool = True
    active: str = "case1_clearing_turn/audio/auto_turn_active.wav"
    complete: str = "case1_clearing_turn/audio/clearing_turn_complete.wav"
    pilot_control: str = "case1_clearing_turn/audio/pilot_control.wav"
    abort: str = "case1_clearing_turn/audio/auto_turn_abort.wav"
    fault: str = "case1_clearing_turn/audio/auto_control_fault.wav"

    def event_paths(self) -> Dict[str, str]:
        return {
            "AUTO_TURN_ACTIVE": self.active,
            "CLEARING_TURN_COMPLETE": self.complete,
            "PILOT_CONTROL": self.pilot_control,
            "AUTO_TURN_ABORT": self.abort,
            "AUTO_CONTROL_FAULT": self.fault,
        }


@dataclass
class ClearingTurnConfig:
    first_turn_angle_deg: float = 20.0
    safe_ias_kts: float = 150.0
    minimum_positive_vs_fpm: float = 300.0
    safe_condition_hold_s: float = 0.5
    wait_safe_timeout_s: float = 5.0
    launch_accel_threshold_g: float = 1.25
    launch_airspeed_rise_kts: float = 8.0
    safe_bank_entry_deg: float = 8.0
    safe_pitch_min_deg: float = -5.0
    safe_pitch_max_deg: float = 20.0
    first_turn_bank_deg: float = 12.0
    capture_bank_deg: float = 10.0
    max_commanded_bank_deg: float = 18.0
    max_allowed_bank_deg: float = 25.0
    max_roll_rate_command_deg_s: float = 8.0
    reverse_lead_deg: float = 2.5
    complete_heading_tolerance_deg: float = 1.5
    complete_bank_tolerance_deg: float = 3.0
    complete_roll_rate_tolerance_deg_s: float = 2.0
    complete_hold_s: float = 0.5
    takeover_threshold: float = 0.10
    negative_vs_limit_fpm: float = -200.0
    pitch_min_deg: float = -10.0
    pitch_max_deg: float = 25.0
    aoa_min_deg: float = -5.0
    aoa_max_deg: float = 18.0
    stale_input_timeout_s: float = 0.5
    max_input_gap_s: float = 0.5
    normal_release_time_s: float = 0.25
    pilot_takeover_release_time_s: float = 0.10
    safety_abort_release_time_s: float = 0.05
    fault_release_time_s: float = 0.05
    first_heading_to_bank_gain: float = 0.8
    capture_heading_to_bank_gain: float = 0.65
    default_dt_s: float = 0.02
    max_state_duration_s: Dict[str, float] = field(default_factory=lambda: {
        "WAIT_LAUNCH": 30.0,
        "WAIT_SAFE": 5.0,
        "FIRST_TURN": 8.0,
        "REVERSING": 5.0,
        "BRC_CAPTURE": 12.0,
    })
    pid: PIDConfig = field(default_factory=PIDConfig)

    def validate(self) -> None:
        positive = (
            "first_turn_angle_deg", "safe_ias_kts", "safe_condition_hold_s",
            "wait_safe_timeout_s", "max_commanded_bank_deg", "max_allowed_bank_deg",
            "complete_hold_s", "takeover_threshold", "default_dt_s",
        )
        for name in positive:
            if float(getattr(self, name)) <= 0:
                raise ValueError(f"{name} must be positive")
        if self.max_commanded_bank_deg > self.max_allowed_bank_deg:
            raise ValueError("commanded bank cannot exceed allowed bank")
        if self.first_turn_bank_deg > self.max_commanded_bank_deg:
            raise ValueError("first-turn bank cannot exceed commanded bank limit")
        if self.capture_bank_deg > self.max_commanded_bank_deg:
            raise ValueError("capture bank cannot exceed commanded bank limit")
        if not 0.0 < self.takeover_threshold <= 1.0:
            raise ValueError("takeover_threshold must be in (0, 1]")

    @classmethod
    def from_json(cls, path: str | Path) -> "ClearingTurnConfig":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        raw = dict(raw.get("clearing_turn", raw))
        pid_raw = raw.pop("pid", {})
        config = cls(**raw, pid=PIDConfig(**pid_raw))
        config.validate()
        return config

    def to_dict(self) -> Mapping[str, Any]:
        return asdict(self)


@dataclass
class ModuleConfig:
    clearing_turn: ClearingTurnConfig = field(default_factory=ClearingTurnConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)

    @classmethod
    def from_json(cls, path: str | Path) -> "ModuleConfig":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        turn_raw = dict(raw.get("clearing_turn", raw))
        pid = PIDConfig(**turn_raw.pop("pid", {}))
        turn = ClearingTurnConfig(**turn_raw, pid=pid)
        turn.validate()
        return cls(clearing_turn=turn, audio=AudioConfig(**raw.get("audio", {})))
