# -*- coding: utf-8 -*-
"""Cold-start UI polish and safety fixups.

Installed after the cold-start setup patches.  This module keeps the no-frame
text requirement while making the cold pages match the main UFC keypad style:
- plain labels use the same green brightness-driven color family as UFCCell;
- setup buttons are centered as DAY / NIGHT / LAND / CV;
- returning from RESET setup preserves the current step number and restores the
  actual checklist step title instead of showing CONFIRM SETUP;
- stale BATTERY_SW=0 configs are corrected to BATTERY_SW=2 for battery ON;
- stale canopy configs are corrected;
- ECM REC is corrected to the DCS-BIOS REC position;
- DISPLAY BRIGHTNESS is executed immediately after APU OFF and sent as a short
  sequenced burst instead of one same-frame command batch;
- the checklist includes ejection-seat safety off/armed first, ALR-67 power with
  FCS reset, manual standby attitude/radar altitude/bingo setup, and a CV-only
  catapult trim confirmation step;
- after COMPLETE, the large START button becomes COMPLETE and jumps to LOCAL ICP.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QLabel

import ufc.colors as colors
import ufc.dcs_bios as dcs_bios
from ufc.cold_start import DEFAULT_DISPLAY_PRESETS, _merged_config, _pct_to_bios
from ufc.cold_direct_entry import (
    APU_TO_RIGHT_CRANK_MS,
    ENTRY_CHECKLIST,
    ENTRY_SETUP,
    PAGE,
    P_DAY,
    P_NIGHT,
    P_RESET,
    P_START,
)
from ufc.cold_setup_split import P_CV, P_LAND

BRIGHTNESS_SEND_INTERVAL_MS = 60


def install_cold_ui_fixups(UFCKeypadWindowClass) -> None:
    """Install final cold UI layout/style, step order, and command fixups."""
    if getattr(UFCKeypadWindowClass, "_cold_ui_fixups_installed", False):
        return
    UFCKeypadWindowClass._cold_ui_fixups_installed = True

    previous_entries_from_config = UFCKeypadWindowClass._cold_entries_from_config

    def _cold_label_style(self) -> str:
        return f"color: {colors.text_color_br()}; background: transparent; border: none;"

    def _cold_plain_label(self, key: str, x: int, y: int, w: int, h: int,
                          font_size: int, bold: bool = False,
                          align: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignCenter) -> QLabel:
        label = QLabel("", self)
        label._page = PAGE
        label.setGeometry(x, y, w, h)
        label.setAlignment(align)
        label.setWordWrap(True)
        label.setStyleSheet(self._cold_label_style())
        label_font = QFont("B612", font_size)
        label_font.setBold(bold)
        label.setFont(label_font)

        def _rescale_font(new_size, lbl=label, f=label_font):
            f.setPointSize(new_size)
            lbl.setFont(f)

        label.rescale_font = _rescale_font
        self._widget_origins.append((label, x, y, w, h, font_size))
        self._cold_status_cells[key] = label
        return label

    def _init_cold_start_page(self):
        """Create no-frame text layout plus centered setup buttons, START, RESET."""
        self._cold_cells = {}
        self._cold_status_cells = {}

        self._cold_plain_label("title", 8, 20, 1008, 58, 31, True)
        self._cold_plain_label("rpm", 8, 100, 1008, 70, 29, True)
        self._cold_plain_label("step", 8, 196, 1008, 86, 28, True)
        self._cold_plain_label("hint", 80, 302, 864, 72, 18, False)
        self._cold_plain_label("status", 8, 378, 1008, 34, 13, False)

        setup_buttons = [
            ("DAY", P_DAY, 216, 430, 138, 58),
            ("NIGHT", P_NIGHT, 368, 430, 158, 58),
            ("LAND", P_LAND, 540, 430, 138, 58),
            ("CV", P_CV, 692, 430, 116, 58),
        ]
        for text, pos, x, y, w, h in setup_buttons:
            cell = self.place_cell(text, pos, x, y, w, h, font_size=15,
                                   register=False, page=PAGE, bold=True)
            self._cold_cells[pos] = cell

        start = self.place_cell("START", P_START, 312, 505, 400, 82,
                                font_size=25, register=False, page=PAGE, bold=True)
        self._cold_cells[P_START] = start

        reset = self.place_cell("RESET", P_RESET, 884, 545, 132, 42,
                                font_size=12, register=False, page=PAGE, bold=True)
        self._cold_cells[P_RESET] = reset
        self._cold_refresh_ui()

    def _cold_set_cell(self, key: str, text: str):
        cell = getattr(self, "_cold_status_cells", {}).get(key)
        if not cell:
            return
        if isinstance(cell, QLabel):
            cell.setStyleSheet(self._cold_label_style())
            cell.setText(text)
            return
        cell._var_text = text
        cell.update()

    def _cold_step_list(self):
        """Authoritative checklist. CV adds one carrier trim step near the end."""
        steps = [
            ("EJECT SAFE OFF", "send", "ejection_seat_arm", "Set ejection-seat safety OFF / ARMED."),
            ("BATTERY ON", "send", "battery_on", "Auto command."),
            ("APU START", "send", "apu_start", "Auto command."),
            ("APU WAIT", "timer", APU_TO_RIGHT_CRANK_MS, "Wait 5 seconds before right engine."),
            ("APU READY?", "user", "", "Confirm APU ready, then START."),
            ("RIGHT CRANK", "send", "right_engine_crank", "Auto command."),
            ("RIGHT IDLE", "user", "", "Set right throttle IDLE, then START."),
            ("RIGHT STABLE?", "flag_right", "", "Confirm right engine stable."),
            ("LEFT CRANK", "send", "left_engine_crank", "Auto command."),
            ("LEFT IDLE", "user", "", "Set left throttle IDLE, then START."),
            ("LEFT STABLE?", "flag_left", "", "Confirm left engine stable."),
            ("APU OFF / FLAPS AUTO", "apu_off", "apu_off_flaps_auto", "Stop APU and set FLAP switch to AUTO."),
            ("BRIGHTNESS", "display_brightness", "", "Apply selected DAY/NIGHT preset."),
            ("CANOPY / OXYGEN", "supervised", "canopy_oxygen", "Close canopy and set OBOGS ON."),
            ("BLEED AIR", "supervised", "bleed_air_cycle", "Program executes; monitor cockpit."),
            ("TRIM RESET", "supervised", "trim_reset", "Program executes; monitor cockpit."),
            ("FCS / RWR", "supervised", "fcs_reset_rwr_power", "Reset FCS and press ALR-67 POWER."),
            ("ECM REC", "supervised", "ecm_receive", "Program executes; monitor cockpit."),
            ("MANUAL SETUP", "user", "", "Set standby attitude, radar altitude minimum, and bingo fuel; then START."),
            ("LOCAL ICP", "unlock", "", "Verify LOCAL ICP ready."),
            ("RADAR / INS", "ins_radar_setup", "", "RADAR OPR; set LAND/CV INS, wait 10s, press AMPCD PB19; then confirm."),
        ]
        if str(getattr(self, "_cold_profile", "land") or "land").lower() == "carrier":
            steps.append((
                "CAT TRIM",
                "user",
                "",
                "Set nose-up trim by weight: <=44000lb 16 deg; 45000-48000lb 17 deg; >=49000lb 19 deg. Then START.",
            ))
        steps.append((
            "HMD CAL / IFA",
            "hmd_calibrate",
            "",
            "Power HMD, set INS IFA, press RDDI OSB18/18/3/20 in order with 3s intervals, calibrate manually, then START.",
        ))
        steps.append(("COMPLETE", "complete", "", "Done. Press COMPLETE to enter LOCAL ICP."))
        return steps

    def _cold_display_brightness_entries(self):
        cfg = _merged_config()
        mode = str(getattr(self, "_cold_display_mode", "day") or "day").lower()
        if mode not in ("day", "night"):
            mode = "day"
        presets = cfg.get("display_brightness_presets", DEFAULT_DISPLAY_PRESETS)
        preset = presets.get(mode, DEFAULT_DISPLAY_PRESETS["day"])
        controls = cfg.get("cold_start_controls", {})
        labels = {"lddi": "LDDI", "rddi": "RDDI", "ampcd": "AMPCD", "hud": "HUD"}
        entries = []

        for target in ("lddi", "rddi", "ampcd", "hud"):
            item = controls.get(f"display_{target}_select", {})
            ident = str(item.get("id", "") or "").strip() if isinstance(item, dict) else ""
            if not ident:
                continue
            value = item.get(f"{mode}_value", item.get("value", ""))
            entries.append({"label": f"{labels[target]} SEL", "id": ident, "value": value})

        for target in ("lddi", "rddi", "ampcd", "hud"):
            percent = int(preset.get(target, 0))
            item = controls.get(f"display_{target}", {})
            ident = str(item.get("id", "") or "").strip() if isinstance(item, dict) else ""
            value_type = item.get("value_type", "analog") if isinstance(item, dict) else "analog"
            if not ident:
                continue
            value = _pct_to_bios(percent) if value_type == "analog" else percent
            entries.append({"label": f"{labels[target]} {percent}%", "id": ident, "value": value})
        return entries

    def _cold_apply_display_brightness(self):
        entries = self._cold_display_brightness_entries()
        mode = str(getattr(self, "_cold_display_mode", "day") or "day").upper()
        self._cold_display_brightness_applied = False
        self._cold_last_action = f"BRIGHTNESS {mode} APPLYING"
        self._cold_step_detail = "Sending display commands in sequence."
        self._cold_refresh_ui()
        if not entries:
            self._cold_last_action = f"BRIGHTNESS {mode}: NO COMMANDS"
            self._cold_display_brightness_applied = True
            self._cold_refresh_ui()
            return

        results = []
        token = getattr(self, "_cold_sequence_token", 0)

        def _send_one(index: int):
            if token != getattr(self, "_cold_sequence_token", 0):
                return
            if index >= len(entries):
                self._cold_display_brightness_applied = True
                self._cold_last_action = f"BRIGHTNESS {mode}: " + " / ".join(results)
                self._cold_step_detail = "Display brightness preset applied."
                self._cold_log(self._cold_last_action)
                self._cold_refresh_ui()
                return
            entry = entries[index]
            ident = str(entry["id"]).strip()
            value = entry["value"]
            ok = dcs_bios.send_dcs_bios(ident, value)
            result = f"{entry['label']} {'OK' if ok else 'FAIL'}"
            results.append(result)
            self._cold_last_action = f"BRIGHTNESS {mode}: {result}"
            self._cold_log(f"brightness: {ident} {value} {'OK' if ok else 'FAIL'}")
            self._cold_refresh_ui()
            QTimer.singleShot(BRIGHTNESS_SEND_INTERVAL_MS, lambda: _send_one(index + 1))

        QTimer.singleShot(0, lambda: _send_one(0))

    def _cold_current_step_text(self):
        idx = int(getattr(self, "_cold_step_index", -1))
        steps = self._cold_step_list()
        if 0 <= idx < len(steps):
            title = steps[idx][0]
            hint = steps[idx][3] if len(steps[idx]) >= 4 else ""
            return title, hint
        return "COLD START READY", "Press START twice to arm and run."

    def _cold_enter_checklist(self, reason: str = "ENTRY CONFIRMED") -> None:
        preserve_progress = bool(getattr(self, "_cold_setup_preserve_progress", False))
        if preserve_progress:
            self._cold_setup_preserve_progress = False
            self._cold_entry_stage = ENTRY_CHECKLIST
            self._cold_entry_confirm_count = 0
            title, hint = self._cold_current_step_text()
            self._cold_last_action = title
            state = getattr(self, "_cold_state", "idle")
            if state == "paused":
                self._cold_exec_phase = "PAUSED"
                self._cold_step_detail = f"Setup updated. Press START to resume. {hint}".strip()
            elif state in ("wait_user", "select_display"):
                self._cold_exec_phase = "USER"
                self._cold_step_detail = hint or "Setup updated. Press START to continue."
            elif state == "complete":
                self._cold_exec_phase = "DONE"
                self._cold_last_action = "COMPLETE"
                self._cold_step_detail = "Setup updated. Checklist was already complete."
            else:
                self._cold_exec_phase = "READY"
                self._cold_step_detail = hint or "Setup updated. Press START to continue."
            return
        self._cold_reset_progress(reason)
        self._cold_entry_stage = ENTRY_CHECKLIST
        self._cold_entry_confirm_count = 0
        self._cold_exec_phase = "READY"
        self._cold_last_action = "COLD START READY"
        self._cold_step_detail = "Press START twice to arm and run."

    def _cold_arm_or_continue(self):
        if self._cold_confirm_setup_or_continue():
            return
        if self._cold_state == "complete":
            self._cold_log("COMPLETE -> LOCAL ICP")
            self._show_page("local_icp")
            return
        if self._cold_state in ("idle", "aborted"):
            if not self._cold_all_known_below_threshold():
                self._cold_enter_hold("ENGINE RPM NOT COLD")
                return
            self._cold_reset_progress("ARM")
            self._cold_entry_stage = ENTRY_CHECKLIST
            self._cold_state = "armed"
            self._cold_exec_phase = "ARMED"
            self._cold_last_action = "ARMED"
            self._cold_step_detail = "Press START again."
            self._cold_log(f"ARMED COLD L={self._cold_left_rpm} R={self._cold_right_rpm}")
            self._cold_refresh_ui()
            return
        if self._cold_state == "armed":
            self._cold_state = "running"
            self._cold_step_index = 0
            self._cold_exec_phase = "EXEC"
            self._cold_log("RUN COLD START")
            self._cold_run_next_step()
            return
        if self._cold_state in ("paused", "hold"):
            was_hold = self._cold_state == "hold"
            self._cold_state = "running"
            self._cold_exec_phase = "EXEC"
            if was_hold:
                self._cold_step_index += 1
            self._cold_log("CONTINUE")
            self._cold_run_next_step()
            return
        if self._cold_state in ("wait_user", "select_display"):
            self._cold_state = "running"
            self._cold_exec_phase = "EXEC"
            self._cold_log("USER CONFIRM")
            self._cold_step_index += 1
            self._cold_run_next_step()
            return

    def _cold_refresh_ui(self):
        cells = getattr(self, "_cold_status_cells", {})
        if not cells:
            return
        lines = self._cold_status_lines()
        for key, text in lines.items():
            self._cold_set_cell(key, text)

        is_page = getattr(self, "_current_page", None) == PAGE
        in_setup = getattr(self, "_cold_entry_stage", ENTRY_SETUP) != ENTRY_CHECKLIST
        waiting_for_rpm = self._cold_detected_mode == "unknown" and not getattr(self, "_cold_first_mode_decided", False)
        for pos in (P_DAY, P_NIGHT, P_LAND, P_CV):
            cell = getattr(self, "_cold_cells", {}).get(pos)
            if cell:
                cell.setVisible(is_page and in_setup and not waiting_for_rpm)
        reset = getattr(self, "_cold_cells", {}).get(P_RESET)
        if reset:
            reset.setVisible(is_page and not in_setup and not waiting_for_rpm)
        start = getattr(self, "_cold_cells", {}).get(P_START)
        if start:
            start.setVisible(is_page and not waiting_for_rpm)
            start.setText("COMPLETE" if getattr(self, "_cold_state", None) == "complete" else "START")

    def _cold_entries_from_config(self, key: str):
        entries = previous_entries_from_config(self, key)
        if key == "battery_on":
            for entry in entries:
                if str(entry.get("id", "")).strip() == "BATTERY_SW":
                    entry["value"] = 2
        elif key == "ejection_seat_arm":
            return [{"id": "EJECTION_SEAT_ARMED", "value": 1, "delay_ms": 250}]
        elif key == "canopy_close":
            return [
                {"id": "CANOPY_SW", "value": 0, "delay_ms": 6500},
                {"id": "CANOPY_SW", "value": 1, "delay_ms": 100},
            ]
        elif key == "ecm_receive":
            return [{"id": "ECM_MODE_SW", "value": 1, "delay_ms": 500}]
        elif key == "rwr_power_on":
            return [
                {"id": "RWR_POWER_BTN", "value": 1, "delay_ms": 120},
                {"id": "RWR_POWER_BTN", "value": 0, "delay_ms": 120},
            ]
        elif key == "fcs_reset_rwr_power":
            return [
                {"id": "FCS_RESET_BTN", "value": 1, "delay_ms": 80},
                {"id": "FCS_RESET_BTN", "value": 0, "delay_ms": 120},
                {"id": "RWR_POWER_BTN", "value": 1, "delay_ms": 120},
                {"id": "RWR_POWER_BTN", "value": 0, "delay_ms": 120},
            ]
        return entries

    UFCKeypadWindowClass._cold_label_style = _cold_label_style
    UFCKeypadWindowClass._cold_plain_label = _cold_plain_label
    UFCKeypadWindowClass._init_cold_start_page = _init_cold_start_page
    UFCKeypadWindowClass._cold_set_cell = _cold_set_cell
    UFCKeypadWindowClass._cold_step_list = _cold_step_list
    UFCKeypadWindowClass._cold_display_brightness_entries = _cold_display_brightness_entries
    UFCKeypadWindowClass._cold_apply_display_brightness = _cold_apply_display_brightness
    UFCKeypadWindowClass._cold_enter_checklist = _cold_enter_checklist
    UFCKeypadWindowClass._cold_current_step_text = _cold_current_step_text
    UFCKeypadWindowClass._cold_arm_or_continue = _cold_arm_or_continue
    UFCKeypadWindowClass._cold_refresh_ui = _cold_refresh_ui
    UFCKeypadWindowClass._cold_entries_from_config = _cold_entries_from_config
