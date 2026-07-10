# -*- coding: utf-8 -*-
"""Split RADAR/INS setup and AMPCD PB19 into two confirmed checklist steps.

The original combined step sent RADAR OPR, selected LAND/CV INS, waited ten
seconds, pressed AMPCD PB19, and only then asked for one user confirmation.
This patch changes that workflow to two independent steps:

1. Set RADAR OPR and the selected LAND/CV INS position, then wait for START.
2. Press and release AMPCD PB19, then wait for START again.

There is intentionally no fixed delay between the two steps.  The user's first
confirmation is the gate that allows PB19 to be pressed.
"""
from __future__ import annotations

from typing import Callable


def install_radar_ins_step_split(UFCKeypadWindowClass) -> None:
    """Install the two-step RADAR/INS + AMPCD PB19 workflow."""
    if getattr(UFCKeypadWindowClass, "_radar_ins_step_split_installed", False):
        return
    UFCKeypadWindowClass._radar_ins_step_split_installed = True

    previous_step_list = UFCKeypadWindowClass._cold_step_list
    previous_run_next_step = UFCKeypadWindowClass._cold_run_next_step

    def _cold_step_list(self):
        steps = []
        for step in previous_step_list(self):
            if step[0] == "RADAR / INS":
                steps.extend([
                    (
                        "RADAR / INS",
                        "radar_ins_confirm",
                        "",
                        "Set RADAR OPR and selected LAND/CV INS. Verify both, then press START.",
                    ),
                    (
                        "AMPCD PB19",
                        "ampcd_pb19_confirm",
                        "",
                        "Press and release AMPCD PB19. Verify the alignment page, then press START.",
                    ),
                ])
            else:
                steps.append(step)
        return steps

    def _enter_user_confirmation(self, action: str, detail: str) -> None:
        self._cold_state = "wait_user"
        self._cold_exec_phase = "USER"
        self._cold_last_action = action
        self._cold_step_detail = detail
        self._cold_refresh_ui()

    def _cold_run_next_step(self):
        if getattr(self, "_cold_state", None) != "running":
            return

        steps = self._cold_step_list()
        index = int(getattr(self, "_cold_step_index", -1))
        if not (0 <= index < len(steps)):
            previous_run_next_step(self)
            return

        title, kind, payload, hint = steps[index]
        if kind not in ("radar_ins_confirm", "ampcd_pb19_confirm"):
            previous_run_next_step(self)
            return

        self._cold_total_steps = len(steps)
        self._cold_last_action = title
        self._cold_step_detail = hint
        self._cold_exec_phase = "AUTO"
        self._cold_refresh_ui()

        if kind == "radar_ins_confirm":
            def after_ins() -> None:
                self._enter_radar_ins_user_confirmation()

            def after_radar() -> None:
                ins_key = "ins_carrier" if self._cold_profile == "carrier" else "ins_land"
                self._cold_send_configured_async(ins_key, after_ins)

            self._cold_send_configured_async("radar_opr", after_radar)
            return

        def after_pb19() -> None:
            self._enter_ampcd_pb19_user_confirmation()

        self._cold_send_configured_async("ampcd_pb19", after_pb19)

    def _enter_radar_ins_user_confirmation(self) -> None:
        profile = "CV" if self._cold_profile == "carrier" else "LAND"
        _enter_user_confirmation(
            self,
            "RADAR / INS CONFIRM",
            f"RADAR OPR and INS {profile} sent. Verify both positions, then press START.",
        )

    def _enter_ampcd_pb19_user_confirmation(self) -> None:
        _enter_user_confirmation(
            self,
            "AMPCD PB19 CONFIRM",
            "AMPCD PB19 press/release sent. Verify the alignment page, then press START.",
        )

    UFCKeypadWindowClass._cold_step_list = _cold_step_list
    UFCKeypadWindowClass._cold_run_next_step = _cold_run_next_step
    UFCKeypadWindowClass._enter_radar_ins_user_confirmation = _enter_radar_ins_user_confirmation
    UFCKeypadWindowClass._enter_ampcd_pb19_user_confirmation = _enter_ampcd_pb19_user_confirmation
