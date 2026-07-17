"""Integration seams. No real DCS implementation belongs in this package."""

from __future__ import annotations

import logging
from typing import Protocol

from .models import FlightFrame


class AutoTrimProvider(Protocol):
    def is_complete(self) -> bool: ...


class TrimCheckProvider(Protocol):
    def passed(self) -> bool: ...


class FlightDataProvider(Protocol):
    def read_frame(self) -> FlightFrame: ...


class RollControlSink(Protocol):
    def set_roll_command(self, value: float) -> None: ...
    def release(self) -> None: ...


class AudioNotifier(Protocol):
    def emit(self, event: str) -> bool: ...


class NullRollControlSink:
    def set_roll_command(self, value: float) -> None:
        del value

    def release(self) -> None:
        pass


class LoggingRollControlSink:
    def __init__(self, logger: logging.Logger | None = None):
        self.logger = logger or logging.getLogger(__name__)

    def set_roll_command(self, value: float) -> None:
        self.logger.info("suggested roll command %.4f", value)

    def release(self) -> None:
        self.logger.info("suggested roll control released")


class SimulatorRollControlSink:
    def __init__(self):
        self.value = 0.0
        self.released = True

    def set_roll_command(self, value: float) -> None:
        self.value = max(-1.0, min(1.0, float(value)))
        self.released = False

    def release(self) -> None:
        self.value = 0.0
        self.released = True
