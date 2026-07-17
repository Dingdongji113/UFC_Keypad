"""Per-run JSONL/CSV telemetry and final-summary writer."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Optional

from .models import ClearingTurnOutput, FlightFrame


class RunLogger:
    def __init__(self, directory: str | Path = "clearing_turn_logs"):
        self.directory = Path(directory)
        self.run_id: Optional[str] = None
        self.event_path: Optional[Path] = None
        self.telemetry_path: Optional[Path] = None
        self.summary_path: Optional[Path] = None
        self._csv_file = None
        self._csv_writer = None

    def start(self, run_id: str) -> None:
        self.close()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.run_id = run_id
        self.event_path = self.directory / f"{run_id}_events.jsonl"
        self.telemetry_path = self.directory / f"{run_id}_telemetry.csv"
        self.summary_path = self.directory / f"{run_id}_summary.json"
        self._csv_file = self.telemetry_path.open("w", newline="", encoding="utf-8")
        fields = [
            "timestamp", "state", "heading", "heading_error", "bank", "roll_rate",
            "desired_bank", "roll_command", "ias", "vertical_speed", "pilot_roll_input",
        ]
        self._csv_writer = csv.DictWriter(self._csv_file, fieldnames=fields)
        self._csv_writer.writeheader()

    def event(self, name: str, **values: Any) -> None:
        if not self.event_path:
            return
        record = {"run_id": self.run_id, "event": name, **values}
        with self.event_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    def telemetry(self, frame: FlightFrame, output: ClearingTurnOutput) -> None:
        if not self._csv_writer:
            return
        self._csv_writer.writerow({
            "timestamp": frame.timestamp,
            "state": output.state,
            "heading": frame.heading_deg,
            "heading_error": output.heading_error_deg,
            "bank": frame.bank_deg,
            "roll_rate": frame.roll_rate_deg_s,
            "desired_bank": output.desired_bank_deg,
            "roll_command": output.roll_command,
            "ias": frame.ias_kts,
            "vertical_speed": frame.vertical_speed_fpm,
            "pilot_roll_input": frame.pilot_roll_input,
        })
        self._csv_file.flush()

    def summary(self, values: Dict[str, Any]) -> None:
        if self.summary_path:
            self.summary_path.write_text(json.dumps(values, indent=2, ensure_ascii=False), encoding="utf-8")

    def close(self) -> None:
        if self._csv_file:
            self._csv_file.close()
        self._csv_file = None
        self._csv_writer = None


class NullRunLogger(RunLogger):
    def __init__(self):
        super().__init__()

    def start(self, run_id: str) -> None:
        self.run_id = run_id

    def event(self, name: str, **values: Any) -> None:
        pass

    def telemetry(self, frame: FlightFrame, output: ClearingTurnOutput) -> None:
        pass

    def summary(self, values: Dict[str, Any]) -> None:
        pass

    def close(self) -> None:
        pass
