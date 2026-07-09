# -*- coding: utf-8 -*-
"""DCS-BIOS receiver patch for real-time IFEI RPM updates.

The base receiver suppresses callbacks when a field value has not changed.  That
is good for UFC text displays, but bad for startup state detection across DCS
missions: engine RPM may remain "0" between two cold missions or remain high in a
hot-start slot, and the startup manager still needs a fresh callback from the
current DCS-BIOS session.

This patch keeps normal value-change filtering for regular fields, but always
emits callbacks for IFEI_RPM_L / IFEI_RPM_R whenever those fields are touched in
an incoming UDP packet.
"""
from __future__ import annotations

import socket
import struct
import time

from ufc.dcs_bios import DCSBIOSReceiver

RPM_BIOS_FIELDS = {"IFEI_RPM_L", "IFEI_RPM_R"}


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

            last_retry = time.time()
            last_value = {}
            addr_file_loaded = self._external_address_available()

            while self.running:
                try:
                    data, _ = self.sock.recvfrom(65535)
                    self._last_packet_time = time.time()

                    if not addr_file_loaded and time.time() - last_retry > 10.0:
                        last_retry = time.time()
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
