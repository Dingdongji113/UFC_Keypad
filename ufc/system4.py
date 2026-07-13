# -*- coding: utf-8 -*-
"""SYSTEM 4A HUD/NAV and SYSTEM 4B EW/JETT integration."""
from __future__ import annotations

import time
from typing import Callable

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QFrame, QLabel

import ufc.dcs_bios as dcs_bios
from ufc.system4_mapping import (
    CONTROLS, FEEDBACK_FIELDS, analog_feedback_fields, integer_feedback_fields,
)
from ufc.system4_safety import System4Safety
from ufc.system4_widgets import (
    AnalogKnob, CutCornerFrame, DetentRotary, GuardedHoldButton, PushButton,
    SpringThreePositionToggle, ThreePositionToggle, TouchButton, TwoPositionToggle,
)


PAGE_4A = "system4a"
PAGE_4B = "system4b"
SYSTEM4_PAGES = (PAGE_4A, PAGE_4B)

FRAME_STYLE = "QFrame { background:#020604; border:2px solid #53615a; }"
TITLE_STYLE = "color:#00e65c; background:#020604; border:none;"
TAB_STYLE = """
QPushButton { color:#00e65c; background:#07100b; border:2px solid #087c38; }
QPushButton:checked { color:#effff4; background:#115b2e; border:2px solid #00e65c; }
QPushButton:pressed { background:#123a22; }
"""
DANGER_FRAME_STYLE = "QFrame { background:#100505; border:2px solid #9b2d2d; }"


def install_system4(UFCKeypadWindowClass) -> None:
    if getattr(UFCKeypadWindowClass, "_system4_installed", False):
        return
    UFCKeypadWindowClass._system4_installed = True

    previous_init_ui = UFCKeypadWindowClass.init_ui
    previous_init_select = UFCKeypadWindowClass._init_system_select
    previous_show_page = UFCKeypadWindowClass._show_page
    previous_cell_click = UFCKeypadWindowClass.on_cell_click
    previous_check_timeout = UFCKeypadWindowClass._check_dcs_timeout
    previous_rescale = UFCKeypadWindowClass._rescale_children
    previous_close = UFCKeypadWindowClass.closeEvent
    previous_reset = getattr(UFCKeypadWindowClass, "_cold_reset_session_state", None)

    def _system4_register(self, widget, x: int, y: int, w: int, h: int,
                          page: str, font_size: int = 10):
        widget._page = page
        widget.setGeometry(x, y, w, h)
        self._widget_origins.append((widget, x, y, w, h, font_size))
        return widget

    def _system4_label(self, text: str, x: int, y: int, w: int, h: int,
                       page: str, size: int = 10, color: str = "#00e65c"):
        label = QLabel(text, self)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setFont(QFont("B612", size, QFont.Weight.Bold))
        label.setStyleSheet(f"color:{color}; background:#020604; border:none;")
        return self._system4_register(label, x, y, w, h, page, size)

    def _system4_section(self, title: str, x: int, y: int, w: int, h: int,
                         page: str, danger: bool = False):
        frame = CutCornerFrame(danger=danger, parent=self)
        self._system4_register(frame, x, y, w, h, page, 0)
        color = "#cf3434" if danger else "#00e65c"
        self._system4_label(title, x + 16, y - 1, min(w - 32, max(140, len(title) * 12)),
                            24, page, 9, color)

    def _system4_send(self, identifier: str, value) -> bool:
        ok = dcs_bios.send_dcs_bios(identifier, value)
        ts = time.strftime("%H:%M:%S", time.localtime())
        try:
            self._key_press_log.append((ts, f"SYSTEM4:{identifier} {value} {'OK' if ok else 'FAIL'}"))
            if len(self._key_press_log) > 50:
                self._key_press_log.pop(0)
            self.keyLogUpdated.emit(ts, f"SYSTEM4:{identifier} {value}")
        except Exception:
            pass
        return ok

    def _system4_sender(self, key: str) -> Callable[[object], None]:
        identifier = CONTROLS[key].identifier
        return lambda value: self._system4_send(identifier, value)

    def _system4_status(self, text: str) -> None:
        self._system4_status_text = str(text)
        for label in getattr(self, "_system4_status_labels", {}).values():
            label.setText(self._system4_status_text)
        arm = getattr(self, "_system4_arm_button", None)
        safety = getattr(self, "_system4_safety", None)
        if arm and safety:
            arm.setChecked(safety.emer_armed)
            arm.setText("ARMED" if safety.emer_armed else "ARM")

    def _system4_add_control(self, key: str, control, geometry, page: str, font=9):
        x, y, w, h = geometry
        self._system4_controls[key] = control
        self._system4_register(control, x, y, w, h, page, font)
        return control

    def _system4_make_header(self, page: str, title: str):
        back = TouchButton("SYSTEMS", self)
        back.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        back.setStyleSheet(TAB_STYLE)
        back.clicked.connect(lambda: self._show_page("select"))
        self._system4_register(back, 8, 7, 130, 50, page, 10)
        tab_a = TouchButton("HUD / NAV", self)
        tab_b = TouchButton("EW / JETT", self)
        for tab in (tab_a, tab_b):
            tab.setCheckable(True)
            tab.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            tab.setStyleSheet(TAB_STYLE)
        tab_a.setChecked(page == PAGE_4A)
        tab_b.setChecked(page == PAGE_4B)
        tab_a.clicked.connect(lambda: self._show_page(PAGE_4A))
        tab_b.clicked.connect(lambda: self._show_page(PAGE_4B))
        self._system4_register(tab_a, 150, 7, 190, 50, page, 10)
        self._system4_register(tab_b, 350, 7, 190, 50, page, 10)
        self._system4_label(title, 550, 7, 466, 28, page, 12)
        status = self._system4_label("DCS DISCONNECTED", 550, 34, 466, 23, page, 8, "#d89a28")
        self._system4_status_labels[page] = status

    def _system4_outer_frame(self, page: str):
        frame = CutCornerFrame(double=True, parent=self)
        return self._system4_register(frame, 4, 62, 1016, 529, page, 0)

    def _init_system4(self) -> None:
        self._system4_controls = {}
        self._system4_status_labels = {}
        self._system4_feedback = {}
        self._system4_status_text = "DCS DISCONNECTED"
        self._system4_safety = System4Safety(
            lambda ident, value: self._system4_send(ident, value),
            lambda text: self._system4_status(text),
            self,
        )

        # SYSTEM 4A
        self._system4_make_header(PAGE_4A, "SYSTEM 4 · HUD / NAV")
        self._system4_outer_frame(PAGE_4A)
        self._system4_section("HUD FLIGHT", 8, 68, 1008, 172, PAGE_4A)
        self._system4_section("HUD VIDEO / LEVEL", 8, 247, 1008, 166, PAGE_4A)
        self._system4_section("ADF / HEADING / COURSE", 8, 420, 1008, 167, PAGE_4A)

        for key, cls, geom in (
            ("hud_rej", ThreePositionToggle, (18, 98, 240, 130)),
            ("hud_mode", TwoPositionToggle, (268, 98, 230, 130)),
            ("hud_alt", TwoPositionToggle, (508, 98, 230, 130)),
            ("hud_att", ThreePositionToggle, (748, 98, 258, 130)),
            ("hud_video", ThreePositionToggle, (18, 277, 188, 124)),
        ):
            spec = CONTROLS[key]
            if cls is TwoPositionToggle:
                control = cls(
                    key.replace("_", " ").upper(), spec.labels, spec.values,
                    self._system4_sender(key), self,
                    use_toggle=key in ("hud_mode", "hud_alt"),
                )
            else:
                control = cls(
                    key.replace("_", " ").upper(), spec.labels, spec.values,
                    self._system4_sender(key), self,
                )
            self._system4_add_control(
                key, control, geom, PAGE_4A,
            )
        for key, title, geom in (
            ("hud_brt", "HUD BRT", (214, 277, 188, 124)),
            ("hud_black", "BLK LVL", (410, 277, 188, 124)),
            ("hud_balance", "BAL", (606, 277, 188, 124)),
            ("hud_aoa", "AOA INDEXER", (802, 277, 204, 124)),
        ):
            self._system4_add_control(key, AnalogKnob(title, self._system4_sender(key), self), geom, PAGE_4A)

        spec = CONTROLS["adf"]
        self._system4_add_control(
            "adf", ThreePositionToggle("ADF", spec.labels, spec.values,
                                         self._system4_sender("adf"), self),
            (18, 450, 300, 124), PAGE_4A,
        )
        self._system4_add_control(
            "hdg", SpringThreePositionToggle("HDG", self._system4_sender("hdg"), parent=self),
            (326, 450, 330, 124), PAGE_4A,
        )
        self._system4_add_control(
            "crs", SpringThreePositionToggle("CRS", self._system4_sender("crs"), parent=self),
            (664, 450, 342, 124), PAGE_4A,
        )

        # SYSTEM 4B
        self._system4_make_header(PAGE_4B, "SYSTEM 4 · EW / JETT")
        self._system4_outer_frame(PAGE_4B)
        self._system4_section("ALR-67", 8, 68, 1008, 190, PAGE_4B)
        self._system4_section("ECM / CMDS", 8, 265, 650, 170, PAGE_4B)
        self._system4_section("RELEASE", 668, 265, 348, 170, PAGE_4B)
        self._system4_section("JETTISON", 8, 442, 1008, 145, PAGE_4B, True)
        for key, title, geom, press_only in (
            ("rwr_bit", "BIT", (20, 98, 188, 145), False),
            ("rwr_offset", "OFFSET", (218, 98, 188, 145), False),
            ("rwr_special", "SPECIAL", (416, 98, 188, 145), False),
            ("rwr_display", "DISPLAY", (614, 98, 188, 145), False),
            ("rwr_power", "POWER", (812, 98, 194, 145), True),
        ):
            self._system4_add_control(
                key, PushButton(title, self._system4_sender(key), press_only=press_only,
                                show_lamp=True, parent=self),
                geom, PAGE_4B,
            )
        spec = CONTROLS["ecm_mode"]
        self._system4_add_control(
            "ecm_mode", DetentRotary("ECM MODE", spec.labels, spec.values,
                                      self._system4_sender("ecm_mode"), self),
            (20, 295, 300, 125), PAGE_4B,
        )
        spec = CONTROLS["dispenser"]
        self._system4_add_control(
            "dispenser", ThreePositionToggle("DISPENSER", spec.labels, spec.values,
                                               self._system4_sender("dispenser"), self),
            (330, 295, 316, 125), PAGE_4B,
        )
        ecm_hold = GuardedHoldButton("ECM JETT", 1000, self._system4_safety.execute_ecm_jett,
                                     danger=False, parent=self)
        self._system4_ecm_hold = self._system4_add_control("ecm_jett", ecm_hold, (20, 470, 240, 105), PAGE_4B)

        def aux_select(value):
            ok = self._system4_safety.request_aux(bool(value))
            if int(value) == 1 and not ok:
                self._system4_controls["aux_rel"].set_state_index(0)

        spec = CONTROLS["aux_rel"]
        self._system4_add_control(
            "aux_rel", TwoPositionToggle("AUX REL", spec.labels, spec.values, aux_select, self),
            (680, 295, 324, 125), PAGE_4B,
        )
        arm = TouchButton("ARM", self)
        arm.setCheckable(True)
        arm.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        arm.setStyleSheet(
            "QPushButton {color:#cf3434;background:#130707;border:2px solid #9b2d2d;}"
            "QPushButton:checked {color:#fff;background:#6b1414;border:2px solid #ff4b4b;}"
        )
        arm.clicked.connect(lambda: self._system4_safety.arm_emergency()
                            if not self._system4_safety.emer_armed
                            else self._system4_safety.disarm("EMER JETT DISARMED"))
        self._system4_arm_button = self._system4_register(arm, 270, 470, 220, 105, PAGE_4B, 13)
        emer = GuardedHoldButton("EMER JETT", 1500, self._system4_safety.execute_emergency,
                                 danger=True, parent=self)
        self._system4_emer_hold = self._system4_add_control("emer_jett", emer, (500, 470, 506, 105), PAGE_4B, 11)

        self._system4_feedback_timer = QTimer(self)
        self._system4_feedback_timer.setInterval(100)
        self._system4_feedback_timer.timeout.connect(self._system4_poll_feedback)
        self._system4_feedback_timer.start()
        self._show_page("local_icp")

    def _system4_read_word(self, address: int) -> int:
        state = self.dcs_bios.parser.state
        return state[address] | (state[address + 1] << 8)

    def _system4_apply_feedback(self, field: str, value) -> None:
        old = self._system4_feedback.get(field)
        if old == value:
            return
        self._system4_feedback[field] = value
        for key, spec in CONTROLS.items():
            if spec.feedback == field and key in self._system4_controls:
                self._system4_controls[key].set_feedback(value)
        if field in ("rwr_special_lt", "rwr_special_en_lt"):
            on = max(float(self._system4_feedback.get("rwr_special_lt", 0)),
                     float(self._system4_feedback.get("rwr_special_en_lt", 0)))
            self._system4_controls["rwr_special"].set_feedback(on)

    def _system4_poll_feedback(self) -> None:
        connected = not bool(getattr(self, "_dcs_disconnected", True))
        self._system4_safety.set_connected(connected)
        if not connected:
            self._system4_status("DCS DISCONNECTED / SAFETY DISARMED")
            self._system4_ecm_hold.reset()
            self._system4_emer_hold.reset()
            return
        if self._system4_status_text.startswith("DCS DISCONNECTED"):
            self._system4_status("DCS CONNECTED")
        for field, address in analog_feedback_fields().items():
            self._system4_apply_feedback(field, round(self._system4_read_word(address) / 65535.0, 3))
        for field, (address, mask, shift) in integer_feedback_fields().items():
            self._system4_apply_feedback(field, (self._system4_read_word(address) & mask) >> shift)

    def _init_system_select(self):
        previous_init_select(self)
        cell = self._select_cells.get((201, 3))
        if cell:
            cell.setText("4  SYSTEM 4\nHUD / NAV / EW")

    def init_ui(self):
        previous_init_ui(self)
        self._init_system4()

    def _show_page(self, page_name):
        previous = getattr(self, "_current_page", None)
        if previous != page_name and hasattr(self, "_system4_safety"):
            self._system4_safety.cancel_all("PAGE CHANGE / SAFETY DISARMED")
            self._system4_ecm_hold.reset()
            self._system4_emer_hold.reset()
        result = previous_show_page(self, page_name)
        if previous in SYSTEM4_PAGES or page_name in SYSTEM4_PAGES:
            self.update()
            self.repaint()
        return result

    def on_cell_click(self, pos):
        if getattr(self, "_current_page", None) == "select" and pos == (201, 3):
            self._show_page(PAGE_4A)
            return
        return previous_cell_click(self, pos)

    def _check_dcs_timeout(self):
        previous_check_timeout(self)
        if hasattr(self, "_system4_safety"):
            self._system4_safety.set_connected(not self._dcs_disconnected)

    def _rescale_children(self, win_w, win_h):
        previous_rescale(self, win_w, win_h)
        scale = min(win_w / self.DESIGN_W, win_h / self.DESIGN_H)
        for control in getattr(self, "_system4_controls", {}).values():
            control.rescale_font(max(6, round(9 * scale)))

    def _cold_reset_session_state(self, reason=""):
        if hasattr(self, "_system4_safety"):
            self._system4_safety.cancel_all("RESET / SAFETY DISARMED")
        if previous_reset:
            return previous_reset(self, reason)

    def closeEvent(self, event):
        if hasattr(self, "_system4_safety"):
            self._system4_safety.cancel_all("APPLICATION CLOSE / SAFETY DISARMED")
        if hasattr(self, "_system4_feedback_timer"):
            self._system4_feedback_timer.stop()
        return previous_close(self, event)

    UFCKeypadWindowClass._system4_register = _system4_register
    UFCKeypadWindowClass._system4_label = _system4_label
    UFCKeypadWindowClass._system4_section = _system4_section
    UFCKeypadWindowClass._system4_send = _system4_send
    UFCKeypadWindowClass._system4_sender = _system4_sender
    UFCKeypadWindowClass._system4_status = _system4_status
    UFCKeypadWindowClass._system4_add_control = _system4_add_control
    UFCKeypadWindowClass._system4_make_header = _system4_make_header
    UFCKeypadWindowClass._system4_outer_frame = _system4_outer_frame
    UFCKeypadWindowClass._init_system4 = _init_system4
    UFCKeypadWindowClass._system4_read_word = _system4_read_word
    UFCKeypadWindowClass._system4_apply_feedback = _system4_apply_feedback
    UFCKeypadWindowClass._system4_poll_feedback = _system4_poll_feedback
    UFCKeypadWindowClass._init_system_select = _init_system_select
    UFCKeypadWindowClass.init_ui = init_ui
    UFCKeypadWindowClass._show_page = _show_page
    UFCKeypadWindowClass.on_cell_click = on_cell_click
    UFCKeypadWindowClass._check_dcs_timeout = _check_dcs_timeout
    UFCKeypadWindowClass._rescale_children = _rescale_children
    UFCKeypadWindowClass._cold_reset_session_state = _cold_reset_session_state
    UFCKeypadWindowClass.closeEvent = closeEvent
