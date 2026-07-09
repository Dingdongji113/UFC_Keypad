# -*- coding: utf-8 -*-
"""IFEI RPM DCS-BIOS fallback support.

The FA-18C startup manager needs left engine RPM to decide whether the aircraft
is cold or already running.  Experience from the DDI/IFEI panel shows that IFEI
strings are a separate, stable data path and can be read without relying on
Addresses.h.

For DCS-Skunkworks DCS-BIOS FA-18C:
    IFEI_RPM_L address = 0x749E, length = 3

This module patches DCSBIOSReceiver in-place before the receiver thread starts.
"""
from __future__ import annotations

import os
import re

from ufc.dcs_bios import DCSBIOSReceiver


IFEI_RPM_L_FIELD = "IFEI_RPM_L"
IFEI_RPM_L_INTERNAL = "left_engine_rpm"
IFEI_RPM_L_ADDR = 0x749E
IFEI_RPM_L_LEN = 3


def install_ifei_rpm_fallback() -> None:
    """Install left engine RPM parsing and hardcoded fallback address."""
    DCSBIOSReceiver.UFC_FIELDS[IFEI_RPM_L_FIELD] = (
        IFEI_RPM_L_INTERNAL,
        None,
        IFEI_RPM_L_LEN,
    )
    DCSBIOSReceiver.KNOWN_FIELDS[IFEI_RPM_L_FIELD] = IFEI_RPM_L_LEN
    DCSBIOSReceiver._INTERNAL_TO_BIOS = {}

    if getattr(DCSBIOSReceiver, "_ifei_rpm_fallback_installed", False):
        return
    DCSBIOSReceiver._ifei_rpm_fallback_installed = True

    original_parse_addresses_h = DCSBIOSReceiver._parse_addresses_h
    original_use_fallback_addresses = DCSBIOSReceiver._use_fallback_addresses

    @classmethod
    def _parse_addresses_h_with_ifei(cls, path: str):
        addr_map = original_parse_addresses_h(path)
        if not path or not os.path.exists(path):
            return addr_map
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    m = re.match(
                        r"#define\s+FA_18C_hornet_IFEI_RPM_L_A\s+(0x[0-9A-Fa-f]+)",
                        line.strip(),
                    )
                    if m:
                        addr_map[int(m.group(1), 16)] = (IFEI_RPM_L_FIELD, IFEI_RPM_L_LEN)
                        break
        except Exception:
            pass
        return addr_map

    def _use_fallback_addresses_with_ifei(self):
        original_use_fallback_addresses(self)
        addr_map = dict(getattr(self.parser, "address_to_field", {}) or {})
        addr_map[IFEI_RPM_L_ADDR] = (IFEI_RPM_L_FIELD, IFEI_RPM_L_LEN)
        self.parser.inject_address_map(addr_map)
        self._addr_map_built = True
        print(
            f"[DCS-BIOS] Injected IFEI RPM fallback: "
            f"{IFEI_RPM_L_FIELD}@0x{IFEI_RPM_L_ADDR:04X} len={IFEI_RPM_L_LEN}"
        )

    DCSBIOSReceiver._parse_addresses_h = _parse_addresses_h_with_ifei
    DCSBIOSReceiver._use_fallback_addresses = _use_fallback_addresses_with_ifei
