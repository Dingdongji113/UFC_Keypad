"""Standalone F/A-18C Case I clearing-turn controller.

This package deliberately has no dependency on DCS, PyQt, or the UFC UI.
"""

from .config import AudioConfig, ClearingTurnConfig, ModuleConfig
from .controller import ClearingTurnController
from .models import (
    AudioEvent,
    ClearingTurnOutput,
    ClearingTurnStartRequest,
    ClearingTurnState,
    ExitReason,
    FlightFrame,
)

__all__ = [
    "AudioEvent",
    "AudioConfig",
    "ClearingTurnConfig",
    "ClearingTurnController",
    "ClearingTurnOutput",
    "ClearingTurnStartRequest",
    "ClearingTurnState",
    "ExitReason",
    "FlightFrame",
    "ModuleConfig",
]
