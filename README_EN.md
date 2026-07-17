# UFC Keypad

[English](README_EN.md) | [简体中文](README.md)

A PyQt6 touch-panel implementation of the **F/A-18C Hornet Up Front Controller** for DCS World. It communicates with DCS through **DCS-BIOS** and includes optional Export.lua support for functions that are not available through normal DCS-BIOS telemetry.

## Features

- **LOCAL ICP** — full UFC layout with touch/click input and live cockpit display data.
- **MORSE LIGHT** — enter text and transmit Morse code through the formation lights.
- **LIGHT CONTROL** — landing/taxi, formation, position and strobe light controls with presets.
- **SYSTEM 4** — two touch pages for HUD/NAV and EW/JETT controls, including large HDG/CRS controls, live feedback, spring-loaded switches, hold actions and guarded jettison controls.
- **SYSTEM SELECT** — touch-scroll navigation with a fixed BACK header and reserved future slots.
- **Cold-start assistant** — LAND and CV startup profiles with guarded automation, manual confirmation points and carrier launch trim support.
- **Selectable startup animation** — UFC BIT or a fictional millennium-era Japanese anime terminal style.
- **English and Simplified Chinese interface** — choose System, English or 简体中文 in the settings window. Changes apply immediately and are saved.
- Native Windows touch isolation for secondary touch displays.
- PyInstaller single-file build support.

## Requirements

- Windows
- Python 3.10 or newer
- PyQt6
- DCS World with DCS-BIOS

Install dependencies and run:

```bash
pip install -r requirements.txt
python main.py
```

Safe mode disables the native hooks, startup overlay and live DCS-BIOS receiver:

```bash
python main_safe.py
```

## Interface language

The settings window contains an **Interface language** selector:

- `System` — Simplified Chinese on a Chinese system locale; English otherwise.
- `English`
- `Simplified Chinese`

The selection is stored in `ufc_config.json`:

```json
{
  "language": "en_US"
}
```

Accepted values are `system`, `en_US` and `zh_CN`. Avionics labels, DCS control identifiers and checklist terminology remain in their established English form in every interface language.

## DCS-BIOS network ports

| Direction | Address | Purpose |
|---|---|---|
| DCS → UFC Keypad | `239.255.50.10:5010/UDP` | DCS-BIOS multicast cockpit state |
| UFC Keypad → DCS | `127.0.0.1:7778/UDP` | DCS-BIOS control commands |

The source of truth is `ufc/dcs_bios.py`.

## Export.lua bridge

Some ejection-seat, ECM and carrier-launch trim functions use the optional bridge in `dcs_export/UFC_Keypad_CVTrim.lua`.

Install or update it with:

```bash
python install_dcs_export_bridge.py
```

After restarting DCS and entering an F/A-18C cockpit, close the main UFC program and run:

```bash
python probe_hornet_bridge.py
```

The probe writes timestamped Markdown and JSON reports. DCS-side bridge logs are stored under:

```text
Saved Games\DCS*\Logs\UFC_Keypad_CVTrim.log
```

## Cold-start assistant

The current flow provides separate LAND and CV profiles. It includes engine-RPM gating, APU and engine sequencing, display and lighting setup, canopy/OBOGS, bleed-air cycle, control checks, FCS/RWR, RADAR/INS, SAI, RADALT, BINGO fuel and HMD/IFA steps.

The CV profile also contains automatic longitudinal catapult trim. Its controller uses fast travel, fine adjustment, fresh-telemetry gating and consecutive in-tolerance verification. Standalone weight-trim and asymmetric-store calculation modules are available for future reuse, but automatic asymmetric lateral trim is not enabled.

## Startup animation

The settings window offers:

| Value | Display name |
|---|---|
| `ufc_bit` | UFC BIT (military self-test) |
| `anime_millennium_jp` | Millennium-era Japanese anime |

The selection is saved as `startup_style` in `ufc_config.json`.

## Verification

Run the available dependency-light checks:

```bash
python verify_i18n.py
python verify_trim_models.py
python _verify.py
```

`_verify.py` requires PyQt6 and exercises the application modules in an off-screen Qt environment.

## Packaging

```bash
pyinstaller UFC_Keypad_v5.spec
```

The spec includes the UFC package, font, configuration template and Export.lua bridge.

## Main modules

| Module | Responsibility |
|---|---|
| `ufc/ui.py` | Main UFC panel and settings window |
| `ufc/i18n.py` | English/Chinese translations and language selection |
| `ufc/i18n_ui.py` | Live settings-window retranslation |
| `ufc/startup.py` | Startup animation overlays |
| `ufc/startup_i18n.py` | Startup-setting localization adapter |
| `ufc/dcs_bios.py` | DCS-BIOS parsing, receiver and command sender |
| `ufc/input.py` | Native touch hooks and Windows input injection |
| `ufc/system4.py` | SYSTEM 4 pages and live feedback integration |
| `ufc/system4_mapping.py` | SYSTEM 4 control and feedback mapping |
| `ufc/system4_widgets.py` | Native-touch switches, knobs and buttons |
| `ufc/cold_start.py` | Cold-start state machine |
| `ufc/cv_trim_auto.py` | CV trim telemetry and command bridge |
| `ufc/cv_trim_two_stage.py` | Fast/fine longitudinal trim controller |
| `ufc/weight_trim.py` | Reusable weight-based launch trim calculation |
| `ufc/asymmetric_launch_trim.py` | Standalone asymmetric-store moment calculation |

## Safety note

This is a simulator utility. It is not approved flight software and must not be used for real-world aircraft operation or flight planning.
