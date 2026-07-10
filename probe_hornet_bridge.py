# -*- coding: utf-8 -*-
"""Probe the UFC_Keypad DCS Export.lua bridge and write reusable reports."""
from __future__ import annotations

import argparse
import json
import socket
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

HOST = "127.0.0.1"
TELEMETRY_PORT = 5518
COMMAND_PORT = 5519

KEYS = [
    "bridge", "last_command", "gross_weight_lbs", "stab_trim_deg", "param_probe",
    "seat_armed_arg_511", "ecm_mode_arg_248", "rwr_power_light_arg_276",
    "rwr_enable_light_arg_267", "fcs_reset_arg_349", "canopy_sw_arg_453",
    "apu_arg_375", "rwr_power_arg_277", "obogs_arg_365", "radar_arg_440",
    "ins_arg_443", "hmd_brt_arg_136",
    *[f"trim_arg_{arg}" for arg in (15, 16, 17, 18, 345, 346, 500, 501, 502, 503)],
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
    tx.sendto(json.dumps(payload, separators=(",", ":")).encode("utf-8"), (HOST, COMMAND_PORT))


def _recv_latest(rx: socket.socket, seconds: float = 1.5) -> Optional[Dict[str, Any]]:
    deadline = time.monotonic() + seconds
    latest = None
    while time.monotonic() < deadline:
        try:
            data, _addr = rx.recvfrom(65535)
        except socket.timeout:
            continue
        try:
            value = json.loads(data.decode("utf-8", errors="strict"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(value, dict):
            latest = value
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


def _changes(before: Optional[Dict[str, Any]], after: Optional[Dict[str, Any]],
             keys: Iterable[str]) -> Dict[str, Dict[str, Any]]:
    if not before or not after:
        return {}
    result = {}
    for key in keys:
        if before.get(key) != after.get(key):
            result[key] = {"before": before.get(key), "after": after.get(key)}
    return result


def _scan_changes(before: Optional[Dict[str, Any]], after: Optional[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    if not before or not after:
        return {}
    a = before.get("scan_args") if isinstance(before.get("scan_args"), dict) else {}
    b = after.get("scan_args") if isinstance(after.get("scan_args"), dict) else {}
    return _changes(a, b, sorted(set(a) | set(b), key=lambda item: int(item)))


def _print_changes(changes: Dict[str, Dict[str, Any]], label: str = "Changed fields") -> None:
    print(f"\n{label}:")
    if not changes:
        print("  none detected")
        return
    for key, values in changes.items():
        print(f"  {key}: {values['before']} -> {values['after']}")


class Report:
    def __init__(self, scan_from: int, scan_to: int) -> None:
        self.started_at = datetime.now().astimezone()
        self.data: Dict[str, Any] = {
            "schema_version": 1,
            "started_at": self.started_at.isoformat(timespec="seconds"),
            "host": HOST,
            "telemetry_port": TELEMETRY_PORT,
            "command_port": COMMAND_PORT,
            "scan_range": {"from": scan_from, "to": scan_to},
            "telemetry_received": False,
            "scan_received": False,
            "events": [],
        }

    def add(self, label: str, payload: Dict[str, Any], before: Optional[Dict[str, Any]],
            after: Optional[Dict[str, Any]], watch: Iterable[str]) -> None:
        field_changes = _changes(before, after, watch)
        scan_changes = _scan_changes(before, after)
        self.data["events"].append({
            "label": label,
            "payload": payload,
            "before": before,
            "after": after,
            "last_command_changed": bool(before and after and before.get("last_command") != after.get("last_command")),
            "field_changes": field_changes,
            "draw_argument_changes": scan_changes,
        })
        _print_changes(field_changes)
        _print_changes(scan_changes, "Changed draw arguments")

    def write(self, output_dir: Path) -> tuple[Path, Path]:
        output_dir.mkdir(parents=True, exist_ok=True)
        stamp = self.started_at.strftime("%Y%m%d_%H%M%S")
        json_path = output_dir / f"probe_report_{stamp}.json"
        md_path = output_dir / f"probe_report_{stamp}.md"
        self.data["finished_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
        json_path.write_text(json.dumps(self.data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        md_path.write_text(self._markdown(), encoding="utf-8")
        return md_path, json_path

    def _markdown(self) -> str:
        d = self.data
        lines = [
            "# UFC_Keypad Hornet bridge probe report", "",
            f"- Started: `{d['started_at']}`",
            f"- Telemetry received: **{'YES' if d['telemetry_received'] else 'NO'}**",
            f"- Draw argument scan received: **{'YES' if d['scan_received'] else 'NO'}**",
            f"- Draw argument scan: `{d['scan_range']['from']}..{d['scan_range']['to']}`", "",
        ]
        initial = d.get("initial")
        if initial:
            lines += ["## Initial telemetry", "", "| Field | Value |", "|---|---|"]
            for key in KEYS:
                lines.append(f"| `{key}` | `{initial.get(key)}` |")
            lines.append("")
        else:
            lines += ["## Failure", "", "No telemetry was received. Check bridge loading, UDP 5518 ownership, and the DCS log.", ""]
        for event in d["events"]:
            lines += [f"## {event['label']}", "", f"Command acknowledged: **{'YES' if event['last_command_changed'] else 'NO'}**", ""]
            lines += ["### Watched field changes", ""]
            lines += self._change_table(event["field_changes"])
            lines += ["", "### Draw argument changes", ""]
            lines += self._change_table(event["draw_argument_changes"])
            lines.append("")
        lines += ["## Raw data", "", f"See `{self.started_at.strftime('probe_report_%Y%m%d_%H%M%S.json')}`.", ""]
        return "\n".join(lines)

    @staticmethod
    def _change_table(changes: Dict[str, Dict[str, Any]]) -> list[str]:
        if not changes:
            return ["No change detected."]
        rows = ["| Field/argument | Before | After |", "|---|---:|---:|"]
        rows.extend(f"| `{key}` | `{value['before']}` | `{value['after']}` |" for key, value in changes.items())
        return rows


def _pause(prompt: str, assume_yes: bool) -> None:
    if not assume_yes:
        input(prompt)


def _probe_clickable(rx: socket.socket, tx: socket.socket, report: Report, *, label: str,
                     device: int, command: int, values: list[float], watch: list[str]) -> None:
    print(f"\n{'#' * 72}\nPROBE {label}: device={device}, command={command}, values={values}\n{'#' * 72}")
    before = _recv_latest(rx, 1.0)
    _print_snapshot(f"BEFORE {label}", before)
    for value in values:
        payload = {"type": "clickable", "label": f"PROBE {label} {value}", "device": device, "command": command, "value": value}
        print(f"\nSEND {payload}")
        _send(tx, payload)
        after = _recv_latest(rx, 1.2)
        _print_snapshot(f"AFTER {label} value={value}", after)
        report.add(f"{label} value={value}", payload, before, after, watch)
        before = after


def _probe_trim(rx: socket.socket, tx: socket.socket, report: Report) -> None:
    print(f"\n{'#' * 72}\nPROBE TRIM UP/DOWN\n{'#' * 72}")
    before = _recv_latest(rx, 1.0)
    _print_snapshot("BEFORE TRIM", before)
    watch = [key for key in KEYS if key.startswith("trim_arg_")] + ["stab_trim_deg"]
    for direction in ("up", "down"):
        payload = {"type": "trim", "direction": direction, "pulse_ms": 250}
        print(f"\nSEND {payload}")
        _send(tx, payload)
        after = _recv_latest(rx, 1.5)
        _print_snapshot(f"AFTER TRIM {direction}", after)
        report.add(f"TRIM {direction}", payload, before, after, watch)
        before = after


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yes", action="store_true", help="run all potentially cockpit-changing probes without prompts")
    parser.add_argument("--output-dir", type=Path, default=Path.cwd(), help="report directory (default: current directory)")
    parser.add_argument("--scan-from", type=int, default=0)
    parser.add_argument("--scan-to", type=int, default=800)
    args = parser.parse_args()
    if not 0 <= args.scan_from <= args.scan_to <= 2000 or args.scan_to - args.scan_from > 1000:
        parser.error("scan range must be within 0..2000 and contain at most 1001 arguments")
    return args


def main() -> int:
    args = _parse_args()
    report = Report(args.scan_from, args.scan_to)
    print("UFC_Keypad Hornet bridge probe")
    print("Run in an F/A-18C cockpit with the main UFC app stopped.")
    rx = _make_rx()
    tx = _make_tx()
    exit_code = 0
    try:
        print("\nEnabling draw-argument scan and sending ping...")
        _send(tx, {"type": "scan_args", "from": args.scan_from, "to": args.scan_to})
        _send(tx, {"type": "dump_params"})
        _send(tx, {"type": "ping"})
        first = _recv_latest(rx, 3.0)
        report.data["initial"] = first
        report.data["telemetry_received"] = bool(first)
        report.data["scan_received"] = bool(first and isinstance(first.get("scan_args"), dict))
        _print_snapshot("INITIAL TELEMETRY", first)
        if not first:
            print("\nFAIL: no telemetry. Check bridge loading, UDP 5518 ownership, and firewall state.")
            exit_code = 2
        else:
            _pause("\nPress Enter to probe EJECTION SEAT ARMED. ", args.yes)
            _probe_clickable(rx, tx, report, label="EJECTION_SEAT_ARMED", device=7, command=3006,
                             values=[1.0, 0.0], watch=["seat_armed_arg_511"])
            _pause("\nPress Enter to probe ECM MODE. ", args.yes)
            _probe_clickable(rx, tx, report, label="ECM_MODE_SW", device=66, command=3001,
                             values=[0.0, 0.1, 0.2, 0.4, 0.3],
                             watch=["ecm_mode_arg_248", "rwr_power_light_arg_276", "rwr_enable_light_arg_267"])
            _pause("\nPress Enter to probe pitch trim. ", args.yes)
            _probe_trim(rx, tx, report)
    except (KeyboardInterrupt, EOFError):
        print("\nProbe interrupted; writing the partial report.")
        report.data["interrupted"] = True
        exit_code = 130
    finally:
        rx.close()
        tx.close()
        md_path, json_path = report.write(args.output_dir)
        print(f"\nReports written:\n  {md_path}\n  {json_path}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
