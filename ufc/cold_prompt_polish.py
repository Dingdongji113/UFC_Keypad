# -*- coding: utf-8 -*-
"""Pilot-facing cold-start wording and compact checklist layout.

This module is intentionally installed last.  It does not change command order,
timing, DCS-BIOS mappings, Export bridge behavior, or confirmation gates.  It
only translates implementation-oriented status text into concise cockpit/checklist
language and applies conservative font fitting to the existing cold-start labels.
"""
from __future__ import annotations

import re
from typing import Dict, Tuple

from PyQt6.QtWidgets import QLabel

from ufc.cold_direct_entry import ENTRY_CHECKLIST


_TITLE_MAP: Dict[str, str] = {
    "EJECT SAFE OFF": "EJECTION SEAT",
    "BATTERY ON": "DC POWER",
    "APU START": "APU START",
    "APU WAIT": "APU READY",
    "APU READY?": "APU READY",
    "RIGHT CRANK": "RIGHT ENGINE",
    "RIGHT IDLE": "RIGHT ENGINE IDLE",
    "RIGHT STABLE?": "RIGHT ENGINE",
    "LEFT CRANK": "LEFT ENGINE",
    "LEFT IDLE": "LEFT ENGINE IDLE",
    "LEFT STABLE?": "LEFT ENGINE",
    "LIGHTS / ANTI-SKID": "LIGHTING / ANTI-SKID",
    "APU OFF / FLAPS AUTO": "APU / FLAPS",
    "BRIGHTNESS": "DISPLAY LEVELS",
    "CANOPY / OXYGEN": "CANOPY / OBOGS",
    "BLEED AIR": "BLEED AIR",
    "CONTROL CHECK": "CONTROL CHECK",
    "TRIM RESET": "T/O TRIM",
    "FCS / RWR": "FCS / ALR-67",
    "ECM REC": "ECM",
    "RADAR / INS": "RADAR / INS",
    "AMPCD PB19": "INS FAST ALIGN",
    "SAI UNLOCK": "STANDBY ATTITUDE",
    "RADALT MIN": "RADALT MINIMUM",
    "BINGO FUEL": "BINGO FUEL",
    "LOCAL ICP": "UFC READY",
    "CAT TRIM": "LAUNCH TRIM",
    "HMD CAL / IFA": "JHMCS ALIGN",
    "COMPLETE": "STARTUP COMPLETE",
}

_STATIC_PROMPTS: Dict[str, Tuple[str, str]] = {
    "EJECT SAFE OFF": ("SEAT SAFETY — ARMED", "CHECK"),
    "BATTERY ON": ("BATTERY — ON", "DC POWER"),
    "APU START": ("APU STARTING", "MONITOR APU"),
    "APU WAIT": ("WAIT FOR APU READY", "WAIT 5 SEC"),
    "APU READY?": ("CONFIRM APU READY\nPRESS CONTINUE", "APU READY"),
    "RIGHT CRANK": ("CRANK SWITCH — RIGHT", "RIGHT ENGINE START"),
    "RIGHT IDLE": ("AT 25% RPM\nTHROTTLE — IDLE", "PRESS CONTINUE"),
    "RIGHT STABLE?": ("RIGHT ENGINE STABLE\nUFC POWER-UP IN PROGRESS", "UFC INITIALIZING"),
    "LEFT CRANK": ("CRANK SWITCH — LEFT", "LEFT ENGINE START"),
    "LEFT IDLE": ("AT 25% RPM\nTHROTTLE — IDLE", "PRESS CONTINUE"),
    "LEFT STABLE?": ("LEFT ENGINE STABILIZING", "MONITOR ENGINE"),
    "LIGHTS / ANTI-SKID": ("LIGHTING CONFIGURATION\nANTI-SKID — SETTING", "STANDBY"),
    "APU OFF / FLAPS AUTO": ("APU — OFF\nFLAPS — AUTO", "CONFIGURATION SET"),
    "BRIGHTNESS": ("DISPLAY LEVELS\nSELECTED PRESET", "SETTING DISPLAYS"),
    "CANOPY / OXYGEN": ("CANOPY — CLOSE\nOBOGS — ON", "CONFIGURATION SET"),
    "BLEED AIR": ("BLEED AIR SELECTOR\nCYCLING", "CONFIRM NORMAL"),
    "CONTROL CHECK": ("FULL CONTROL CHECK\nSELECT SKIP OR EXECUTE", "OPTIONAL"),
    "TRIM RESET": ("TAKEOFF TRIM\nSETTING REFERENCE", "T/O TRIM"),
    "FCS / RWR": ("FCS — RESET\nALR-67 — ON", "SYSTEMS SET"),
    "ECM REC": ("ECM MODE — REC", "SYSTEM SET"),
    "RADAR / INS": ("RADAR — OPR\nINS ALIGNMENT — SETTING", "VERIFY SELECTORS"),
    "AMPCD PB19": ("FAST ALIGN — SELECTING\nSTANDBY", "AMPCD ALIGN PAGE"),
    "SAI UNLOCK": ("STANDBY INDICATOR\nUNCAGING", "VERIFY FLAG CLEAR"),
    "RADALT MIN": ("SET WARNING HEIGHT\n− DECREASE    + INCREASE", "LIVE COCKPIT VALUE"),
    "BINGO FUEL": ("SET RESERVE QUANTITY\n− DECREASE    + INCREASE", "LIVE COCKPIT VALUE"),
    "LOCAL ICP": ("UP-FRONT CONTROLS\nAVAILABLE", "UFC READY"),
    "CAT TRIM": ("CALCULATING LAUNCH TRIM\nFROM GROSS WEIGHT", "ADJUSTING"),
    "HMD CAL / IFA": ("HMD — ON\nINS — IFA", "INITIALIZING"),
    "COMPLETE": ("AIRCRAFT CONFIGURED\nMISSION CHECKS NEXT", "PRESS COMPLETE"),
}

_CONTROL_ACTIONS: Dict[str, Tuple[str, str]] = {
    "PROBE EXTEND": ("REFUEL PROBE — EXTEND", "OBSERVE FULL TRAVEL"),
    "PROBE RETRACT": ("REFUEL PROBE — RETRACT", "CONFIRM STOWED"),
    "HOOK DOWN": ("ARRESTING HOOK — DOWN", "OBSERVE FULL TRAVEL"),
    "HOOK UP": ("ARRESTING HOOK — UP", "CONFIRM STOWED"),
    "LAUNCH BAR DOWN": ("LAUNCH BAR — EXTEND", "OBSERVE FULL TRAVEL"),
    "LAUNCH BAR RETRACT": ("LAUNCH BAR — RETRACT", "CONFIRM STOWED"),
    "WING FOLD": ("WING FOLD — CHECK", "OBSERVE FULL TRAVEL"),
    "WING UNFOLD": ("WING SPREAD — CHECK", "OBSERVE FULL TRAVEL"),
    "WING RESTORE": ("WING POSITION — RESTORE", "WAITING FOR LOCK"),
    "MECHANISMS COMPLETE": ("MECHANISMS — CHECKED", "AXIS CHECK NEXT"),
    "STICK FULL AFT": ("STICK — FULL AFT", "CHECK CONTROL RESPONSE"),
    "STICK FULL FORWARD": ("STICK — FULL FORWARD", "CHECK CONTROL RESPONSE"),
    "STICK FULL LEFT": ("STICK — FULL LEFT", "CHECK CONTROL RESPONSE"),
    "STICK FULL RIGHT": ("STICK — FULL RIGHT", "CHECK CONTROL RESPONSE"),
    "RUDDER FULL LEFT": ("RUDDER — FULL LEFT", "CHECK CONTROL RESPONSE"),
    "RUDDER FULL RIGHT": ("RUDDER — FULL RIGHT", "CHECK CONTROL RESPONSE"),
    "CONTROL CHECK COMPLETE": ("FLIGHT CONTROLS — CHECKED", "PRESS CONTINUE"),
    "CONTROL DATA MISSING": ("CONTROL DATA UNAVAILABLE", "CONTINUE TO SKIP"),
}

_OSB_PROGRESS = {
    "RDDI OSB18 1/2": "PAGE SETUP 1/4",
    "RDDI OSB18 2/2": "PAGE SETUP 2/4",
    "RDDI OSB3": "PAGE SETUP 3/4",
    "RDDI OSB20": "PAGE SETUP 4/4",
}

_BASE_FONT_SIZES = {
    "title": 31,
    "rpm": 29,
    "step": 28,
    "hint": 18,
    "status": 13,
}


def _profile_alignment(self) -> str:
    return "CV" if str(getattr(self, "_cold_profile", "land")).lower() == "carrier" else "GND"


def _format_launch_trim(detail: str) -> Tuple[str, str] | None:
    match = re.search(
        r"Weight\s+([0-9.]+)\s+lb,\s*target\s+([0-9.]+)\s+deg,\s*current\s+([0-9.]+)\s+deg",
        str(detail or ""),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    weight = float(match.group(1))
    target = float(match.group(2))
    current = float(match.group(3))
    return (
        f"GROSS WT {weight:,.0f} LB\nTRIM {current:.1f}° → {target:.1f}°",
        "ADJUSTING",
    )


def install_cold_prompt_polish(UFCKeypadWindowClass) -> None:
    """Install the final pilot-facing wording layer."""
    if getattr(UFCKeypadWindowClass, "_cold_prompt_polish_installed", False):
        return
    UFCKeypadWindowClass._cold_prompt_polish_installed = True

    previous_status_lines = UFCKeypadWindowClass._cold_status_lines
    previous_set_cell = UFCKeypadWindowClass._cold_set_cell

    def _cold_prompt_current_step(self):
        steps = self._cold_step_list()
        index = int(getattr(self, "_cold_step_index", -1))
        if 0 <= index < len(steps):
            return steps[index]
        return None

    def _cold_prompt_content(self, original_title: str, kind: str) -> Tuple[str, str, str]:
        action = str(getattr(self, "_cold_last_action", "") or "")
        detail = str(getattr(self, "_cold_step_detail", "") or "")
        state = str(getattr(self, "_cold_state", "") or "")
        display_title = _TITLE_MAP.get(original_title, original_title)
        hint, status = _STATIC_PROMPTS.get(original_title, (detail, ""))

        if state == "hold":
            return "SYSTEM HOLD", "CHECK COCKPIT CONDITION\nCONTINUE ONLY IF SAFE", "DETAILS RECORDED IN LOG"

        if kind == "lighting_setup":
            lighting_phase = str(getattr(self, "_cold_lighting_phase", "") or "")
            mode = str(getattr(self, "_cold_display_mode", "day") or "day").upper()
            profile = "CV" if str(getattr(self, "_cold_profile", "land")).lower() == "carrier" else "LAND"
            if lighting_phase == "ask_flood":
                return display_title, "FLOOD LIGHTS\n70% LEVEL?", "SELECT NO OR YES"
            if lighting_phase == "ask_chart":
                return display_title, "CHART LIGHT\n70% LEVEL?", "SELECT NO OR YES"
            return display_title, f"{mode} CONFIGURATION\nLIGHTING / ANTI-SKID — SETTING", f"{profile} PROFILE"

        if kind == "control_check":
            control_phase = str(getattr(self, "_cold_control_phase", "") or "")
            progress = int(getattr(self, "_cold_control_progress", 0) or 0)
            if action in _CONTROL_ACTIONS:
                mapped_action, mapped_hint = _CONTROL_ACTIONS[action]
                if action == "CONTROL CHECK COMPLETE":
                    return display_title, f"{mapped_action}\n{mapped_hint}", "CONTROL CHECK 100%"
                return mapped_action, mapped_hint, f"CONTROL CHECK {progress}%"
            if control_phase in ("aborted", "restoring"):
                return display_title, "RESTORING INITIAL POSITIONS\nCONTROLS — NEUTRAL", f"CONTROL CHECK {progress}%"
            return display_title, hint, f"CONTROL CHECK {progress}%"

        if kind == "radar_ins_confirm":
            align = _profile_alignment(self)
            if state == "wait_user":
                return display_title, f"RADAR — OPR\nINS ALIGNMENT — {align}", "VERIFY SELECTORS · CONTINUE"
            return display_title, f"RADAR — OPR\nINS ALIGNMENT — {align}", "SETTING SELECTORS"

        if kind == "ampcd_pb19_confirm":
            if state == "wait_user" or action == "AMPCD PB19 CONFIRM":
                return display_title, "FAST ALIGN — SELECTED\nVERIFY ALIGNMENT · CONTINUE", "AMPCD ALIGN PAGE"
            return display_title, "FAST ALIGN — SELECTING\nSTANDBY", "AMPCD ALIGN PAGE"

        if kind == "manual_sai_unlock":
            if state == "wait_user":
                return display_title, "STANDBY INDICATOR — UNCAGED\nVERIFY FLAG CLEAR", "PRESS CONTINUE"
            return display_title, "STANDBY INDICATOR\nUNCAGING", "STANDBY"

        if kind == "manual_radalt_direct":
            return display_title, "SET WARNING HEIGHT\n− DECREASE    + INCREASE", "LIVE COCKPIT VALUE"

        if kind == "manual_bingo_direct":
            return display_title, "SET RESERVE QUANTITY\n− DECREASE    + INCREASE", "LIVE COCKPIT VALUE"

        if kind == "cat_trim_auto":
            if action == "CAT TRIM DATA?":
                return display_title, "LAUNCH TRIM DATA\nUNAVAILABLE", "SET MANUALLY · CONTINUE"
            if action == "CAT TRIM LIMIT":
                return display_title, "AUTO TRIM LIMIT\nVERIFY MANUALLY", "PRESS CONTINUE"
            formatted = _format_launch_trim(detail)
            if formatted is not None:
                return display_title, formatted[0], formatted[1]
            return display_title, hint, status

        if kind == "hmd_calibrate":
            if action == "HMD / IFA WAIT 10S":
                return display_title, "INS — IFA\nAVIONICS INITIALIZING", "WAIT 10 SEC"
            if action in _OSB_PROGRESS:
                return display_title, "ALIGNMENT PAGE — OPENING\nSTANDBY", _OSB_PROGRESS[action]
            if action == "HMD CALIBRATE":
                return display_title, "ALIGNMENT PAGE READY\nCOMPLETE HELMET ALIGNMENT", "PRESS CONTINUE"
            return display_title, "HMD — ON\nINS — IFA", "INITIALIZING"

        if kind == "flag_right" or action == "UFC STARTUP":
            return "RIGHT ENGINE", "RIGHT ENGINE STABLE\nUFC POWER-UP IN PROGRESS", "UFC INITIALIZING"

        if kind == "flag_left":
            return "LEFT ENGINE", "LEFT ENGINE STABILIZING", "MONITOR ENGINE"

        if kind == "unlock":
            return display_title, "UP-FRONT CONTROLS\nAVAILABLE", "UFC READY"

        if kind == "complete" or state == "complete":
            return "STARTUP COMPLETE", "AIRCRAFT CONFIGURED\nMISSION CHECKS NEXT", "PRESS COMPLETE"

        return display_title, hint, status

    def _cold_status_lines(self):
        base = previous_status_lines(self)
        if not isinstance(base, dict):
            return base

        left, right = self._cold_get_fresh_rpms()
        l_txt = "---" if left is None else f"{left:05.1f}%"
        r_txt = "---" if right is None else f"{right:05.1f}%"
        waiting_for_rpm = (
            getattr(self, "_cold_detected_mode", "unknown") == "unknown"
            and not getattr(self, "_cold_first_mode_decided", False)
        )
        if waiting_for_rpm:
            return {
                "title": "CHECKING AIRCRAFT",
                "rpm": f"L {l_txt}        R {r_txt}",
                "step": "WAITING FOR ENGINE RPM",
                "hint": "READING LEFT / RIGHT RPM",
                "status": "",
            }

        if getattr(self, "_cold_entry_stage", None) != ENTRY_CHECKLIST:
            confirm = int(getattr(self, "_cold_entry_confirm_count", 0) or 0)
            display = str(getattr(self, "_cold_display_mode", "day") or "day").upper()
            profile = "CV" if str(getattr(self, "_cold_profile", "land")).lower() == "carrier" else "LAND"
            progress = "STEP KEPT" if getattr(self, "_cold_setup_preserve_progress", False) else "NEW CHECKLIST"
            return {
                "title": "COLD START SETUP",
                "rpm": f"L {l_txt}        R {r_txt}",
                "step": f"SELECT {display} / {profile}",
                "hint": "VERIFY DAY / NIGHT\nVERIFY LAND / CV",
                "status": f"CONFIRM {confirm}/2    {progress}",
            }

        steps = self._cold_step_list()
        index = int(getattr(self, "_cold_step_index", -1))
        total = len(steps)
        if not (0 <= index < total):
            state = str(getattr(self, "_cold_state", "") or "")
            if state == "armed":
                return {
                    "title": "F/A-18C COLD START",
                    "rpm": f"L {l_txt}        R {r_txt}",
                    "step": "COLD START ARMED",
                    "hint": "CHECKLIST READY\nPRESS START",
                    "status": "ARMED",
                }
            return {
                "title": "F/A-18C COLD START",
                "rpm": f"L {l_txt}        R {r_txt}",
                "step": "COLD START READY",
                "hint": "CHECK CONFIGURATION\nPRESS START",
                "status": "READY",
            }

        step = steps[index]
        original_title = str(step[0])
        kind = str(step[1])
        action, hint, status = self._cold_prompt_content(original_title, kind)
        return {
            "title": "F/A-18C COLD START",
            "rpm": f"L {l_txt}        R {r_txt}",
            "step": f"STEP {index + 1:02d}/{total:02d}\n{action}",
            "hint": hint,
            "status": status,
        }

    def _cold_set_cell(self, key: str, text: str):
        previous_set_cell(self, key, text)
        cell = getattr(self, "_cold_status_cells", {}).get(key)
        if not isinstance(cell, QLabel):
            return
        base_size = _BASE_FONT_SIZES.get(key)
        if base_size is None:
            return
        lines = str(text or "").splitlines() or [""]
        longest = max(len(line) for line in lines)
        size = base_size
        if key == "step":
            if longest > 30:
                size = 25
            if longest > 38:
                size = 22
        elif key == "hint":
            if longest > 34 or len(lines) > 2:
                size = 16
        elif key == "status" and longest > 58:
            size = 12
        font = cell.font()
        if font.pointSize() != size:
            font.setPointSize(size)
            cell.setFont(font)

    UFCKeypadWindowClass._cold_prompt_current_step = _cold_prompt_current_step
    UFCKeypadWindowClass._cold_prompt_content = _cold_prompt_content
    UFCKeypadWindowClass._cold_status_lines = _cold_status_lines
    UFCKeypadWindowClass._cold_set_cell = _cold_set_cell
