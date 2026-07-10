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
- Step 15 now closes the canopy and enables OBOGS.
- The former combined RADAR/INS/PB19 step is now split into two confirmed steps: step 20 sets RADAR OPR plus LAND/CV INS and waits for START; step 21 presses/releases AMPCD PB19 and waits for START again. The fixed ten-second delay between them was removed.
- HMD calibration/INS IFA is now LAND step 26 and CV step 27, using DAY/NIGHT-dependent HMD brightness.
- Step 13 combines APU OFF with FLAPS AUTO using DCS-BIOS state 0 and local input value 1.0.
- New step 12 runs after both engines are stable. DAY sets STROBE BRIGHT only; NIGHT additionally sets LDG/TAXI ON, formation/position and core interior dimmers to 70%, and cockpit mode NITE. It asks for FLOOD and CHART choices with matching UFC touch controls. The exterior master switch is untouched; anti-skid is ON for LAND and OFF for CV.
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

## Superseded Step 19 closed-loop automation

This section records the earlier implementation and is retained only as test
history. The direct-touch implementation below replaces its targets and loops.

- Added `ufc/manual_setup_auto.py` with guarded SAI, RADALT, and BINGO stages.
- Confirmed local mappings: SAI device 32/command 3002/arguments 213 and 209;
  RADALT device 30/command 3002/arguments 291 and 287; IFEI UP/DOWN device 33,
  commands 3003/3004, with `IFEI_BINGO` string feedback.
- Live probing confirmed a BINGO press changes the displayed target by 100 lb.
- Live probing confirmed RADALT is a relative rotary and `+1000`/`-1000`
  DCS-BIOS values provide approximately ten-foot closed-loop resolution.
- Added configurable LAND 200 ft / 3000 lb and CV 200 ft / 4000 lb defaults.
- Extended DCS-BIOS parsing and bridge telemetry with stable feedback fields.
  Failures enter `wait_user` with per-stage status.
- Live LAND acceptance completed in the running aircraft: SAI was already
  unlocked and correctly skipped; RADALT moved from about 447 ft to 208 ft in
  50 fine pulses; BINGO moved from 100 lb to exactly 3000 lb in 29 presses.
  Every primary action produced feedback, so the bridge was not invoked.

## Follow-up: direct touch setup and PB19 single press

- Split former step 19 into `SAI UNLOCK`, `RADALT MIN`, and `BINGO FUEL`, each
  with its own user confirmation.
- Added large on-screen touch −/+ controls. They directly operate the cockpit:
  one pulse per tap, repeat after 250 ms and then about every 100 ms while held.
- Removed local target values and closed-loop regulation. RADALT/BINGO centers
  are read-only real telemetry, and START only stops repeat and advances.
- Primary DCS-BIOS and bridge fallback are mutually exclusive per pulse; the
  bridge is used only if sending through DCS-BIOS fails.
- SAI now uses local input command `SAI_Rotate_EXT`: device 32, command 3005,
  CCW value -0.3, through the bridge `SetCommand` path. It does not use the
  normal SAI pitch-adjust rotary.
- AMPCD PB19 now contains exactly one DCS-BIOS press/release pair. The former
  unconditional bridge copy was removed to eliminate the observed double tap.

## Live direct-control acceptance

- Installed bridge SHA-256 matches the repository source and DCS logged a fresh
  bridge load.
- Live DCS-BIOS state showed FLAPS HALF (`1`) before the test; sending the new
  AUTO state (`0`) moved it to AUTO and it remained there.
- Live BINGO increment changed the IFEI value from 0 to 100 lb; decrement
  restored it to 0 lb, confirming right-increase and left-decrease mapping.
- Live RADALT `+1311` increased the pointer and `-1311` decreased it; the final
  decrement restored one step after the increment. No bridge duplicate was sent.
- Live bridge logging confirmed SAI `SetCommand` device 32/command 3005 at
  `-0.3`, followed by its timed release to `0` after 300 ms.

## Post-engine lighting and anti-skid

- Added `LIGHTS / ANTI-SKID` immediately after both engines are stable. LAND now
  has 27 steps and CV has 28.
- DAY sends only STROBE BRIGHT plus the profile anti-skid state, so it does not
  switch on any interior lights. NIGHT sets LDG/TAXI ON, STROBE BRIGHT,
  formation/position and console/instrument/warn-caution brightness to 70%, and
  cockpit light mode to NITE.
- NIGHT asks FLOOD and CHART independently with matching UFC-style NO/YES touch
  controls. Enabled is 70%; disabled is 0. START cannot bypass either prompt.
- The command list never contains an exterior master-light command. LAND sends
  anti-skid ON and CV sends anti-skid OFF.
- Live DCS acceptance applied the complete NIGHT/LAND sequence: every requested
  switch state matched, and 45875 input values reported as 45874 due to cockpit
  analog quantization (effectively 70%). The original cockpit lighting state was
  restored exactly after the test.
