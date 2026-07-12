# -*- coding: utf-8 -*-
"""Virtual flash modes for the three normally steady external lights.

LIGHT CONTROL keeps the aircraft's real STROBE switch unchanged, but extends:
- LDG/TAXI: OFF, ON, FLASH DIM, FLASH BRI
- FORMATION: 0..100, FLASH DIM, FLASH BRI
- POSITION: 0..100, FLASH DIM, FLASH BRI

The option lists are clamped at both ends and never wrap around.
"""
from __future__ import annotations

import time
from typing import Dict

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QGraphicsOpacityEffect

from ufc.constants import DCS_FORM, DCS_LDG_TAXI, DCS_POSITION
from ufc.dcs_bios import send_dcs_bios


STEADY = "steady"
FLASH_DIM = "flash_dim"
FLASH_BRI = "flash_bri"

FLASH_TICK_MS = 50
FLASH_PERIOD_MS = 1000
LDG_DIM_ON_MS = 150
LDG_BRI_ON_MS = 500
DIMMER_ON_MS = 500
DIMMER_FLASH_DIM_VALUE = int(round(65535 * 0.30))
DIMMER_FLASH_BRI_VALUE = 65535
DIMMER_LEVELS = tuple(int(round(65535 * step / 10.0)) for step in range(11))

_EFFECT_KEYS = ("ldg", "form", "pos")
_FIELD_TO_KEY = {
    "ldg_taxi_sw": "ldg",
    "formation_dimmer": "form",
    "position_dimmer": "pos",
}
_KEY_TO_DCS = {
    "ldg": DCS_LDG_TAXI,
    "form": DCS_FORM,
    "pos": DCS_POSITION,
}


def clamp_option_index(index: int, delta: int, maximum: int) -> int:
    """Move one option left/right without wrapping at either boundary."""
    return max(0, min(int(maximum), int(index) + int(delta)))


def _nearest_dimmer_index(raw: int) -> int:
    value = max(0, min(65535, int(raw)))
    return max(0, min(10, int(round(value / 65535.0 * 10.0))))


def install_light_flash_modes(UFCKeypadWindowClass) -> None:
    """Extend LIGHT CONTROL with non-cycling virtual flash states."""
    if getattr(UFCKeypadWindowClass, "_light_flash_modes_installed", False):
        return
    UFCKeypadWindowClass._light_flash_modes_installed = True

    previous_init_light_control = UFCKeypadWindowClass._init_light_control
    previous_update_light_display = UFCKeypadWindowClass._update_light_display
    previous_update_display = UFCKeypadWindowClass._update_display
    previous_refresh_from_dcs = UFCKeypadWindowClass._refresh_from_dcs
    previous_light_button = UFCKeypadWindowClass._light_button
    previous_light_preset = UFCKeypadWindowClass._light_preset
    previous_show_page = UFCKeypadWindowClass._show_page
    previous_check_dcs_timeout = UFCKeypadWindowClass._check_dcs_timeout
    previous_close_event = UFCKeypadWindowClass.closeEvent
    previous_cold_apply_lighting = getattr(UFCKeypadWindowClass, "_cold_apply_lighting_entries", None)
    previous_cold_reset_session = getattr(UFCKeypadWindowClass, "_cold_reset_session_state", None)

    def _init_light_control(self) -> None:
        self._light_effect_modes = {key: STEADY for key in _EFFECT_KEYS}
        self._light_steady_state = {
            "ldg": int(getattr(self, "_light_state", {}).get("ldg", 0)),
            "form": int(getattr(self, "_light_state", {}).get("form", 0)),
            "pos": int(getattr(self, "_light_state", {}).get("pos", 0)),
        }
        self._light_flash_last_output = {key: None for key in _EFFECT_KEYS}
        self._light_flash_epoch = time.monotonic()
        self._light_flash_timer = QTimer(self)
        self._light_flash_timer.setInterval(FLASH_TICK_MS)
        self._light_flash_timer.timeout.connect(self._light_flash_tick)
        self._light_arrow_cells = {}

        previous_init_light_control(self)

        for widget, *_ in getattr(self, "_widget_origins", []):
            if getattr(widget, "_page", None) != "light_control":
                continue
            pos = getattr(widget, "pos", None)
            if (
                isinstance(pos, tuple)
                and len(pos) == 2
                and pos[0] in (32, 33)
                and 0 <= int(pos[1]) <= 3
            ):
                direction = "left" if pos[0] == 32 else "right"
                self._light_arrow_cells[(int(pos[1]), direction)] = widget

        for key in ("ldg", "form", "pos", "strobe"):
            self._update_light_display(key)

    def _light_effect_mode(self, key: str) -> str:
        return str(getattr(self, "_light_effect_modes", {}).get(key, STEADY))

    def _light_option_index(self, key: str) -> int:
        if key in _EFFECT_KEYS:
            mode = self._light_effect_mode(key)
            if key == "ldg":
                if mode == FLASH_DIM:
                    return 2
                if mode == FLASH_BRI:
                    return 3
                return 1 if int(getattr(self, "_light_steady_state", {}).get("ldg", 0)) else 0
            if mode == FLASH_DIM:
                return 11
            if mode == FLASH_BRI:
                return 12
            return _nearest_dimmer_index(
                int(getattr(self, "_light_steady_state", {}).get(key, 0))
            )

        if key == "strobe":
            return {1: 0, 2: 1, 0: 2}.get(
                int(getattr(self, "_light_state", {}).get("strobe", 1)),
                0,
            )
        return 0

    def _light_option_max(self, key: str) -> int:
        if key == "ldg":
            return 3
        if key in ("form", "pos"):
            return 12
        if key == "strobe":
            return 2
        return 0

    def _set_arrow_opacity(self, cell, enabled: bool) -> None:
        if cell is None:
            return
        enabled = bool(enabled)
        cell.setEnabled(enabled)
        opacity = 1.0 if enabled else 0.32
        if getattr(cell, "_light_boundary_opacity", None) == opacity:
            return
        effect = cell.graphicsEffect()
        if not isinstance(effect, QGraphicsOpacityEffect):
            effect = QGraphicsOpacityEffect(cell)
            cell.setGraphicsEffect(effect)
        effect.setOpacity(opacity)
        cell._light_boundary_opacity = opacity

    def _light_update_arrow_states(self, key: str) -> None:
        row_map = {"ldg": 0, "form": 1, "pos": 2, "strobe": 3}
        row = row_map.get(key)
        if row is None:
            return
        index = self._light_option_index(key)
        maximum = self._light_option_max(key)
        self._set_arrow_opacity(
            getattr(self, "_light_arrow_cells", {}).get((row, "left")),
            index > 0,
        )
        self._set_arrow_opacity(
            getattr(self, "_light_arrow_cells", {}).get((row, "right")),
            index < maximum,
        )

    def _light_any_flash_active(self) -> bool:
        return any(self._light_effect_mode(key) != STEADY for key in _EFFECT_KEYS)

    def _light_stop_timer_if_idle(self) -> None:
        if self._light_any_flash_active():
            return
        timer = getattr(self, "_light_flash_timer", None)
        if timer is not None:
            timer.stop()
        for key in _EFFECT_KEYS:
            self._light_flash_last_output[key] = None

    def _light_send_value(self, key: str, value: int) -> None:
        value = int(value)
        self._light_last_local[key] = time.time()
        self._light_state[key] = value
        send_dcs_bios(_KEY_TO_DCS[key], value)

    def _light_set_steady(self, key: str, value: int, *, send: bool = True) -> None:
        if key == "ldg":
            value = 1 if int(value) else 0
        else:
            value = max(0, min(65535, int(value)))
        self._light_effect_modes[key] = STEADY
        self._light_steady_state[key] = value
        self._light_flash_last_output[key] = None
        self._light_state[key] = value
        if send:
            self._light_send_value(key, value)
        self._light_stop_timer_if_idle()
        self._update_light_display(key)

    def _light_set_effect(self, key: str, mode: str) -> None:
        if mode not in (FLASH_DIM, FLASH_BRI):
            return
        if self._light_effect_mode(key) == STEADY:
            current = int(getattr(self, "_light_state", {}).get(key, 0))
            if key == "ldg":
                current = 1 if current else 0
            else:
                current = max(0, min(65535, current))
            self._light_steady_state[key] = current
        self._light_effect_modes[key] = mode
        self._light_flash_last_output[key] = None
        timer = getattr(self, "_light_flash_timer", None)
        if timer is not None and not timer.isActive():
            self._light_flash_epoch = time.monotonic()
            timer.start()
        self._light_flash_tick()
        self._update_light_display(key)

    def _light_flash_tick(self) -> None:
        if getattr(self, "_dcs_disconnected", False):
            timer = getattr(self, "_light_flash_timer", None)
            if timer is not None:
                timer.stop()
            return

        phase_ms = int((time.monotonic() - self._light_flash_epoch) * 1000.0) % FLASH_PERIOD_MS
        for key in _EFFECT_KEYS:
            mode = self._light_effect_mode(key)
            if mode == STEADY:
                continue
            if key == "ldg":
                on_ms = LDG_DIM_ON_MS if mode == FLASH_DIM else LDG_BRI_ON_MS
                value = 1 if phase_ms < on_ms else 0
            else:
                if phase_ms < DIMMER_ON_MS:
                    value = DIMMER_FLASH_DIM_VALUE if mode == FLASH_DIM else DIMMER_FLASH_BRI_VALUE
                else:
                    value = 0
            if self._light_flash_last_output.get(key) == value:
                continue
            self._light_flash_last_output[key] = value
            self._light_send_value(key, value)

    def _light_cancel_all_flash(self, *, restore: bool) -> None:
        active = [key for key in _EFFECT_KEYS if self._light_effect_mode(key) != STEADY]
        for key in active:
            value = int(getattr(self, "_light_steady_state", {}).get(key, 0))
            self._light_effect_modes[key] = STEADY
            self._light_flash_last_output[key] = None
            self._light_state[key] = value
            if restore and not getattr(self, "_dcs_disconnected", False):
                self._light_send_value(key, value)
            self._update_light_display(key)
        self._light_stop_timer_if_idle()

    def _update_light_display(self, key):
        cell = getattr(self, "_light_displays", {}).get(key)
        if key in _EFFECT_KEYS and cell is not None:
            mode = self._light_effect_mode(key)
            if mode == FLASH_DIM:
                cell._var_text = "FLASH\nDIM"
            elif mode == FLASH_BRI:
                cell._var_text = "FLASH\nBRI"
            elif key == "ldg":
                cell._var_text = "ON" if int(self._light_steady_state.get("ldg", 0)) else "OFF"
            else:
                level = _nearest_dimmer_index(int(self._light_steady_state.get(key, 0))) * 10
                cell._var_text = str(level)
            cell.update()
            self._light_update_arrow_states(key)
            return

        previous_update_light_display(self, key)
        if key == "strobe":
            self._light_update_arrow_states(key)

    def _light_button(self, light_key, direction):
        if light_key not in _EFFECT_KEYS:
            previous_light_button(self, light_key, direction)
            return

        delta = 1 if direction == "up" else -1
        current = self._light_option_index(light_key)
        maximum = self._light_option_max(light_key)
        target = clamp_option_index(current, delta, maximum)
        if target == current:
            self._light_update_arrow_states(light_key)
            return

        if light_key == "ldg":
            if target <= 1:
                self._light_set_steady("ldg", target)
            elif target == 2:
                self._light_set_effect("ldg", FLASH_DIM)
            else:
                self._light_set_effect("ldg", FLASH_BRI)
            return

        if target <= 10:
            self._light_set_steady(light_key, DIMMER_LEVELS[target])
        elif target == 11:
            self._light_set_effect(light_key, FLASH_DIM)
        else:
            self._light_set_effect(light_key, FLASH_BRI)

    def _update_display(self, field_name, value):
        previous_update_display(self, field_name, value)
        key = _FIELD_TO_KEY.get(str(field_name))
        if key is None:
            return
        if self._light_effect_mode(key) == STEADY:
            current = int(getattr(self, "_light_state", {}).get(key, 0))
            if key == "ldg":
                current = 1 if current else 0
            self._light_steady_state[key] = current
        self._update_light_display(key)

    def _refresh_from_dcs(self):
        previous_refresh_from_dcs(self)
        for key in _EFFECT_KEYS:
            if self._light_effect_mode(key) == STEADY:
                current = int(getattr(self, "_light_state", {}).get(key, 0))
                if key == "ldg":
                    current = 1 if current else 0
                self._light_steady_state[key] = current
            self._update_light_display(key)
        self._update_light_display("strobe")

    def _light_preset(self, config: Dict[str, int]):
        self._light_cancel_all_flash(restore=False)
        previous_light_preset(self, config)
        for key in _EFFECT_KEYS:
            if key not in config:
                continue
            value = int(config[key])
            if key == "ldg":
                value = 1 if value else 0
            else:
                value = max(0, min(65535, value))
            self._light_steady_state[key] = value
            self._light_effect_modes[key] = STEADY
            self._update_light_display(key)

    def _show_page(self, page_name):
        if page_name == "morse_light" and self._light_effect_mode("form") != STEADY:
            self._light_set_steady(
                "form",
                int(getattr(self, "_light_steady_state", {}).get("form", 0)),
            )
        previous_show_page(self, page_name)

    def _check_dcs_timeout(self):
        previous_check_dcs_timeout(self)
        if getattr(self, "_dcs_disconnected", False):
            self._light_cancel_all_flash(restore=False)

    def _cold_apply_lighting_entries(self):
        self._light_cancel_all_flash(restore=False)
        return previous_cold_apply_lighting(self)

    def _cold_reset_session_state(self, reason: str):
        self._light_cancel_all_flash(restore=False)
        return previous_cold_reset_session(self, reason)

    def closeEvent(self, event):
        timer = getattr(self, "_light_flash_timer", None)
        if timer is not None:
            timer.stop()
        previous_close_event(self, event)

    UFCKeypadWindowClass._init_light_control = _init_light_control
    UFCKeypadWindowClass._light_effect_mode = _light_effect_mode
    UFCKeypadWindowClass._light_option_index = _light_option_index
    UFCKeypadWindowClass._light_option_max = _light_option_max
    UFCKeypadWindowClass._set_arrow_opacity = _set_arrow_opacity
    UFCKeypadWindowClass._light_update_arrow_states = _light_update_arrow_states
    UFCKeypadWindowClass._light_any_flash_active = _light_any_flash_active
    UFCKeypadWindowClass._light_stop_timer_if_idle = _light_stop_timer_if_idle
    UFCKeypadWindowClass._light_send_value = _light_send_value
    UFCKeypadWindowClass._light_set_steady = _light_set_steady
    UFCKeypadWindowClass._light_set_effect = _light_set_effect
    UFCKeypadWindowClass._light_flash_tick = _light_flash_tick
    UFCKeypadWindowClass._light_cancel_all_flash = _light_cancel_all_flash
    UFCKeypadWindowClass._update_light_display = _update_light_display
    UFCKeypadWindowClass._light_button = _light_button
    UFCKeypadWindowClass._update_display = _update_display
    UFCKeypadWindowClass._refresh_from_dcs = _refresh_from_dcs
    UFCKeypadWindowClass._light_preset = _light_preset
    UFCKeypadWindowClass._show_page = _show_page
    UFCKeypadWindowClass._check_dcs_timeout = _check_dcs_timeout
    UFCKeypadWindowClass.closeEvent = closeEvent

    if previous_cold_apply_lighting is not None:
        UFCKeypadWindowClass._cold_apply_lighting_entries = _cold_apply_lighting_entries
    if previous_cold_reset_session is not None:
        UFCKeypadWindowClass._cold_reset_session_state = _cold_reset_session_state
