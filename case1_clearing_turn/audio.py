"""Audio-event arbitration and pluggable notifier implementations."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Iterable, List

from .interfaces import AudioNotifier
from .models import AudioEvent


PRIORITY = {
    AudioEvent.CLEARING_TURN_COMPLETE: 1,
    AudioEvent.PILOT_CONTROL: 2,
    AudioEvent.AUTO_TURN_ABORT: 3,
    AudioEvent.AUTO_CONTROL_FAULT: 4,
}


class LoggingAudioNotifier:
    def __init__(self, logger: logging.Logger | None = None):
        self.logger = logger or logging.getLogger(__name__)

    def emit(self, event: str) -> bool:
        self.logger.info("audio event: %s", event)
        return True


class MockAudioNotifier:
    def __init__(self, fail: bool = False):
        self.events: List[str] = []
        self.fail = fail

    def emit(self, event: str) -> bool:
        self.events.append(event)
        return not self.fail


class FileAudioNotifier:
    """Play configured WAV files on Windows; fail safely everywhere else."""

    def __init__(self, paths: Dict[str, str], logger: logging.Logger | None = None):
        self.paths = dict(paths)
        self.logger = logger or logging.getLogger(__name__)

    def emit(self, event: str) -> bool:
        path = Path(self.paths.get(event, ""))
        if not path.is_file():
            self.logger.error("audio file missing for %s: %s", event, path)
            return False
        try:
            import winsound
            winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)
            return True
        except Exception:
            self.logger.exception("audio playback failed for %s", event)
            return False


class AudioManager:
    def __init__(self, notifier: AudioNotifier):
        self.notifier = notifier
        self.played: set[str] = set()
        self.last_failed = False

    def reset(self) -> None:
        self.played.clear()
        self.last_failed = False

    def emit_once(self, candidates: Iterable[AudioEvent]) -> str | None:
        choices = [event for event in candidates if event.value not in self.played]
        if not choices:
            return None
        event = max(choices, key=lambda item: PRIORITY.get(item, 0))
        self.played.add(event.value)
        try:
            self.last_failed = not bool(self.notifier.emit(event.value))
        except Exception:
            logging.getLogger(__name__).exception("audio notifier raised")
            self.last_failed = True
        return event.value
