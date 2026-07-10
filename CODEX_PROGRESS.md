# Codex progress (2026-07-10)

## Completed

- `probe_hornet_bridge.py` now always writes timestamped Markdown and JSON reports, including the no-telemetry and interrupted paths.
- Every cockpit command records its payload, before/after telemetry, `last_command` acknowledgement, watched-field changes, and changes found by the full draw-argument scan.
- `dcs_export/UFC_Keypad_CVTrim.lua` now accepts `{"type":"scan_args","from":0,"to":800}` and returns a `scan_args` JSON object in telemetry.
- Scan input is limited to `0..2000` and at most 1001 arguments per request.
- README usage and `_verify.py` compile coverage were updated.
- Live cockpit probing corrected ejection-seat ARMED to `0.0` and ECM REC to `0.3`; both were verified against cockpit arguments 511 and 248.
- Telemetry now reads cockpit arguments from device 0 instead of external-aircraft draw arguments.
- Live introspection found `ExternalFM:HumanInfo:mass_lb` for gross weight and `ExternalFM:HumanInfo:Lstab` for stabilator/trim feedback.
- Pitch trim now uses the local FA-18C HOTAS device 13 commands 3014/3015; a one-second pulse changed Lstab by about two degrees and the opposite pulse restored it.
- Corrected APU ON from invalid DCS-BIOS state 3 to state 1 and added direct device 12/command 3001 fallback; live argument 375 changed from 0 to 1.
- A three-second hold on cockpit command 3001 was proven ineffective. The live-verified fix uses device 12 command 3023 (`APU_ControlSw_TM_WARTHOG`): value 1 latched argument 375 at 1.0 and value 0 released it.
- Corrected ALR-67 POWER as a latching control: it is now set to 1 without an immediate release, with direct device 53/command 3001 fallback; live argument 277 latched at 1 and power light 276 illuminated.
- Step 14 now closes the canopy and enables OBOGS.
- The former combined RADAR/INS/PB19 step is now split into two confirmed steps: step 21 sets RADAR OPR plus LAND/CV INS and waits for START; step 22 presses/releases AMPCD PB19 and waits for START again. The fixed ten-second delay between them was removed.
- HMD calibration/INS IFA is now LAND step 23 and CV step 24, using DAY/NIGHT-dependent HMD brightness.
- Step 12 now combines APU OFF with FLAPS HALF.
- HMD setup sets INS IFA, waits ten seconds, then presses RDDI OSB18, OSB18, OSB3, and OSB20 strictly in order with three seconds between completed presses.
- Each HMD RDDI OSB uses one 200 ms DCS-BIOS press/release. Export bridge is fallback-only and is never sent simultaneously, preventing accidental double presses.

## Local findings

- The active DCS profile is `Saved Games\DCS` (not `DCS.openbeta`).
- `Export.lua` already loads `Scripts\UFC_Keypad_CVTrim.lua`.
- The existing DCS log proves the old bridge loaded and received the ejection-seat and ECM clickable commands.
- The installed bridge is older than the source in this handoff and must be replaced before the next probe.
- DCS was not running during this work, so cockpit acceptance could not be performed.

## Verification performed

- Python compilation passes for the changed probe, installer, and verification script.
- The probe's no-telemetry path returns exit code 2 and still writes valid Markdown/JSON reports.
- A synthetic before/after test confirms command acknowledgement and draw-argument changes are serialized into both report formats.
- A project virtual environment was created with PyQt6 and the full `_verify.py` suite now passes all checks.
- Live CV trim acceptance at approximately 36,685 lb reached 15.816 degrees for a 16.0-degree target after 16 pulses (0.184-degree error).

## Required live-DCS step

1. Run `python install_dcs_export_bridge.py` from this project to update the installed bridge.
2. Fully restart DCS and enter an F/A-18C cockpit.
3. Stop the main UFC app so it does not own UDP 5518.
4. Run `python probe_hornet_bridge.py` (or add `--yes` for no prompts).
5. Return both generated `probe_report_*.md` and `probe_report_*.json` files.

The resulting evidence is required before changing the hard-coded ejection-seat, ECM, or trim command values.
