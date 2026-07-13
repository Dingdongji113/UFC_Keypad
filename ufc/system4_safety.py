# -*- coding: utf-8 -*-
"""Safety state machines for SYSTEM 4 hazardous controls."""
from __future__ import annotations

import time
from typing import Callable

from PyQt6.QtCore import QObject, QTimer

from ufc.system4_mapping import CONTROLS


class System4Safety(QObject):
    AUX_CONFIRM_MS = 3000
    EMER_ARM_MS = 3000
    PULSE_MS = 120

    def __init__(self, sender: Callable[[str, object], bool],
                 status: Callable[[str], None], parent=None):
        super().__init__(parent)
        self.sender = sender
        self.status = status
        self.connected = False
        self.aux_pending = False
        self.emer_armed = False
        self.emer_deadline = 0.0
        self._aux_timer = QTimer(self)
        self._aux_timer.setSingleShot(True)
        self._aux_timer.timeout.connect(self._expire_aux)
        self._emer_timer = QTimer(self)
        self._emer_timer.setSingleShot(True)
        self._emer_timer.timeout.connect(lambda: self.disarm("EMER ARM TIMEOUT"))

    def set_connected(self, connected: bool) -> None:
        self.connected = bool(connected)
        if not self.connected:
            self.cancel_all("DCS DISCONNECTED")

    def _send(self, identifier: str, value) -> bool:
        if not self.connected:
            self.status("BLOCKED: DCS DISCONNECTED")
            return False
        return bool(self.sender(identifier, value))

    def _pulse(self, identifier: str) -> bool:
        if not self._send(identifier, 1):
            return False
        QTimer.singleShot(self.PULSE_MS, lambda: self.sender(identifier, 0))
        return True

    def request_aux(self, enable: bool) -> bool:
        spec = CONTROLS["aux_rel"]
        if not enable:
            self._clear_aux()
            ok = self._send(spec.identifier, "TOGGLE")
            self.status("AUX REL NORM" if ok else "AUX REL NORM FAILED")
            return ok
        if not self.connected:
            self.status("AUX REL BLOCKED: DCS DISCONNECTED")
            return False
        if not self.aux_pending:
            self.aux_pending = True
            self._aux_timer.start(self.AUX_CONFIRM_MS)
            self.status("CONFIRM AUX REL ENABLE")
            return False
        self._clear_aux()
        ok = self._send(spec.identifier, "TOGGLE")
        self.status("AUX REL ENABLE" if ok else "AUX REL ENABLE FAILED")
        return ok

    def _clear_aux(self) -> None:
        self.aux_pending = False
        self._aux_timer.stop()

    def _expire_aux(self) -> None:
        if self.aux_pending:
            self.aux_pending = False
            self.status("AUX REL CONFIRM TIMEOUT")

    def execute_ecm_jett(self) -> bool:
        ok = self._pulse(CONTROLS["ecm_jett"].identifier)
        self.status("ECM JETT SENT" if ok else "ECM JETT BLOCKED")
        return ok

    def arm_emergency(self) -> bool:
        if not self.connected:
            self.status("EMER JETT BLOCKED: DCS DISCONNECTED")
            return False
        self.emer_armed = True
        self.emer_deadline = time.monotonic() + self.EMER_ARM_MS / 1000.0
        self._emer_timer.start(self.EMER_ARM_MS)
        self.status("EMER JETT ARMED: HOLD WITHIN 3S")
        return True

    def execute_emergency(self) -> bool:
        valid = self.emer_armed and time.monotonic() <= self.emer_deadline and self.connected
        if not valid:
            self.disarm("EMER JETT BLOCKED / NOT ARMED")
            return False
        ok = self._pulse(CONTROLS["emer_jett"].identifier)
        self.disarm("EMER JETT SENT" if ok else "EMER JETT FAILED")
        return ok

    def disarm(self, reason: str = "DISARMED") -> None:
        was_armed = self.emer_armed
        self.emer_armed = False
        self.emer_deadline = 0.0
        self._emer_timer.stop()
        if was_armed or "SENT" in reason or "BLOCKED" in reason:
            self.status(reason)

    def cancel_all(self, reason: str = "SAFETY RESET") -> None:
        had_pending = self.aux_pending or self.emer_armed
        self._clear_aux()
        self.disarm(reason)
        if had_pending and not self.emer_armed:
            self.status(reason)
