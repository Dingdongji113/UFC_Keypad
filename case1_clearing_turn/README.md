# Case I Clearing Turn (standalone)

This package implements the isolated F/A-18C Case I clearing-turn module. It
does **not** import DCS, modify `Export.lua`, connect to the UFC UI, or send a
real flight-control command. `roll_command` is an advisory value consumed only
by tests, logs, or the bundled simulator.

## State flow

`IDLE -> ARMED -> WAIT_LAUNCH -> WAIT_SAFE -> FIRST_TURN -> REVERSING -> BRC_CAPTURE -> EXITING -> COMPLETED`

Pilot takeover and safety exits terminate at `ABORTED`; invalid numeric data or
internal controller errors terminate at `FAULTED`. Control release is ramped,
confirmed, and only then emits the matching one-shot exit audio event.

CAT 1/2 first turn right by 20 degrees; CAT 3/4 first turn left by 20 degrees.
The first target is always based on `launch_heading_deg`, never on BRC.

## Run

From the repository root:

```bash
python -m case1_clearing_turn.simulator --cat 2 --launch-heading 63 --brc 63 --scenario normal
```

Available scenarios: `normal`, `pilot_takeover`, `negative_climb`,
`excessive_bank`, `navigation_failure`, `stale_input`, and `audio_failure`.
Each run writes event JSONL, telemetry CSV, and a final JSON summary under
`clearing_turn_logs/` (or `--log-dir`).

Use custom thresholds without editing code:

```bash
python -m case1_clearing_turn.simulator --cat 3 --launch-heading 10 --brc 10 --scenario normal --config case1_clearing_turn/default_config.json
```

## Test

```bash
python -m unittest discover -s case1_clearing_turn/tests -v
```

## Future integration seams

`interfaces.py` defines providers for trim completion, trim-check result, and
flight frames, plus null/logging/simulator roll sinks and an audio notifier.
A future adapter may connect those seams after the existing trim workflow, but
this package intentionally provides no DCS or UFC adapter.

`ModuleConfig.from_json()` loads both controller thresholds and configured
audio paths. Pass `AudioConfig.event_paths()` to `FileAudioNotifier` for local
WAV playback; simulator/test mode continues to use `MockAudioNotifier`.
