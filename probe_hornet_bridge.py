# -*- coding: utf-8 -*-
"""Probe the UFC_Keypad DCS Export.lua bridge in a live F/A-18C mission.

Run this with DCS already in an F/A-18C cockpit and the Export bridge installed:

    python probe_hornet_bridge.py

The script listens on UDP 5518, sends commands to UDP 5519, and prints the
telemetry before/after each probe.  It does not need the main UFC app running.

What it proves:
- whether DCS loaded UFC_Keypad_CVTrim.lua;
- whether Python -> DCS command UDP works;
- whether the expected cockpit draw arguments change;
- whether CV trim telemetry can read weight/current trim.
"""
from __future__ import annotations

import json
import socket
import time
from typing import Any, Dict, Iterable, Optional

HOST = "127.0.0.1"
TELEMETRY_PORT = 5518
COMMAND_PORT = 5519

KEYS = [
    "bridge",
    "last_command",
    "gross_weight_lbs",
    "stab_trim_deg",
    "seat_armed_arg_511",
    "ecm_mode_arg_248",
    "rwr_power_light_arg_276",
    "rwr_enable_light_arg_267",
    "fcs_reset_arg_349",
    "canopy_sw_arg_453",
    "trim_arg_15",
    "trim_arg_16",
    "trim_arg_17",
    "trim_arg_18",
    "trim_arg_345",
    "trim_arg_346",
    "trim_arg_500",
    "trim_arg_501",
    "trim_arg_502",
    "trim_arg_503",
]


def _make_rx() -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((HOST, TELEMETRY_PORT))
    sock.settimeout(0.25)
    return sock


def _make_tx() -> socket.socket:
    return socket.socket(socket.AF_INET, socket.SOCK_DGRAM)


def _send(tx: socket.socket, payload: Dict[str, Any]) -> None:
    data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    tx.sendto(data, (HOST, COMMAND_PORT))


def _recv_latest(rx: socket.socket, seconds: float = 1.5) -> Optional[Dict[str, Any]]:
    deadline = time.time() + seconds
    latest = None
    while time.time() < deadline:
        try:
            data, _addr = rx.recvfrom(65535)
        except socket.timeout:
            continue
        try:
            latest = json.loads(data.decode("utf-8", errors="ignore"))
        except json.JSONDecodeError:
            continue
    return latest


def _print_snapshot(title: str, snap: Optional[Dict[str, Any]]) -> None:
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)
    if not snap:
        print("NO TELEMETRY RECEIVED")
        return
    for key in KEYS:
        print(f"{key:24s}: {snap.get(key)}")


def _diff(before: Optional[Dict[str, Any]], after: Optional[Dict[str, Any]], keys: Iterable[str]) -> None:
    print("\nChanged fields:")
    if not before or not after:
        print("  cannot compare; missing telemetry")
        return
    changed = False
    for key in keys:
        a = before.get(key)
        b = after.get(key)
        if a != b:
            changed = True
            print(f"  {key}: {a} -> {b}")
    if not changed:
        print("  no listed field changed")


def _probe_clickable(rx: socket.socket, tx: socket.socket, *, label: str, device: int, command: int,
                     values: list[float], watch: list[str]) -> None:
    print("\n" + "#" * 72)
    print(f"PROBE {label}: device={device}, command={command}, values={values}")
    print("#" * 72)
    before = _recv_latest(rx, 1.0)
    _print_snapshot(f"BEFORE {label}", before)
    for value in values:
        payload = {"type": "clickable", "label": f"PROBE {label} {value}", "device": device, "command": command, "value": value}
        print(f"\nSEND {payload}")
        _send(tx, payload)
        after = _recv_latest(rx, 1.2)
        _print_snapshot(f"AFTER {label} value={value}", after)
        _diff(before, after, watch)
        before = after


def _probe_trim(rx: socket.socket, tx: socket.socket) -> None:
    print("\n" + "#" * 72)
    print("PROBE TRIM UP/DOWN")
    print("#" * 72)
    before = _recv_latest(rx, 1.0)
    _print_snapshot("BEFORE TRIM", before)
    for direction in ("up", "down"):
        payload = {"type": "trim", "direction": direction, "pulse_ms": 250}
        print(f"\nSEND {payload}")
        _send(tx, payload)
        after = _recv_latest(rx, 1.5)
        _print_snapshot(f"AFTER TRIM {direction}", after)
        _diff(before, after, [k for k in KEYS if k.startswith("trim_arg_")] + ["stab_trim_deg"])
        before = after


def main() -> int:
    print("UFC_Keypad Hornet bridge probe")
    print("Run while DCS is in an F/A-18C cockpit. Do not run the main UFC app at the same time.")
    print("Listening on 127.0.0.1:5518 and sending to 127.0.0.1:5519")

    rx = _make_rx()
    tx = _make_tx()

    print("\nSending ping...")
    _send(tx, {"type": "ping"})
    first = _recv_latest(rx, 3.0)
    _print_snapshot("INITIAL TELEMETRY", first)
    if not first:
        print("\nFAIL: no telemetry. DCS did not load the Export bridge or another app is already bound to UDP 5518.")
        return 2

    input("\nPress Enter to probe EJECTION SEAT ARMED. Watch the cockpit handle. ")
    _probe_clickable(
        rx,
        tx,
        label="EJECTION_SEAT_ARMED",
        device=7,
        command=3006,
        values=[1.0, 0.0, 1.0, -1.0, 1.0],
        watch=["seat_armed_arg_511"],
    )

    input("\nPress Enter to probe ECM MODE. Watch the ECM switch. ")
    _probe_clickable(
        rx,
        tx,
        label="ECM_MODE_SW",
        device=66,
        command=3001,
        values=[0.0, 0.1, 0.2, 0.3, 0.4, -0.1, 0.1],
        watch=["ecm_mode_arg_248", "rwr_power_light_arg_276", "rwr_enable_light_arg_267"],
    )

    input("\nPress Enter to probe pitch trim. Watch FCS/STAB trim and console output. ")
    _probe_trim(rx, tx)

    print("\nProbe complete. Also check Saved Games\\DCS.openbeta\\Logs\\UFC_Keypad_CVTrim.log")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
