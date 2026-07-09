# -*- coding: utf-8 -*-
"""DCS-BIOS receiver patch for real-time IFEI RPM updates.

The base receiver suppresses callbacks when a field value has not changed.  That
is good for UFC text displays, but bad for startup state detection across DCS
missions: engine RPM may remain "0" between two cold missions or remain high in a
hot-start slot, and the startup manager still needs a fresh callback from the
current DCS-BIOS session.

This patch uses two paths:
- Event path: if IFEI_RPM_L / IFEI_RPM_R are touched by an incoming UDP packet,
  emit them immediately even if the value is unchanged.
- State polling path: after every UDP packet, read the hardcoded IFEI RPM string
  bytes directly from parser.state and emit left/right RPM snapshots.  This fixes
  cold-dark 0/0 cases where DCS-BIOS has valid state bytes but does not report a
  touched string update for IFEI_RPM_L/R.
"""
from __future__ import annotations

import re
import socket
import struct
import time

from ufc.dcs_bios import DCSBIOSReceiver
from ufc.ifei_rpm import (
    IFEI_RPM_L_ADDR,
    IFEI_RPM_L_FIELD,
    IFEI_RPM_L_INTERNAL,
    IFEI_RPM_L_LEN,
    IFEI_RPM_R_ADDR,
    IFEI_RPM_R_FIELD,
    IFEI_RPM_R_INTERNAL,
    IFEI_RPM_R_LEN,
)

RPM_BIOS_FIELDS = {IFEI_RPM_L_FIELD, IFEI_RPM_R_FIELD}
RPM_SNAPSHOT_INTERVAL_SEC = 0.25


def _decode_rpm_state(parser, addr: int, length: int) -> str:
    """Decode a fixed IFEI RPM string from parser.state.

    DCS-BIOS strings are stored as bytes in parser.state.  If DCS-BIOS has not
    touched the field yet, the state bytes are all zero; for cold-start gating we
    treat that as a valid cold 0 snapshot after the receiver is already synced.
    """
    raw = bytes(parser.state[addr + i] for i in range(length))
    if not raw or all(b == 0 for b in raw):
        return "0"
    text = "".join(chr(b) if 0x20 <= b <= 0x7E else " " for b in raw).strip()
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    return match.group(0) if match else "0"


def install_realtime_rpm_callbacks() -> None:
    """Patch DCSBIOSReceiver.run so RPM fields are emitted on every fresh packet."""
    if getattr(DCSBIOSReceiver, "_realtime_rpm_patch_installed", False):
        return
    DCSBIOSReceiver._realtime_rpm_patch_installed = True

    def run(self):
        """Receiver thread main loop with always-callback RPM fields."""
        self.running = True

        self._learn_addresses()

        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.bind(("", self.DCS_BIOS_PORT))

            mreq = struct.pack("4sL", socket.inet_aton(self.DCS_BIOS_IP), socket.INADDR_ANY)
            self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
            self.sock.settimeout(0.5)

            print(f"[DCS-BIOS] Listening on {self.DCS_BIOS_IP}:{self.DCS_BIOS_PORT}")
            print("[DCS-BIOS] Realtime RPM callbacks enabled for IFEI_RPM_L / IFEI_RPM_R")
            print("[DCS-BIOS] IFEI RPM state polling enabled")

            last_retry = time.time()
            last_value = {}
            last_snapshot_emit = 0.0
            addr_file_loaded = self._external_address_available()

            while self.running:
                try:
                    data, _ = self.sock.recvfrom(65535)
                    now = time.time()
                    self._last_packet_time = now

                    if not addr_file_loaded and now - last_retry > 10.0:
                        last_retry = now
                        if self._external_address_available():
                            print("[DCS-BIOS] External address file now available, reloading...")
                            self._learn_addresses()
                            addr_file_loaded = True

                    updated = self.parser.parse(data)

                    for field_name, value in updated:
                        self.latest[field_name] = value
                        prev = last_value.get(field_name)
                        changed = value != prev
                        always_emit = field_name in RPM_BIOS_FIELDS
                        if changed or always_emit:
                            last_value[field_name] = value
                            if self.callback and field_name in self.UFC_FIELDS:
                                internal_name = self.UFC_FIELDS[field_name][0]
                                self.callback(internal_name, value)

                    # Fallback: poll fixed IFEI RPM bytes directly from parser.state.
                    # This does not depend on parser.parse() reporting the strings as
                    # touched in the current packet, so cold-dark 0/0 can still be
                    # classified after the DCS-BIOS stream is alive.
                    if self.parser.synced and now - last_snapshot_emit >= RPM_SNAPSHOT_INTERVAL_SEC:
                        last_snapshot_emit = now
                        rpm_snapshots = [
                            (IFEI_RPM_L_FIELD, IFEI_RPM_L_INTERNAL, IFEI_RPM_L_ADDR, IFEI_RPM_L_LEN),
                            (IFEI_RPM_R_FIELD, IFEI_RPM_R_INTERNAL, IFEI_RPM_R_ADDR, IFEI_RPM_R_LEN),
                        ]
                        for field_name, internal_name, addr, length in rpm_snapshots:
                            value = _decode_rpm_state(self.parser, addr, length)
                            self.latest[field_name] = value
                            self.latest[internal_name] = value
                            last_value[field_name] = value
                            if self.callback:
                                self.callback(internal_name, value)

                    for addr, internal_name in self.parser.analog_addresses.items():
                        lo = self.parser.state[addr]
                        hi = self.parser.state[addr + 1]
                        raw = lo | (hi << 8)
                        val = round(raw / 65535.0, 3)
                        self.latest[internal_name] = str(val)
                        prev_a = last_value.get(internal_name)
                        if val != prev_a:
                            last_value[internal_name] = val
                            if self.callback:
                                self.callback(internal_name, str(val))

                    for addr, (internal_name, mask, shift) in self.parser.integer_addrs.items():
                        lo = self.parser.state[addr]
                        hi = self.parser.state[addr + 1]
                        raw = lo | (hi << 8)
                        val = (raw & mask) >> shift
                        prev_i = last_value.get(internal_name)
                        if val != prev_i:
                            last_value[internal_name] = val
                            if self.callback:
                                self.callback(internal_name, str(val))

                except socket.timeout:
                    continue
                except Exception as e:
                    if self.running:
                        print(f"[DCS-BIOS] Receive error: {e}")

        except Exception as e:
            print(f"[DCS-BIOS] Failed to start: {e}")
        finally:
            self.stop()

    DCSBIOSReceiver.run = run
