# -*- coding: utf-8 -*-
"""Cold-start UI polish and safety fixups.

Installed after the cold-start setup patches.  This module keeps the no-frame
text requirement while making the cold pages match the main UFC keypad style:
- plain labels use the same green brightness-driven color family as UFCCell;
- setup buttons are centered as DAY / NIGHT / LAND / CV;
- returning from RESET setup preserves the current step number and restores the
  actual checklist step title instead of showing CONFIRM SETUP;
- stale BATTERY_SW=0 configs are corrected to BATTERY_SW=2 for battery ON;
- stale canopy / ECM configs are corrected to the observed DCS-BIOS state order;
- DISPLAY BRIGHTNESS is executed immediately after APU OFF.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QLabel

import ufc.colors as colors
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
        """Authoritative 21-step checklist with brightness after APU OFF."""
        return [
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
            ("APU OFF", "apu_off", "apu_off", "Auto command."),
            ("BRIGHTNESS", "display_brightness", "", "Apply selected DAY/NIGHT preset."),
            ("CANOPY CLOSE", "supervised", "canopy_close", "Program executes; monitor cockpit."),
            ("BLEED AIR", "supervised", "bleed_air_cycle", "Program executes; monitor cockpit."),
            ("TRIM RESET", "supervised", "trim_reset", "Program executes; monitor cockpit."),
            ("FCS RESET", "supervised", "fcs_reset", "Program executes; monitor cockpit."),
            ("ECM REC", "supervised", "ecm_receive", "Program executes; monitor cockpit."),
            ("IFF MANUAL", "user", "", "Open IFF manually, then START."),
            ("LOCAL ICP", "unlock", "", "Verify LOCAL ICP ready."),
            ("INS", "ins", "", "Set selected LAND/CV profile."),
            ("COMPLETE", "complete", "", "Done."),
        ]

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

    def _cold_entries_from_config(self, key: str):
        entries = previous_entries_from_config(self, key)
        if key == "battery_on":
            for entry in entries:
                if str(entry.get("id", "")).strip() == "BATTERY_SW":
                    entry["value"] = 2
        elif key == "canopy_close":
            return [
                {"id": "CANOPY_SW", "value": 0, "delay_ms": 6500},
                {"id": "CANOPY_SW", "value": 1, "delay_ms": 100},
            ]
        elif key == "ecm_receive":
            return [{"id": "ECM_MODE_SW", "value": 3, "delay_ms": 500}]
        return entries

    UFCKeypadWindowClass._cold_label_style = _cold_label_style
    UFCKeypadWindowClass._cold_plain_label = _cold_plain_label
    UFCKeypadWindowClass._init_cold_start_page = _init_cold_start_page
    UFCKeypadWindowClass._cold_set_cell = _cold_set_cell
    UFCKeypadWindowClass._cold_step_list = _cold_step_list
    UFCKeypadWindowClass._cold_enter_checklist = _cold_enter_checklist
    UFCKeypadWindowClass._cold_current_step_text = _cold_current_step_text
    UFCKeypadWindowClass._cold_entries_from_config = _cold_entries_from_config
