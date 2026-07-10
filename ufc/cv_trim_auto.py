# -*- coding: utf-8 -*-
"""CV catapult trim and direct cockpit command bridge.

Some FA-18C cold-start actions are unreliable through DCS-BIOS alone on the
user's install, while board weight and stabilator trim are not exposed as normal
DCS-BIOS fields.  This module therefore uses an optional Export.lua bridge:

- UDP 5518: DCS -> UFC_Keypad telemetry JSON
- UDP 5519: UFC_Keypad -> DCS command JSON

The normal DCS-BIOS command is still sent first for cockpit controls.  The bridge
is a second path for controls that have repeatedly failed in practice, and a
required path for automatic CV catapult trim.
"""
from __future__ import annotations

import json
import math
import os
import socket
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from PyQt6.QtCore import QTimer

TELEMETRY_PORT = 5518
COMMAND_PORT = 5519
TRIM_TOLERANCE_DEG = 0.25
TRIM_PULSE_MS = 120
TRIM_RECHECK_MS = 260
TRIM_MAX_PULSES = 90
INS_TO_AMPCD_DELAY_MS = 10000
RDDI_OSB_INTERVAL_MS = 3000


@dataclass
class CVTrimSnapshot:
    weight_lbs: Optional[float] = None
    trim_deg: Optional[float] = None
    timestamp: float = 0.0
    raw: Optional[Dict[str, Any]] = None


class CVTrimTelemetryReceiver:
    """Tiny UDP JSON telemetry receiver for CV catapult trim."""

    def __init__(self, port: int = TELEMETRY_PORT):
        self.port = int(port)
        self._sock: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._latest = CVTrimSnapshot()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="UFC CV Trim Telemetry", daemon=True)
        self._thread.start()

    def snapshot(self) -> CVTrimSnapshot:
        with self._lock:
            return CVTrimSnapshot(
                weight_lbs=self._latest.weight_lbs,
                trim_deg=self._latest.trim_deg,
                timestamp=self._latest.timestamp,
                raw=dict(self._latest.raw or {}),
            )

    def inject_for_test(self, weight_lbs: Optional[float], trim_deg: Optional[float]) -> None:
        with self._lock:
            self._latest = CVTrimSnapshot(weight_lbs=weight_lbs, trim_deg=trim_deg, timestamp=time.time(), raw={})

    def _run(self) -> None:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("127.0.0.1", self.port))
            sock.settimeout(0.5)
            self._sock = sock
            print(f"[CV-TRIM] Listening telemetry on 127.0.0.1:{self.port}")
        except Exception as exc:
            print(f"[CV-TRIM] Telemetry receiver failed: {exc}")
            return

        while not self._stop.is_set():
            try:
                data, _ = self._sock.recvfrom(8192)
                payload = json.loads(data.decode("utf-8", errors="ignore"))
                weight = _pick_float(payload, "gross_weight_lbs", "weight_lbs", "board_weight_lbs", "empty_weight_lbs")
                trim = _pick_float(payload, "stab_trim_deg", "stabilator_trim_deg", "elevator_trim_deg", "pitch_trim_deg")
                with self._lock:
                    self._latest = CVTrimSnapshot(weight_lbs=weight, trim_deg=trim, timestamp=time.time(), raw=payload)
            except socket.timeout:
                continue
            except Exception as exc:
                print(f"[CV-TRIM] Telemetry parse error: {exc}")


_RECEIVER = CVTrimTelemetryReceiver()
_COMMAND_SOCK: Optional[socket.socket] = None


def _debug_log(message: str) -> None:
    try:
        path = os.path.join(os.getcwd(), "cv_trim_debug.log")
        with open(path, "a", encoding="utf-8") as f:
            f.write(time.strftime("[%Y-%m-%d %H:%M:%S] ") + str(message) + "\n")
    except Exception:
        pass


def _command_sock() -> socket.socket:
    global _COMMAND_SOCK
    if _COMMAND_SOCK is None:
        _COMMAND_SOCK = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    return _COMMAND_SOCK


def _send_bridge_payload(payload: Dict[str, Any]) -> bool:
    try:
        data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        _command_sock().sendto(data, ("127.0.0.1", COMMAND_PORT))
        _debug_log(f"bridge send {payload}")
        return True
    except Exception as exc:
        _debug_log(f"bridge send failed {payload}: {exc}")
        print(f"[CV-TRIM] Bridge command send failed: {exc}")
        return False


def _pick_float(payload: Dict[str, Any], *names: str) -> Optional[float]:
    for name in names:
        value = payload.get(name)
        if value is None:
            continue
        try:
            number = float(value)
            if math.isfinite(number):
                return number
        except (TypeError, ValueError):
            continue
    return None


def cv_trim_target_deg(weight_lbs: float) -> float:
    """Return carrier launch nose-up trim target from board/gross weight."""
    weight = float(weight_lbs)
    if weight <= 44000.0:
        return 16.0
    if weight < 49000.0:
        return 17.0
    return 19.0


def send_direct_clickable(device: int, command: int, value: float, *, label: str = "", hold_ms: int = 0,
                          release_value: Optional[float] = None) -> bool:
    """Send a direct clickable cockpit action through the Export.lua bridge."""
    payload: Dict[str, Any] = {
        "type": "clickable",
        "device": int(device),
        "command": int(command),
        "value": float(value),
    }
    if label:
        payload["label"] = str(label)
    if hold_ms:
        payload["hold_ms"] = int(hold_ms)
    if release_value is not None:
        payload["release_value"] = float(release_value)
    return _send_bridge_payload(payload)


def send_direct_set_command(device: int, command: int, value: float, *, label: str = "", hold_ms: int = 0,
                            release_value: Optional[float] = None) -> bool:
    """Send a device SetCommand action through the Export.lua bridge."""
    payload: Dict[str, Any] = {
        "type": "set_command",
        "device": int(device),
        "command": int(command),
        "value": float(value),
    }
    if label:
        payload["label"] = str(label)
    if hold_ms:
        payload["hold_ms"] = int(hold_ms)
    if release_value is not None:
        payload["release_value"] = float(release_value)
    return _send_bridge_payload(payload)


def send_cv_trim_pulse(direction: str, pulse_ms: int = TRIM_PULSE_MS) -> bool:
    """Send a trim pulse request to the optional DCS Export bridge."""
    direction = str(direction).lower().strip()
    if direction not in ("up", "down"):
        return False
    return _send_bridge_payload({"type": "trim", "direction": direction, "pulse_ms": int(pulse_ms)})


def install_cv_trim_automation(UFCKeypadWindowClass) -> None:
    """Patch the cold checklist so CV CAT TRIM is automatic when telemetry exists."""
    if getattr(UFCKeypadWindowClass, "_cv_trim_automation_installed", False):
        return
    UFCKeypadWindowClass._cv_trim_automation_installed = True
    _RECEIVER.start()

    previous_step_list = UFCKeypadWindowClass._cold_step_list

    def _cv_trim_snapshot(self) -> CVTrimSnapshot:
        return _RECEIVER.snapshot()

    def _cv_trim_target_deg(self, weight_lbs: float) -> float:
        return cv_trim_target_deg(weight_lbs)

    def _cold_step_list(self):
        steps = []
        for step in previous_step_list(self):
            if step[0] == "CAT TRIM":
                steps.append((
                    "CAT TRIM",
                    "cat_trim_auto",
                    "",
                    "Auto trim for CV launch. Needs board weight and stabilator trim telemetry.",
                ))
            else:
                steps.append(step)
        return steps

    def _cold_run_cat_trim_auto(self, advance_if_running: Callable[[], None]) -> None:
        self._cold_exec_phase = "AUTO"
        self._cold_last_action = "CAT TRIM"
        self._cold_trim_pulse_count = 0
        self._cold_refresh_ui()

        def _tick():
            if getattr(self, "_cold_state", None) != "running":
                return
            snap = self._cv_trim_snapshot()
            age = time.time() - snap.timestamp if snap.timestamp else 999.0
            _debug_log(f"cat trim tick weight={snap.weight_lbs} trim={snap.trim_deg} age={age:.2f} raw={snap.raw}")
            if snap.weight_lbs is None or snap.trim_deg is None or age > 2.0:
                self._cold_state = "wait_user"
                self._cold_exec_phase = "USER"
                self._cold_last_action = "CAT TRIM DATA?"
                self._cold_step_detail = (
                    "No fresh CV trim telemetry. Check dcs_export/UFC_Keypad_CVTrim.lua and cv_trim_debug.log. "
                    "Set catapult trim manually and press START if needed."
                )
                self._cold_log("CAT TRIM telemetry missing; fallback to user confirmation")
                self._cold_refresh_ui()
                return

            target = self._cv_trim_target_deg(snap.weight_lbs)
            current = float(snap.trim_deg)
            error = target - current
            self._cold_last_action = f"CAT TRIM {current:.1f}->{target:.0f}"
            self._cold_step_detail = f"Weight {snap.weight_lbs:.0f} lb, target {target:.0f} deg, current {current:.1f} deg."
            self._cold_refresh_ui()

            if abs(error) <= TRIM_TOLERANCE_DEG:
                self._cold_log(f"CAT TRIM complete weight={snap.weight_lbs:.0f} current={current:.2f} target={target:.2f}")
                advance_if_running()
                return

            pulse_count = int(getattr(self, "_cold_trim_pulse_count", 0))
            if pulse_count >= TRIM_MAX_PULSES:
                self._cold_state = "wait_user"
                self._cold_exec_phase = "USER"
                self._cold_last_action = "CAT TRIM LIMIT"
                self._cold_step_detail = "Auto trim pulse limit reached. Verify trim manually, then START."
                self._cold_refresh_ui()
                return

            direction = "up" if error > 0 else "down"
            ok = send_cv_trim_pulse(direction)
            self._cold_trim_pulse_count = pulse_count + 1
            self._cold_log(f"CAT TRIM pulse {direction} ok={ok} current={current:.2f} target={target:.2f}")
            QTimer.singleShot(TRIM_RECHECK_MS, _tick)

        QTimer.singleShot(0, _tick)

    def _cold_run_next_step(self):
        if self._cold_state != "running":
            return
        steps = self._cold_step_list()
        self._cold_total_steps = len(steps)
        if self._cold_step_index >= len(steps):
            self._cold_state = "complete"
            self._cold_exec_phase = "DONE"
            self._cold_last_action = "COMPLETE"
            self._cold_step_detail = "Cold start complete."
            self._cold_refresh_ui()
            return

        title, kind, payload, hint = steps[self._cold_step_index]
        self._cold_last_action = title
        self._cold_step_detail = hint
        self._cold_exec_phase = "EXEC"
        self._cold_refresh_ui()

        def advance_if_running():
            if getattr(self, "_cold_state", None) == "running":
                self._cold_step_index += 1
                self._cold_run_next_step()

        if kind in ("send", "supervised"):
            self._cold_exec_phase = "EXEC"
            self._cold_refresh_ui()
            self._cold_send_configured_async(payload, advance_if_running)
        elif kind == "timer":
            self._cold_exec_phase = "WAIT"
            self._cold_refresh_ui()
            QTimer.singleShot(int(payload), advance_if_running)
        elif kind == "user":
            self._cold_state = "wait_user"
            self._cold_exec_phase = "USER"
            self._cold_refresh_ui()
        elif kind == "cat_trim_auto":
            self._cold_run_cat_trim_auto(advance_if_running)
        elif kind == "flag_right":
            self._cold_right_engine_online = True
            self._cold_state = "animating"
            self._cold_exec_phase = "UFC BOOT"
            self._cold_last_action = "UFC STARTUP"
            self._cold_step_detail = "Playing 5s UFC animation."
            self._cold_refresh_ui()

            def after_right_anim():
                self._show_page("cold_start")
                self._cold_start_anim_played = True
                self._cold_ui_powered = True
                self._cold_state = "running"
                self._cold_step_index += 1
                self._cold_run_next_step()

            self._cold_play_startup_animation(return_page="cold_start", after=after_right_anim)
        elif kind == "flag_left":
            self._cold_left_engine_online = True
            self._cold_exec_phase = "EXEC"
            self._cold_step_detail = "Left engine confirmed."
            self._cold_refresh_ui()
            QTimer.singleShot(500, advance_if_running)
        elif kind == "apu_off":
            def after_apu_off():
                self._cold_apu_off = True
                advance_if_running()
            self._cold_send_configured_async(payload, after_apu_off)
        elif kind == "display_brightness":
            self._cold_apply_display_brightness()
            QTimer.singleShot(900, advance_if_running)
        elif kind == "unlock":
            self._cold_unlock_local_icp()
            QTimer.singleShot(700, advance_if_running)
        elif kind == "ins":
            self._cold_send_configured_async(
                "ins_carrier" if self._cold_profile == "carrier" else "ins_land",
                advance_if_running,
            )
        elif kind == "ins_radar_setup":
            self._cold_exec_phase = "AUTO"
            self._cold_step_detail = "Setting RADAR OPR and selected INS alignment position."
            self._cold_refresh_ui()

            def after_pb19():
                self._cold_state = "wait_user"
                self._cold_exec_phase = "USER"
                self._cold_last_action = "RADAR / INS CONFIRM"
                self._cold_step_detail = "RADAR OPR and AMPCD PB19 sent. Verify alignment page, then START."
                self._cold_refresh_ui()

            def press_pb19():
                self._cold_last_action = "AMPCD PB19"
                self._cold_step_detail = "Ten seconds elapsed; pressing AMPCD PB19."
                self._cold_refresh_ui()
                self._cold_send_configured_async("ampcd_pb19", after_pb19)

            def after_ins():
                self._cold_last_action = "INS WAIT 10S"
                self._cold_step_detail = "Waiting 10 seconds before AMPCD PB19."
                self._cold_refresh_ui()
                QTimer.singleShot(INS_TO_AMPCD_DELAY_MS, press_pb19)

            def after_radar():
                self._cold_send_configured_async(
                    "ins_carrier" if self._cold_profile == "carrier" else "ins_land",
                    after_ins,
                )

            self._cold_send_configured_async("radar_opr", after_radar)
        elif kind == "hmd_calibrate":
            self._cold_exec_phase = "AUTO"
            self._cold_step_detail = "Powering HMD and setting INS IFA."
            self._cold_refresh_ui()

            def wait_for_hmd_calibration():
                self._cold_state = "wait_user"
                self._cold_exec_phase = "USER"
                self._cold_last_action = "HMD CALIBRATE"
                self._cold_step_detail = "Calibrate HMD manually, then press START. INS is set to IFA."
                self._cold_refresh_ui()

            osb_sequence = [
                ("right_ddi_pb18", "RDDI OSB18 1/2"),
                ("right_ddi_pb18", "RDDI OSB18 2/2"),
                ("right_ddi_pb03", "RDDI OSB3"),
                ("right_ddi_pb20", "RDDI OSB20"),
            ]

            def press_osb(index: int):
                if index >= len(osb_sequence):
                    wait_for_hmd_calibration()
                    return
                key, label = osb_sequence[index]
                self._cold_last_action = label
                self._cold_step_detail = f"Pressing {label}; next command in 3 seconds."
                self._cold_refresh_ui()

                def after_press():
                    QTimer.singleShot(RDDI_OSB_INTERVAL_MS, lambda: press_osb(index + 1))

                self._cold_send_configured_async(key, after_press)

            def set_ifa():
                self._cold_send_configured_async("ins_ifa", lambda: press_osb(0))

            hmd_key = "hmd_night" if str(getattr(self, "_cold_display_mode", "day")).lower() == "night" else "hmd_day"
            self._cold_send_configured_async(hmd_key, set_ifa)
        elif kind == "complete":
            self._cold_state = "complete"
            self._cold_exec_phase = "DONE"
            self._cold_last_action = "COMPLETE"
            self._cold_step_detail = "Cold start complete. Press COMPLETE for LOCAL ICP."
            self._cold_refresh_ui()

    UFCKeypadWindowClass._cv_trim_snapshot = _cv_trim_snapshot
    UFCKeypadWindowClass._cv_trim_target_deg = _cv_trim_target_deg
    UFCKeypadWindowClass._cold_step_list = _cold_step_list
    UFCKeypadWindowClass._cold_run_cat_trim_auto = _cold_run_cat_trim_auto
    UFCKeypadWindowClass._cold_run_next_step = _cold_run_next_step
