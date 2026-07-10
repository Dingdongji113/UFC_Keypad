# -*- coding: utf-8 -*-
"""Direct cockpit command fallback for controls that fail through DCS-BIOS.

The cold-start manager still sends normal DCS-BIOS commands first.  For controls
that have failed in the user's runtime environment, it then sends an Export.lua
bridge command that calls GetDevice(...):performClickableAction(...) directly in
DCS.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List

from PyQt6.QtCore import QTimer

import ufc.dcs_bios as dcs_bios
from ufc.cv_trim_auto import send_direct_clickable


def install_direct_command_fixups(UFCKeypadWindowClass) -> None:
    """Patch sequence execution and selected cold-start command entries."""
    if getattr(UFCKeypadWindowClass, "_direct_command_fixups_installed", False):
        return
    UFCKeypadWindowClass._direct_command_fixups_installed = True

    previous_entries_from_config = UFCKeypadWindowClass._cold_entries_from_config

    def _cold_entries_from_config(self, key: str) -> List[Dict[str, Any]]:
        if key == "apu_start":
            return [
                {"id": "APU_CONTROL_SW", "value": 1, "delay_ms": 100},
                {
                    # Local command_defs.lua: APU_ControlSw_TM_WARTHOG=3023.
                    # Unlike cockpit command 3001, this latching input command
                    # was verified live to hold argument 375 at 1.0.
                    "bridge": "clickable", "device": 12, "command": 3023,
                    "value": 1.0, "label": "APU LATCH ON", "delay_ms": 350,
                },
            ]
        if key == "apu_off":
            return [
                {"id": "APU_CONTROL_SW", "value": 0, "delay_ms": 100},
                {
                    "bridge": "clickable", "device": 12, "command": 3023,
                    "value": 0.0, "label": "APU LATCH OFF", "delay_ms": 350,
                },
            ]
        if key == "apu_off_flaps_half":
            return [
                {"id": "APU_CONTROL_SW", "value": 0, "delay_ms": 100},
                {
                    "bridge": "clickable", "device": 12, "command": 3023,
                    "value": 0.0, "label": "APU LATCH OFF", "delay_ms": 350,
                },
                {"id": "FLAP_SW", "value": 1, "delay_ms": 150},
                {
                    "bridge": "clickable", "device": 2, "command": 3007,
                    "value": 0.0, "label": "FLAPS HALF", "delay_ms": 350,
                },
            ]
        if key == "ejection_seat_arm":
            return [
                # DCS-BIOS path, still useful if it works on the local install.
                {"id": "EJECTION_SEAT_ARMED", "value": 0, "delay_ms": 150},
                # Direct clickable fallback: device 7, command 3006 from DCS-BIOS source.
                {
                    "bridge": "clickable",
                    "device": 7,
                    "command": 3006,
                    "value": 0.0,
                    "label": "EJECTION SEAT ARMED",
                    "delay_ms": 350,
                },
            ]
        if key == "ecm_receive":
            return [
                # Local DCS input mapping confirms REC is cockpit value 0.3.
                {"id": "ECM_MODE_SW", "value": 3, "delay_ms": 150},
                # Direct clickable fallback: local input default.lua maps REC to 0.3.
                {
                    "bridge": "clickable",
                    "device": 66,
                    "command": 3001,
                    "value": 0.3,
                    "label": "ECM REC",
                    "delay_ms": 350,
                },
            ]
        if key == "fcs_reset_rwr_power":
            return [
                {"id": "FCS_RESET_BTN", "value": 1, "delay_ms": 80},
                {"id": "FCS_RESET_BTN", "value": 0, "delay_ms": 120},
                # The ALR-67 POWER control is latching. Sending a release/0
                # immediately after 1 turns it back off on this DCS build.
                {"id": "RWR_POWER_BTN", "value": 1, "delay_ms": 150},
                {
                    "bridge": "clickable", "device": 53, "command": 3001,
                    "value": 1.0, "label": "RWR POWER ON", "delay_ms": 350,
                },
            ]
        if key == "canopy_oxygen":
            return previous_entries_from_config(self, "canopy_close") + [
                {"id": "OBOGS_SW", "value": 1, "delay_ms": 150},
                {
                    "bridge": "clickable", "device": 10, "command": 3001,
                    "value": 1.0, "label": "OBOGS ON", "delay_ms": 350,
                },
            ]
        if key == "radar_opr":
            return [
                {"id": "RADAR_SW", "value": 2, "delay_ms": 150},
                {
                    "bridge": "clickable", "device": 42, "command": 3001,
                    "value": 0.2, "label": "RADAR OPR", "delay_ms": 350,
                },
            ]
        if key in ("ins_land", "ins_carrier", "ins_ifa"):
            state = {"ins_land": 2, "ins_carrier": 1, "ins_ifa": 4}[key]
            value = state / 10.0
            return [
                {"id": "INS_SW", "value": state, "delay_ms": 150},
                {
                    "bridge": "clickable", "device": 44, "command": 3001,
                    "value": value, "label": key.upper(), "delay_ms": 350,
                },
            ]
        if key == "ampcd_pb19":
            return [
                {"id": "AMPCD_PB_19", "value": 1, "delay_ms": 120},
                {"id": "AMPCD_PB_19", "value": 0, "delay_ms": 120},
                {
                    "bridge": "clickable", "device": 37, "command": 3029,
                    "value": 1.0, "hold_ms": 120, "release_value": 0.0,
                    "label": "AMPCD PB19", "delay_ms": 350,
                },
            ]
        if key in ("right_ddi_pb18", "right_ddi_pb03", "right_ddi_pb20"):
            number = {"right_ddi_pb18": 18, "right_ddi_pb03": 3, "right_ddi_pb20": 20}[key]
            command = {18: 3028, 3: 3013, 20: 3030}[number]
            ident = f"RIGHT_DDI_PB_{number:02d}"
            return [
                {"id": ident, "value": 1, "delay_ms": 120},
                {"id": ident, "value": 0, "delay_ms": 120},
                {
                    "bridge": "clickable", "device": 36, "command": command,
                    "value": 1.0, "hold_ms": 120, "release_value": 0.0,
                    "label": f"RDDI OSB{number}", "delay_ms": 350,
                },
            ]
        if key in ("hmd_day", "hmd_night"):
            is_day = key == "hmd_day"
            bios_value = 65535 if is_day else 30583
            direct_value = 0.75 if is_day else 0.35
            return [
                {"id": "HMD_OFF_BRT", "value": bios_value, "delay_ms": 150},
                {
                    "bridge": "clickable", "device": 58, "command": 3001,
                    "value": direct_value, "label": key.upper(), "delay_ms": 350,
                },
            ]
        return previous_entries_from_config(self, key)

    def _cold_run_sequence_entries(self, key: str, entries: List[Dict[str, Any]], index: int,
                                   token: int, done: Callable[[], None]) -> None:
        if token != getattr(self, "_cold_sequence_token", None):
            return
        if getattr(self, "_cold_state", None) != "running":
            return
        if index >= len(entries):
            done()
            return

        entry = entries[index]
        delay_ms = max(0, int(entry.get("delay_ms", 0) or 0))

        if entry.get("bridge") == "clickable" or "device" in entry:
            try:
                ok = send_direct_clickable(
                    int(entry.get("device")),
                    int(entry.get("command")),
                    float(entry.get("value")),
                    label=str(entry.get("label", key)),
                    hold_ms=int(entry.get("hold_ms", 0) or 0),
                    release_value=entry.get("release_value"),
                )
            except Exception as exc:
                ok = False
                self._cold_log(f"{key}: bridge exception {exc}")
            label = str(entry.get("label", "DIRECT"))
            self._cold_log(f"{key}: BRIDGE {label} {'OK' if ok else 'FAIL'}")
            # Do not hard-stop on bridge send failure: if DCS-BIOS worked, stopping here
            # would create a false failure.  The visible cockpit state is the source of truth.
            QTimer.singleShot(delay_ms, lambda: self._cold_run_sequence_entries(key, entries, index + 1, token, done))
            return

        ident = str(entry.get("id", "") or "").strip()
        if not ident:
            self._cold_log(f"{key}: NO ID")
            self._cold_last_action = f"{self._cold_last_action} / NO ID"
            self._cold_refresh_ui()
            QTimer.singleShot(delay_ms, lambda: self._cold_run_sequence_entries(key, entries, index + 1, token, done))
            return

        value = entry.get("value", "")
        ok = dcs_bios.send_dcs_bios(ident, value)
        self._cold_log(f"{key}: {ident} {value} {'OK' if ok else 'FAIL'}")
        if not ok:
            self._cold_enter_hold(f"{key} SEND FAILED")
            return
        QTimer.singleShot(delay_ms, lambda: self._cold_run_sequence_entries(key, entries, index + 1, token, done))

    UFCKeypadWindowClass._cold_entries_from_config = _cold_entries_from_config
    UFCKeypadWindowClass._cold_run_sequence_entries = _cold_run_sequence_entries
