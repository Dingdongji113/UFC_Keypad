# -*- coding: utf-8 -*-
"""HMD calibration timing fixups.

The HMD calibration page is sensitive to both avionics initialization time and
OSB press duration.  This patch is installed after the other cold-start patches
and changes two things without duplicating the full checklist state machine:

- after HMD power and INS IFA are commanded, wait 10 seconds before the first
  RDDI OSB command;
- send each RDDI OSB as one 500 ms dual-path hold (DCS-BIOS + Export bridge),
  instead of two separate short clicks from the two command paths.
"""
from __future__ import annotations

from typing import Callable, Dict, Tuple

from PyQt6.QtCore import QTimer

import ufc.dcs_bios as dcs_bios
from ufc.cv_trim_auto import send_direct_clickable

HMD_IFA_TO_OSB_DELAY_MS = 10000
RDDI_OSB_HOLD_MS = 500
RDDI_OSB_POST_RELEASE_MS = 200

_RDDI_BUTTONS: Dict[str, Tuple[str, int, int]] = {
    "right_ddi_pb18": ("RIGHT_DDI_PB_18", 3028, 18),
    "right_ddi_pb03": ("RIGHT_DDI_PB_03", 3013, 3),
    "right_ddi_pb20": ("RIGHT_DDI_PB_20", 3030, 20),
}


def install_hmd_osb_timing_fix(UFCKeypadWindowClass) -> None:
    """Install the HMD/IFA delay and long RDDI OSB press behavior."""
    if getattr(UFCKeypadWindowClass, "_hmd_osb_timing_fix_installed", False):
        return
    UFCKeypadWindowClass._hmd_osb_timing_fix_installed = True

    previous_send_configured_async = UFCKeypadWindowClass._cold_send_configured_async

    def _is_hmd_cal_step(self) -> bool:
        try:
            index = int(getattr(self, "_cold_step_index", -1))
            steps = self._cold_step_list()
            return 0 <= index < len(steps) and steps[index][0] == "HMD CAL / IFA"
        except Exception:
            return False

    def _send_rddi_osb_hold(self, key: str, done: Callable[[], None]) -> None:
        ident, command, number = _RDDI_BUTTONS[key]
        token = getattr(self, "_cold_sequence_token", 0)
        if getattr(self, "_cold_state", None) != "running":
            return

        bios_ok = dcs_bios.send_dcs_bios(ident, 1)
        bridge_ok = send_direct_clickable(
            36,
            command,
            1.0,
            label=f"RDDI OSB{number} LONG HOLD",
            hold_ms=RDDI_OSB_HOLD_MS,
            release_value=0.0,
        )
        self._cold_log(
            f"{key}: HOLD {RDDI_OSB_HOLD_MS}ms "
            f"DCSBIOS={'OK' if bios_ok else 'FAIL'} BRIDGE={'OK' if bridge_ok else 'FAIL'}"
        )

        def _release_bios() -> None:
            if token != getattr(self, "_cold_sequence_token", 0):
                return
            if getattr(self, "_cold_state", None) != "running":
                return
            release_ok = dcs_bios.send_dcs_bios(ident, 0)
            self._cold_log(f"{key}: RELEASE {'OK' if release_ok else 'FAIL'}")
            QTimer.singleShot(RDDI_OSB_POST_RELEASE_MS, done)

        QTimer.singleShot(RDDI_OSB_HOLD_MS, _release_bios)

    def _cold_send_configured_async(self, key: str, done: Callable[[], None]) -> None:
        if key in _RDDI_BUTTONS:
            self._send_rddi_osb_hold(key, done)
            return

        if key == "ins_ifa" and self._is_hmd_cal_step():
            def _after_ifa() -> None:
                self._cold_exec_phase = "WAIT"
                self._cold_last_action = "HMD / IFA WAIT 10S"
                self._cold_step_detail = (
                    "HMD powered and INS set to IFA. Waiting 10 seconds before RDDI OSB sequence."
                )
                self._cold_log("HMD / IFA initialized; wait 10s before first RDDI OSB")
                self._cold_refresh_ui()
                QTimer.singleShot(HMD_IFA_TO_OSB_DELAY_MS, done)

            previous_send_configured_async(self, key, _after_ifa)
            return

        previous_send_configured_async(self, key, done)

    UFCKeypadWindowClass._is_hmd_cal_step = _is_hmd_cal_step
    UFCKeypadWindowClass._send_rddi_osb_hold = _send_rddi_osb_hold
    UFCKeypadWindowClass._cold_send_configured_async = _cold_send_configured_async
