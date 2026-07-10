# -*- coding: utf-8 -*-
"""Automatic post-engine lighting and LAND/CV anti-skid setup."""
from __future__ import annotations

from typing import Any, Dict, List

from ufc.cold_direct_entry import PAGE

P_LIGHT_NO = (91, 0)
P_LIGHT_YES = (91, 2)

LIGHT_BRIGHTNESS_PERCENT = 70
LIGHT_BRIGHTNESS_VALUE = (LIGHT_BRIGHTNESS_PERCENT * 65535 + 50) // 100


def install_cold_lighting_automation(UFCKeypadWindowClass) -> None:
    if getattr(UFCKeypadWindowClass, "_cold_lighting_automation_installed", False):
        return
    UFCKeypadWindowClass._cold_lighting_automation_installed = True

    previous_init_page = UFCKeypadWindowClass._init_cold_start_page
    previous_step_list = UFCKeypadWindowClass._cold_step_list
    previous_run_next_step = UFCKeypadWindowClass._cold_run_next_step
    previous_handle_click = UFCKeypadWindowClass._cold_handle_click
    previous_arm_or_continue = UFCKeypadWindowClass._cold_arm_or_continue
    previous_refresh_ui = UFCKeypadWindowClass._cold_refresh_ui

    def _init_cold_start_page(self) -> None:
        previous_init_page(self)
        no_cell = self.place_cell(
            "NO", P_LIGHT_NO, 216, 430, 160, 58,
            font_size=22, register=False, page=PAGE, bold=True,
        )
        question_cell = self.place_cell(
            "", None, 392, 430, 240, 58,
            font_size=13, is_variable=True, register=False,
            no_feedback=True, page=PAGE, bold=True,
        )
        yes_cell = self.place_cell(
            "YES", P_LIGHT_YES, 648, 430, 160, 58,
            font_size=22, register=False, page=PAGE, bold=True,
        )
        self._cold_lighting_cells = {
            "no": no_cell,
            "question": question_cell,
            "yes": yes_cell,
        }
        for cell in self._cold_lighting_cells.values():
            cell.setVisible(False)

    def _cold_step_list(self):
        steps = []
        inserted = False
        for step in previous_step_list(self):
            steps.append(step)
            if step[0] == "LEFT STABLE?":
                steps.append((
                    "LIGHTS / ANTI-SKID",
                    "lighting_setup",
                    "",
                    "Apply DAY/NIGHT lighting and LAND/CV anti-skid settings.",
                ))
                inserted = True
        if not inserted:
            raise RuntimeError("LEFT STABLE? step not found for lighting insertion")
        return steps

    def _cold_lighting_entries(
        self,
        display_mode: str | None = None,
        profile: str | None = None,
        flood_enabled: bool = False,
        chart_enabled: bool = False,
    ) -> List[Dict[str, Any]]:
        mode = str(display_mode or getattr(self, "_cold_display_mode", "day")).lower()
        active_profile = str(profile or getattr(self, "_cold_profile", "land")).lower()
        anti_skid = 0 if active_profile == "carrier" else 1
        entries: List[Dict[str, Any]] = [
            {"id": "STROBE_SW", "value": 0, "delay_ms": 120},
        ]
        if mode == "night":
            entries.extend([
                {"id": "LDG_TAXI_SW", "value": 1, "delay_ms": 120},
                {"id": "FORMATION_DIMMER", "value": LIGHT_BRIGHTNESS_VALUE, "delay_ms": 120},
                {"id": "POSITION_DIMMER", "value": LIGHT_BRIGHTNESS_VALUE, "delay_ms": 120},
                {"id": "CONSOLES_DIMMER", "value": LIGHT_BRIGHTNESS_VALUE, "delay_ms": 120},
                {"id": "INST_PNL_DIMMER", "value": LIGHT_BRIGHTNESS_VALUE, "delay_ms": 120},
                {"id": "WARN_CAUTION_DIMMER", "value": LIGHT_BRIGHTNESS_VALUE, "delay_ms": 120},
                {"id": "COCKKPIT_LIGHT_MODE_SW", "value": 1, "delay_ms": 120},
                {"id": "FLOOD_DIMMER", "value": LIGHT_BRIGHTNESS_VALUE if flood_enabled else 0, "delay_ms": 120},
                {"id": "CHART_DIMMER", "value": LIGHT_BRIGHTNESS_VALUE if chart_enabled else 0, "delay_ms": 120},
            ])
        entries.append({"id": "ANTI_SKID_SW", "value": anti_skid, "delay_ms": 120})
        return entries

    def _cold_lighting_context_valid(self) -> bool:
        phase = getattr(self, "_cold_lighting_phase", "")
        steps = self._cold_step_list()
        index = int(getattr(self, "_cold_step_index", -1))
        kind = steps[index][1] if 0 <= index < len(steps) else ""
        return (
            getattr(self, "_cold_state", None) == "wait_user"
            and getattr(self, "_current_page", None) == PAGE
            and phase in ("ask_flood", "ask_chart")
            and kind == "lighting_setup"
            and getattr(self, "_cold_lighting_step_index", None) == index
            and getattr(self, "_cold_lighting_token", None) == getattr(self, "_cold_sequence_token", None)
        )

    def _cold_apply_lighting_entries(self) -> None:
        token = int(getattr(self, "_cold_lighting_token", getattr(self, "_cold_sequence_token", 0)))
        step_index = int(getattr(self, "_cold_lighting_step_index", getattr(self, "_cold_step_index", -1)))
        self._cold_state = "running"
        self._cold_exec_phase = "AUTO"
        self._cold_lighting_phase = "applying"
        self._cold_last_action = "LIGHTS / ANTI-SKID"
        self._cold_step_detail = "Applying the selected lighting and anti-skid settings."
        self._cold_refresh_ui()
        entries = self._cold_lighting_entries(
            flood_enabled=bool(getattr(self, "_cold_lighting_flood", False)),
            chart_enabled=bool(getattr(self, "_cold_lighting_chart", False)),
        )

        def done() -> None:
            if (
                token == getattr(self, "_cold_sequence_token", None)
                and step_index == getattr(self, "_cold_step_index", None)
                and getattr(self, "_cold_state", None) == "running"
            ):
                self._cold_lighting_phase = ""
                self._cold_step_index += 1
                self._cold_run_next_step()

        self._cold_run_sequence_entries("lighting_setup", entries, 0, token, done)

    def _cold_run_lighting_setup(self) -> None:
        self._cold_lighting_step_index = self._cold_step_index
        self._cold_lighting_token = self._cold_sequence_token
        self._cold_lighting_flood = False
        self._cold_lighting_chart = False
        if str(getattr(self, "_cold_display_mode", "day")).lower() != "night":
            self._cold_apply_lighting_entries()
            return
        self._cold_state = "wait_user"
        self._cold_exec_phase = "SELECT"
        self._cold_lighting_phase = "ask_flood"
        self._cold_last_action = "FLOOD LIGHT?"
        self._cold_step_detail = "Select YES for 70% flood lighting, or NO to keep it off."
        self._cold_refresh_ui()

    def _cold_handle_lighting_choice(self, enabled: bool) -> None:
        if not self._cold_lighting_context_valid():
            return
        if self._cold_lighting_phase == "ask_flood":
            self._cold_lighting_flood = bool(enabled)
            self._cold_lighting_phase = "ask_chart"
            self._cold_last_action = "CHART LIGHT?"
            self._cold_step_detail = "Select YES for 70% chart lighting, or NO to keep it off."
            self._cold_refresh_ui()
            return
        self._cold_lighting_chart = bool(enabled)
        self._cold_apply_lighting_entries()

    def _cold_handle_click(self, pos) -> None:
        if pos in (P_LIGHT_NO, P_LIGHT_YES) and self._cold_lighting_context_valid():
            self._cold_handle_lighting_choice(pos == P_LIGHT_YES)
            return
        previous_handle_click(self, pos)

    def _cold_arm_or_continue(self) -> None:
        if self._cold_lighting_context_valid():
            self._cold_last_action = "SELECT LIGHT OPTION"
            self._cold_step_detail = "Use the on-screen NO / YES buttons before continuing."
            self._cold_refresh_ui()
            return
        previous_arm_or_continue(self)

    def _cold_refresh_ui(self) -> None:
        previous_refresh_ui(self)
        cells = getattr(self, "_cold_lighting_cells", {})
        visible = self._cold_lighting_context_valid()
        for cell in cells.values():
            cell.setVisible(visible)
        if visible and cells.get("question"):
            label = "FLOOD LIGHT?" if self._cold_lighting_phase == "ask_flood" else "CHART LIGHT?"
            cells["question"].setText(label)

    def _cold_run_next_step(self) -> None:
        if getattr(self, "_cold_state", None) == "running":
            steps = self._cold_step_list()
            index = int(getattr(self, "_cold_step_index", -1))
            if 0 <= index < len(steps) and steps[index][1] == "lighting_setup":
                self._cold_total_steps = len(steps)
                self._cold_run_lighting_setup()
                return
        previous_run_next_step(self)

    UFCKeypadWindowClass._init_cold_start_page = _init_cold_start_page
    UFCKeypadWindowClass._cold_step_list = _cold_step_list
    UFCKeypadWindowClass._cold_lighting_entries = _cold_lighting_entries
    UFCKeypadWindowClass._cold_lighting_context_valid = _cold_lighting_context_valid
    UFCKeypadWindowClass._cold_apply_lighting_entries = _cold_apply_lighting_entries
    UFCKeypadWindowClass._cold_run_lighting_setup = _cold_run_lighting_setup
    UFCKeypadWindowClass._cold_handle_lighting_choice = _cold_handle_lighting_choice
    UFCKeypadWindowClass._cold_handle_click = _cold_handle_click
    UFCKeypadWindowClass._cold_arm_or_continue = _cold_arm_or_continue
    UFCKeypadWindowClass._cold_refresh_ui = _cold_refresh_ui
    UFCKeypadWindowClass._cold_run_next_step = _cold_run_next_step
