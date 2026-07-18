# Audio placeholders

The default configuration names the five WAV assets expected by
`FileAudioNotifier`. They are intentionally not bundled with this source-only
module. Test and simulator runs use `MockAudioNotifier`, so no sound device or
audio file is required.

To enable local playback, add WAV files with the configured names or supply a
different event-to-path mapping. Missing or unplayable files are logged and
reported as `audio_failed`; they never change the flight-control state.
