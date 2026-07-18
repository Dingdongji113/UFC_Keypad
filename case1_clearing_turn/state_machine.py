"""Explicit transition graph for the clearing-turn lifecycle."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from .models import ClearingTurnState


ALLOWED_TRANSITIONS = {
    ClearingTurnState.IDLE: {ClearingTurnState.ARMED, ClearingTurnState.FAULTED},
    ClearingTurnState.ARMED: {ClearingTurnState.WAIT_LAUNCH, ClearingTurnState.ABORTED, ClearingTurnState.FAULTED},
    ClearingTurnState.WAIT_LAUNCH: {ClearingTurnState.WAIT_SAFE, ClearingTurnState.ABORTED, ClearingTurnState.FAULTED},
    ClearingTurnState.WAIT_SAFE: {ClearingTurnState.FIRST_TURN, ClearingTurnState.EXITING, ClearingTurnState.ABORTED, ClearingTurnState.FAULTED},
    ClearingTurnState.FIRST_TURN: {ClearingTurnState.REVERSING, ClearingTurnState.EXITING},
    ClearingTurnState.REVERSING: {ClearingTurnState.BRC_CAPTURE, ClearingTurnState.EXITING},
    ClearingTurnState.BRC_CAPTURE: {ClearingTurnState.EXITING},
    ClearingTurnState.EXITING: {ClearingTurnState.COMPLETED, ClearingTurnState.ABORTED, ClearingTurnState.FAULTED},
    ClearingTurnState.COMPLETED: {ClearingTurnState.IDLE},
    ClearingTurnState.ABORTED: {ClearingTurnState.IDLE},
    ClearingTurnState.FAULTED: {ClearingTurnState.IDLE},
}


@dataclass
class StateMachine:
    state: ClearingTurnState = ClearingTurnState.IDLE
    entered_at: float = 0.0
    on_transition: Optional[Callable[[ClearingTurnState, ClearingTurnState, float], None]] = None

    def transition(self, new_state: ClearingTurnState, timestamp: float) -> None:
        old_state = self.state
        if new_state not in ALLOWED_TRANSITIONS.get(old_state, set()):
            raise RuntimeError(f"invalid state transition: {old_state.value} -> {new_state.value}")
        self.state = new_state
        self.entered_at = timestamp
        if self.on_transition:
            self.on_transition(old_state, new_state, timestamp)

    def elapsed(self, timestamp: float) -> float:
        return max(0.0, timestamp - self.entered_at)
