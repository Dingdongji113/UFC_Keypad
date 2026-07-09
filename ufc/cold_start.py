# -*- coding: utf-8 -*-
"""F/A-18C cold-start sequencer UI patch.

This module intentionally lives outside ``ufc.ui``.  The main window is already
large and historically fragile, so the sequencer is installed by monkey-patching
``UFCKeypadWindow`` before the window instance is created.

Implementation scope:
- Adds a SYSTEMS option "4  COLD START".
- Adds a low-brightness cold-start sequencer page.
- Implements an ASSIST-style sequence:
  battery/APU/right engine/left engine/APU off/supervised system prep/display
  mode/display brightness/UFC ready/INS mode/complete.
- Does not run BIT/self-test and does not touch external lights.
- Requires user confirmation for APU ready and throttle-idle/engine-stable
  points.
- After both engines are stable and APU is off, the program performs supervised
  steps for canopy, bleed-air cycle, trim reset, FCS reset, and ECM receive.
- IFF is deliberately a manual reminder; the program does not auto-operate it.
- Applies DAY/NIGHT display brightness presets to LDDI/RDDI/AMPCD/HUD through
  config-driven DCS-BIOS controls.

DCS-BIOS control identifiers are configurable through ``ufc_config.json``.  The
built-in defaults target DCS-Skunkworks DCS-BIOS FA-18C_hornet.lua identifiers.
Timed sequences are executed with QTimer so long actions, such as canopy close,
do not freeze the touch panel UI.
"""
from __future__ import annotations

import time
from typing import Any, Callable, Dict, List

from PyQt6.QtCore import Qt, QTimer

from ufc.config import load_config, save_config
from ufc.dcs_bios import send_dcs_bios


PAGE = "cold_start"

# Click positions reserved for the cold-start page.  They intentionally do not
# overlap existing UFC_BIOS_MAP entries, so UFCCell will not emit aircraft UFC
# commands before the page handler sees them.
P_START = (300, 0)
P_PAUSE = (300, 1)
P_ABORT = (300, 2)
P_SKIP = (300, 3)
P_DAY = (300, 4)
P_NIGHT = (300, 5)
P_PROFILE = (300, 6)

DEFAULT_DISPLAY_PRESETS = {
    "day": {
        "lddi": 80,
        "rddi": 80,
        "ampcd": 80,
        "hud": 70,
    },
    "night": {
        "lddi": 25,
        "rddi": 25,
        "ampcd": 20,
        "hud": 25,
    },
}

# A control may be either:
#   {"id": "CONTROL", "value": 1}
# or a timed sequence:
#   {"sequence": [{"id": "CONTROL", "value": "INC", "repeat": 3, "delay_ms": 80}]}
DEFAULT_CONTROLS = {
    "battery_on": {"id": "BATTERY_SW", "value": 0},
    "apu_start": {"id": "APU_CONTROL_SW", "value": 1},
    "right_engine_crank": {"id": "ENGINE_CRANK_SW", "value": 2},
    "left_engine_crank": {"id": "ENGINE_CRANK_SW", "value": 0},
    "apu_off": {"id": "APU_CONTROL_SW", "value": 0},
    "canopy_close": {
        "sequence": [
            {"id": "CANOPY_SW", "value": 2, "delay_ms": 6000},
            {"id": "CANOPY_SW", "value": 1, "delay_ms": 80},
        ]
    },
    "bleed_air_cycle": {
        "sequence": [
            {"id": "BLEED_AIR_PULL", "value": 1, "delay_ms": 150},
            {"id": "BLEED_AIR_KNOB", "value": 0, "delay_ms": 120},
            {"id": "BLEED_AIR_KNOB", "value": 1, "delay_ms": 120},
            {"id": "BLEED_AIR_KNOB", "value": 2, "delay_ms": 120},
            {"id": "BLEED_AIR_KNOB", "value": 3, "delay_ms": 120},
            {"id": "BLEED_AIR_KNOB", "value": 1, "delay_ms": 120},
        ]
    },
    "trim_reset": {
        "sequence": [
            {"id": "TO_TRIM_BTN", "value": 1, "delay_ms": 80},
            {"id": "TO_TRIM_BTN", "value": 0, "delay_ms": 80},
        ]
    },
    "fcs_reset": {
        "sequence": [
            {"id": "FCS_RESET_BTN", "value": 1, "delay_ms": 80},
            {"id": "FCS_RESET_BTN", "value": 0, "delay_ms": 80},
        ]
    },
    "ecm_receive": {"id": "ECM_MODE_SW", "value": 1},
    "ins_land": {"id": "INS_SW", "value": 2},
    "ins_carrier": {"id": "INS_SW", "value": 1},
    "display_lddi_select": {"id": "LEFT_DDI_BRT_SELECT", "day_value": 2, "night_value": 1},
    "display_rddi_select": {"id": "RIGHT_DDI_BRT_SELECT", "day_value": 2, "night_value": 1},
    "display_ampcd_select": {"id": "", "day_value": 1, "night_value": 0},
    "display_hud_select": {"id": "", "day_value": 1, "night_value": 0},
    "display_lddi": {"id": "LEFT_DDI_BRT_CTL", "value_type": "analog"},
    "display_rddi": {"id": "RIGHT_DDI_BRT_CTL", "value_type": "analog"},
    "display_ampcd": {"id": "AMPCD_BRT_CTL", "value_type": "analog"},
    "display_hud": {"id": "HUD_SYM_BRT", "value_type": "analog"},
}


def _pct_to_bios(percent: int) -> int:
    percent = max(0, min(100, int(percent)))
    return round(percent / 100 * 65535)


def _merged_config() -> Dict[str, Any]:
    cfg = load_config()
    controls = {key: value.copy() for key, value in DEFAULT_CONTROLS.items()}
    for key, value in (cfg.get("cold_start_controls", {}) or {}).items():
        if isinstance(value, dict):
            merged = controls.get(key, {}).copy()
            merged.update(value)
            controls[key] = merged
        else:
            controls[key] = value

    presets = {
        "day": DEFAULT_DISPLAY_PRESETS["day"].copy(),
        "night": DEFAULT_DISPLAY_PRESETS["night"].copy(),
    }
    user_presets = cfg.get("display_brightness_presets", {}) or {}
    for mode in ("day", "night"):
        if isinstance(user_presets.get(mode), dict):
            presets[mode].update(user_presets[mode])

    cfg.setdefault("cold_start_mode", "assist")
    cfg.setdefault("cold_start_profile", "land")
    cfg.setdefault("cold_start_display_mode", "day")
    cfg["cold_start_controls"] = controls
    cfg["display_brightness_presets"] = presets
    return cfg


def patch_cold_start(UFCKeypadWindowClass):
    """Install cold-start page and state machine onto ``UFCKeypadWindow``."""
    if getattr(UFCKeypadWindowClass, "_cold_start_patch_installed", False):
        return
    UFCKeypadWindowClass._cold_start_patch_installed = True

    orig_init_ui = UFCKeypadWindowClass.init_ui
    orig_on_cell_click = UFCKeypadWindowClass.on_cell_click

    def init_ui(self):
        orig_init_ui(self)
        self._cold_start_setup_state()
        self._init_cold_start_page()
        # Original init_ui ends on local_icp before this page exists.  Re-apply
        # visibility so the new cold-start widgets start hidden.
        self._show_page(self._current_page)

    def on_cell_click(self, pos):
        # SYSTEM SELECT option 4 -> COLD START
        if getattr(self, "_current_page", None) == "select" and pos == (201, 3):
            self._show_page(PAGE)
            self._cold_refresh_ui()
            return

        if getattr(self, "_current_page", None) == PAGE:
            self._cold_handle_click(pos)
            return

        orig_on_cell_click(self, pos)

    UFCKeypadWindowClass.init_ui = init_ui
    UFCKeypadWindowClass.on_cell_click = on_cell_click

    # Attach methods.  We keep them as standalone functions to avoid touching
    # ufc.ui directly.
    UFCKeypadWindowClass._cold_start_setup_state = _cold_start_setup_state
    UFCKeypadWindowClass._init_cold_start_page = _init_cold_start_page
    UFCKeypadWindowClass._cold_handle_click = _cold_handle_click
    UFCKeypadWindowClass._cold_arm_or_continue = _cold_arm_or_continue
    UFCKeypadWindowClass._cold_run_next_step = _cold_run_next_step
    UFCKeypadWindowClass._cold_enter_hold = _cold_enter_hold
    UFCKeypadWindowClass._cold_abort = _cold_abort
    UFCKeypadWindowClass._cold_pause = _cold_pause
    UFCKeypadWindowClass._cold_skip = _cold_skip
    UFCKeypadWindowClass._cold_set_display_mode = _cold_set_display_mode
    UFCKeypadWindowClass._cold_set_profile = _cold_set_profile
    UFCKeypadWindowClass._cold_send_configured = _cold_send_configured
    UFCKeypadWindowClass._cold_send_configured_async = _cold_send_configured_async
    UFCKeypadWindowClass._cold_run_sequence_entries = _cold_run_sequence_entries
    UFCKeypadWindowClass._cold_apply_display_brightness = _cold_apply_display_brightness
    UFCKeypadWindowClass._cold_unlock_local_icp = _cold_unlock_local_icp
    UFCKeypadWindowClass._cold_status_lines = _cold_status_lines
    UFCKeypadWindowClass._cold_refresh_ui = _cold_refresh_ui
    UFCKeypadWindowClass._cold_set_cell = _cold_set_cell
    UFCKeypadWindowClass._cold_log = _cold_log


def _cold_start_setup_state(self):
    cfg = _merged_config()
    self._cold_state = "idle"
    self._cold_step_index = -1
    self._cold_hold_reason = ""
    self._cold_display_mode = str(cfg.get("cold_start_display_mode", "day")).lower()
    if self._cold_display_mode not in ("day", "night"):
        self._cold_display_mode = "day"
    self._cold_profile = str(cfg.get("cold_start_profile", "land")).lower()
    if self._cold_profile not in ("land", "carrier"):
        self._cold_profile = "land"
    self._cold_right_engine_online = False
    self._cold_left_engine_online = False
    self._cold_apu_off = False
    self._cold_display_brightness_applied = False
    self._cold_normal_ufc_locked = True
    self._cold_sequence_token = 0
    self._cold_cells = {}
    self._cold_status_cells = {}
    self._cold_last_action = "READY"
    self._cold_total_steps = 20


def _init_cold_start_page(self):
    # Top row
    self.place_cell("I/P", (0, 0), 8, 7, 140, 90, font_size=20,
                    register=False, no_feedback=True, page=PAGE)
    self.place_cell("SYSTEMS", (1, 0), 164, 7, 140, 90, font_size=20,
                    register=False, no_feedback=True, page=PAGE)
    title = self.place_cell("COLD START\nSEQUENCER", None, 316, 7, 700, 90,
                            font_size=26, is_variable=True, register=False,
                            no_feedback=True, page=PAGE)
    self._cold_status_cells["title"] = title

    # Four status rows
    rows = [
        ("state", 114, 90),
        ("engines", 221, 90),
        ("action", 328, 90),
        ("mode", 435, 90),
    ]
    for key, y, h in rows:
        c = self.place_cell("", None, 8, y, 1008, h, font_size=22,
                            is_variable=True, register=False, no_feedback=True,
                            page=PAGE, var_align=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._cold_status_cells[key] = c

    # Bottom controls
    y5, h5 = 542, 50
    buttons = [
        ("START", P_START, 8, 140),
        ("PAUSE", P_PAUSE, 156, 140),
        ("ABORT", P_ABORT, 304, 140),
        ("SKIP", P_SKIP, 452, 120),
        ("DAY", P_DAY, 580, 110),
        ("NIGHT", P_NIGHT, 698, 130),
        ("LAND/CV", P_PROFILE, 836, 180),
    ]
    for text, pos, x, w in buttons:
        cell = self.place_cell(text, pos, x, y5, w, h5, font_size=13,
                               register=False, page=PAGE, bold=True)
        self._cold_cells[pos] = cell

    self._cold_refresh_ui()


def _cold_handle_click(self, pos):
    if pos == (1, 0):
        self._show_page("select")
        return
    if pos == (0, 0):
        self._show_page("local_icp")
        return
    if pos == P_START:
        self._cold_arm_or_continue()
    elif pos == P_PAUSE:
        self._cold_pause()
    elif pos == P_ABORT:
        self._cold_abort()
    elif pos == P_SKIP:
        self._cold_skip()
    elif pos == P_DAY:
        self._cold_set_display_mode("day")
    elif pos == P_NIGHT:
        self._cold_set_display_mode("night")
    elif pos == P_PROFILE:
        self._cold_set_profile("carrier" if self._cold_profile == "land" else "land")
    self._cold_refresh_ui()


def _cold_arm_or_continue(self):
    if self._cold_state in ("idle", "aborted", "complete"):
        self._cold_state = "armed"
        self._cold_step_index = -1
        self._cold_last_action = "PRESS START AGAIN TO RUN"
        self._cold_log("ARMED")
        return

    if self._cold_state == "armed":
        self._cold_state = "running"
        self._cold_step_index = 0
        self._cold_log("RUN")
        self._cold_run_next_step()
        return

    if self._cold_state == "paused":
        self._cold_state = "running"
        self._cold_log("RESUME")
        self._cold_run_next_step()
        return

    if self._cold_state == "hold":
        self._cold_state = "running"
        self._cold_log("CONTINUE")
        self._cold_step_index += 1
        self._cold_run_next_step()
        return

    if self._cold_state == "wait_user":
        self._cold_state = "running"
        self._cold_log("USER CONFIRM")
        self._cold_step_index += 1
        self._cold_run_next_step()
        return

    if self._cold_state == "select_display":
        if not self._cold_display_mode:
            self._cold_enter_hold("SELECT DAY OR NIGHT")
            return
        self._cold_state = "running"
        self._cold_step_index += 1
        self._cold_run_next_step()
        return


def _cold_run_next_step(self):
    if self._cold_state != "running":
        return

    steps = [
        ("BATTERY ON", "send", "battery_on"),
        ("APU START", "send", "apu_start"),
        ("CONFIRM APU READY", "user", "APU READY? PRESS START"),
        ("RIGHT ENGINE CRANK", "send", "right_engine_crank"),
        ("SET RIGHT THROTTLE IDLE", "user", "SET R THROTTLE IDLE, THEN START"),
        ("CONFIRM RIGHT ENGINE STABLE", "flag_right", "R ENGINE STABLE CONFIRMED"),
        ("LEFT ENGINE CRANK", "send", "left_engine_crank"),
        ("SET LEFT THROTTLE IDLE", "user", "SET L THROTTLE IDLE, THEN START"),
        ("CONFIRM LEFT ENGINE STABLE", "flag_left", "L ENGINE STABLE CONFIRMED"),
        ("APU OFF", "apu_off", "apu_off"),
        ("CLOSE CANOPY", "supervised", "canopy_close"),
        ("BLEED AIR PULL ROTATE 360", "supervised", "bleed_air_cycle"),
        ("TRIM RESET", "supervised", "trim_reset"),
        ("FCS RESET", "supervised", "fcs_reset"),
        ("ECM RECEIVE", "supervised", "ecm_receive"),
        ("MANUAL IFF ON", "user", "OPEN IFF MANUALLY, THEN START"),
        ("SELECT DISPLAY MODE", "select_display", "SELECT DAY OR NIGHT"),
        ("APPLY DISPLAY BRIGHTNESS", "display_brightness", ""),
        ("LOCAL ICP READY", "unlock", ""),
        ("INS MODE", "ins", ""),
        ("COMPLETE", "complete", ""),
    ]
    self._cold_total_steps = len(steps) - 1

    if self._cold_step_index >= len(steps):
        self._cold_state = "complete"
        self._cold_last_action = "COLD START COMPLETE"
        self._cold_refresh_ui()
        return

    title, kind, payload = steps[self._cold_step_index]
    self._cold_last_action = title
    self._cold_refresh_ui()

    if kind == "send":
        self._cold_send_configured_async(payload, lambda: _cold_advance_if_running(self))
    elif kind == "supervised":
        self._cold_last_action = f"SUPERVISE {title}"
        self._cold_refresh_ui()
        self._cold_send_configured_async(payload, lambda: _cold_advance_if_running(self))
    elif kind == "user":
        self._cold_state = "wait_user"
        self._cold_last_action = str(payload)
    elif kind == "flag_right":
        self._cold_right_engine_online = True
        self._cold_last_action = "R ENGINE STABLE / UFC STANDBY"
        QTimer.singleShot(500, lambda: _cold_advance_if_running(self))
    elif kind == "flag_left":
        self._cold_left_engine_online = True
        self._cold_last_action = "BOTH ENGINES STABLE"
        QTimer.singleShot(500, lambda: _cold_advance_if_running(self))
    elif kind == "apu_off":
        def _after_apu_off():
            self._cold_apu_off = True
            _cold_advance_if_running(self)
        self._cold_send_configured_async(payload, _after_apu_off)
    elif kind == "select_display":
        self._cold_state = "select_display"
        self._cold_last_action = "SELECT DAY OR NIGHT, THEN START"
    elif kind == "display_brightness":
        self._cold_apply_display_brightness()
        QTimer.singleShot(700, lambda: _cold_advance_if_running(self))
    elif kind == "unlock":
        self._cold_unlock_local_icp()
        QTimer.singleShot(700, lambda: _cold_advance_if_running(self))
    elif kind == "ins":
        self._cold_send_configured_async(
            "ins_carrier" if self._cold_profile == "carrier" else "ins_land",
            lambda: _cold_advance_if_running(self),
        )
    elif kind == "complete":
        self._cold_state = "complete"
        self._cold_last_action = "COLD START COMPLETE"
        self._cold_refresh_ui()


def _cold_advance_if_running(self):
    if getattr(self, "_cold_state", None) == "running":
        self._cold_step_index += 1
        self._cold_run_next_step()


def _cold_enter_hold(self, reason: str):
    self._cold_sequence_token += 1
    self._cold_state = "hold"
    self._cold_hold_reason = reason
    self._cold_last_action = f"HOLD: {reason}"
    self._cold_log(self._cold_last_action)
    self._cold_refresh_ui()


def _cold_abort(self):
    self._cold_sequence_token += 1
    self._cold_state = "aborted"
    self._cold_last_action = "ABORTED"
    self._cold_log("ABORTED")
    self._cold_refresh_ui()


def _cold_pause(self):
    if self._cold_state in ("running", "wait_user", "select_display"):
        self._cold_sequence_token += 1
        self._cold_state = "paused"
        self._cold_last_action = "PAUSED"
        self._cold_log("PAUSED")
        self._cold_refresh_ui()


def _cold_skip(self):
    if self._cold_state in ("running", "wait_user", "hold", "select_display", "paused"):
        self._cold_sequence_token += 1
        self._cold_state = "running"
        self._cold_step_index += 1
        self._cold_log("SKIP")
        self._cold_run_next_step()


def _cold_set_display_mode(self, mode: str):
    mode = str(mode).lower()
    if mode not in ("day", "night"):
        return
    self._cold_display_mode = mode
    cfg = load_config()
    cfg["cold_start_display_mode"] = mode
    save_config(cfg)
    self._cold_last_action = f"DISPLAY MODE {mode.upper()}"
    self._cold_log(self._cold_last_action)


def _cold_set_profile(self, profile: str):
    profile = str(profile).lower()
    if profile not in ("land", "carrier"):
        return
    self._cold_profile = profile
    cfg = load_config()
    cfg["cold_start_profile"] = profile
    save_config(cfg)
    self._cold_last_action = f"PROFILE {profile.upper()}"
    self._cold_log(self._cold_last_action)


def _cold_entries_from_config(self, key: str) -> List[Dict[str, Any]]:
    cfg = _merged_config()
    item = cfg.get("cold_start_controls", {}).get(key, {})
    if not isinstance(item, dict):
        self._cold_log(f"{key}: INVALID CONFIG")
        self._cold_last_action = f"{self._cold_last_action} / BAD CFG"
        return []

    raw_sequence = item.get("sequence")
    if isinstance(raw_sequence, list):
        entries: List[Dict[str, Any]] = []
        for raw in raw_sequence:
            if not isinstance(raw, dict):
                continue
            repeat = max(1, int(raw.get("repeat", 1) or 1))
            for _ in range(repeat):
                entries.append({
                    "id": raw.get("id", ""),
                    "value": raw.get("value", raw.get("command", "")),
                    "delay_ms": max(0, int(raw.get("delay_ms", 0) or 0)),
                })
        return entries

    return [{
        "id": item.get("id", ""),
        "value": item.get("value", item.get("command", "")),
        "delay_ms": max(0, int(item.get("delay_ms", 500) or 0)),
    }]


def _cold_send_configured(self, key: str) -> bool:
    """Compatibility synchronous sender for short one-shot controls."""
    sent = False
    for entry in self._cold_entries_from_config(key):
        ident = str(entry.get("id", "") or "").strip()
        if not ident:
            self._cold_log(f"{key}: NO ID")
            self._cold_last_action = f"{self._cold_last_action} / NO ID"
            continue
        value = entry.get("value", "")
        ok = send_dcs_bios(ident, value)
        sent = sent or ok
        self._cold_log(f"{key}: {ident} {value} {'OK' if ok else 'FAIL'}")
        if not ok:
            self._cold_enter_hold(f"{key} SEND FAILED")
            return False
    return sent


def _cold_send_configured_async(self, key: str, done: Callable[[], None]) -> None:
    entries = self._cold_entries_from_config(key)
    self._cold_sequence_token += 1
    token = self._cold_sequence_token
    if not entries:
        QTimer.singleShot(0, done)
        return
    self._cold_run_sequence_entries(key, entries, 0, token, done)


def _cold_run_sequence_entries(self, key: str, entries: List[Dict[str, Any]], index: int, token: int, done: Callable[[], None]) -> None:
    if token != getattr(self, "_cold_sequence_token", None):
        return
    if getattr(self, "_cold_state", None) != "running":
        return
    if index >= len(entries):
        done()
        return

    entry = entries[index]
    ident = str(entry.get("id", "") or "").strip()
    delay_ms = max(0, int(entry.get("delay_ms", 0) or 0))
    if not ident:
        self._cold_log(f"{key}: NO ID")
        self._cold_last_action = f"{self._cold_last_action} / NO ID"
        self._cold_refresh_ui()
        QTimer.singleShot(delay_ms, lambda: self._cold_run_sequence_entries(key, entries, index + 1, token, done))
        return

    value = entry.get("value", "")
    ok = send_dcs_bios(ident, value)
    self._cold_log(f"{key}: {ident} {value} {'OK' if ok else 'FAIL'}")
    if not ok:
        self._cold_enter_hold(f"{key} SEND FAILED")
        return
    QTimer.singleShot(delay_ms, lambda: self._cold_run_sequence_entries(key, entries, index + 1, token, done))


def _cold_apply_display_brightness(self):
    cfg = _merged_config()
    presets = cfg.get("display_brightness_presets", DEFAULT_DISPLAY_PRESETS)
    preset = presets.get(self._cold_display_mode, DEFAULT_DISPLAY_PRESETS["day"])
    controls = cfg.get("cold_start_controls", {})

    labels = {
        "lddi": "LDDI",
        "rddi": "RDDI",
        "ampcd": "AMPCD",
        "hud": "HUD",
    }
    results = []

    # Set known DAY/NIGHT selectors first.  Ambiguous selectors can be left with
    # an empty id in config and will be skipped.
    for target in ("lddi", "rddi", "ampcd", "hud"):
        item = controls.get(f"display_{target}_select", {})
        ident = str(item.get("id", "") or "").strip() if isinstance(item, dict) else ""
        if not ident:
            continue
        value = item.get(f"{self._cold_display_mode}_value", item.get("value", ""))
        ok = send_dcs_bios(ident, value)
        results.append(f"{labels[target]} SEL {'OK' if ok else 'FAIL'}")

    for target in ("lddi", "rddi", "ampcd", "hud"):
        percent = int(preset.get(target, 0))
        item = controls.get(f"display_{target}", {})
        ident = str(item.get("id", "") or "").strip() if isinstance(item, dict) else ""
        value_type = item.get("value_type", "analog") if isinstance(item, dict) else "analog"
        if not ident:
            results.append(f"{labels[target]} {percent}% NO ID")
            continue
        value = _pct_to_bios(percent) if value_type == "analog" else percent
        ok = send_dcs_bios(ident, value)
        results.append(f"{labels[target]} {percent}% {'OK' if ok else 'FAIL'}")
    self._cold_display_brightness_applied = True
    self._cold_last_action = " / ".join(results)


def _cold_unlock_local_icp(self):
    self._cold_normal_ufc_locked = not (
        self._cold_right_engine_online
        and self._cold_left_engine_online
        and self._cold_apu_off
        and self._cold_display_brightness_applied
    )
    if self._cold_normal_ufc_locked:
        self._cold_enter_hold("UFC LOCK CONDITIONS NOT MET")
        return
    self._cold_last_action = "UFC ONLINE / LOCAL ICP READY"


def _cold_status_lines(self):
    state = getattr(self, "_cold_state", "idle").upper()
    idx = getattr(self, "_cold_step_index", -1)
    total = getattr(self, "_cold_total_steps", 20)
    step_txt = "--" if idx < 0 else f"{idx:02d}/{total:02d}"
    profile = getattr(self, "_cold_profile", "land").upper()
    mode = getattr(self, "_cold_display_mode", "day").upper()
    r_eng = "STABLE" if getattr(self, "_cold_right_engine_online", False) else "OFF/START"
    l_eng = "STABLE" if getattr(self, "_cold_left_engine_online", False) else "OFF/START"
    apu = "OFF" if getattr(self, "_cold_apu_off", False) else "ON/REQ"
    ufc = "READY" if not getattr(self, "_cold_normal_ufc_locked", True) else (
        "STANDBY" if getattr(self, "_cold_right_engine_online", False) else "LOCKED"
    )
    return {
        "state": f"STATE {state:<12} STEP {step_txt:<6} PROFILE {profile}",
        "engines": f"R ENG {r_eng:<10} L ENG {l_eng:<10} APU {apu:<8} UFC {ufc}",
        "action": f"ACTION {getattr(self, '_cold_last_action', 'READY')}",
        "mode": f"DISPLAY {mode:<5}  SUPERVISE ACTIONS / MANUAL IFF REQUIRED",
    }


def _cold_refresh_ui(self):
    cells = getattr(self, "_cold_status_cells", {})
    if not cells:
        return
    lines = self._cold_status_lines()
    for key, text in lines.items():
        self._cold_set_cell(key, text)


def _cold_set_cell(self, key: str, text: str):
    cell = getattr(self, "_cold_status_cells", {}).get(key)
    if not cell:
        return
    cell._var_text = text
    cell.update()


def _cold_log(self, message: str):
    ts = time.strftime("%H:%M:%S", time.localtime())
    try:
        self._key_press_log.append((ts, f"COLD:{message}"))
        if len(self._key_press_log) > 50:
            self._key_press_log.pop(0)
        self.keyLogUpdated.emit(ts, f"COLD:{message}")
    except Exception:
        pass
