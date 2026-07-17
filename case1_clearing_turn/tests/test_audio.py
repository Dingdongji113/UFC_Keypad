import unittest
from pathlib import Path

from case1_clearing_turn.audio import AudioManager, FileAudioNotifier, MockAudioNotifier
from case1_clearing_turn.config import ModuleConfig
from case1_clearing_turn.models import AudioEvent


class AudioTests(unittest.TestCase):
    def test_priority_and_once(self):
        notifier = MockAudioNotifier()
        manager = AudioManager(notifier)
        emitted = manager.emit_once([
            AudioEvent.CLEARING_TURN_COMPLETE, AudioEvent.AUTO_CONTROL_FAULT,
            AudioEvent.PILOT_CONTROL,
        ])
        self.assertEqual(emitted, AudioEvent.AUTO_CONTROL_FAULT.value)
        self.assertIsNone(manager.emit_once([AudioEvent.AUTO_CONTROL_FAULT]))
        self.assertEqual(notifier.events, [AudioEvent.AUTO_CONTROL_FAULT.value])

    def test_missing_file_fails_without_raising(self):
        notifier = FileAudioNotifier({AudioEvent.AUTO_TURN_ACTIVE.value: "missing.wav"})
        self.assertFalse(notifier.emit(AudioEvent.AUTO_TURN_ACTIVE.value))

    def test_notifier_failure_is_recorded(self):
        manager = AudioManager(MockAudioNotifier(fail=True))
        self.assertEqual(manager.emit_once([AudioEvent.AUTO_TURN_ACTIVE]), "AUTO_TURN_ACTIVE")
        self.assertTrue(manager.last_failed)

    def test_audio_paths_load_from_module_config(self):
        config_path = Path(__file__).parents[1] / "default_config.json"
        config = ModuleConfig.from_json(config_path)
        self.assertEqual(
            config.audio.event_paths()["PILOT_CONTROL"],
            "case1_clearing_turn/audio/pilot_control.wav",
        )


if __name__ == "__main__":
    unittest.main()
