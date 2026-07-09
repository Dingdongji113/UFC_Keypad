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
        if key == "ejection_seat_arm":
            return [
                # DCS-BIOS path, still useful if it works on the local install.
                {"id": "EJECTION_SEAT_ARMED", "value": 1, "delay_ms": 150},
                # Direct clickable fallback: device 7, command 3006 from DCS-BIOS source.
                {
                    "bridge": "clickable",
                    "device": 7,
                    "command": 3006,
                    "value": 1.0,
                    "label": "EJECTION SEAT ARMED",
                    "delay_ms": 350,
                },
            ]
        if key == "ecm_receive":
            return [
                # DCS-BIOS REC position from source positions XMIT / REC / BIT / STBY / OFF.
                {"id": "ECM_MODE_SW", "value": 1, "delay_ms": 150},
                # Direct clickable fallback: defineTumb range {0,0.4}; REC is 0.1.
                {
                    "bridge": "clickable",
                    "device": 66,
                    "command": 3001,
                    "value": 0.1,
                    "label": "ECM REC",
                    "delay_ms": 350,
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
