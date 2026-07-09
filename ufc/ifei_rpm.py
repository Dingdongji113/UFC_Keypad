# -*- coding: utf-8 -*-
"""IFEI RPM DCS-BIOS support.

The FA-18C cold-start manager needs engine RPM to decide whether the aircraft
UFC/avionics should be considered available.  IFEI strings are a separate,
stable data path and can be read without relying on Addresses.h.

For DCS-Skunkworks DCS-BIOS FA-18C:
    IFEI_RPM_L address = 0x749E, length = 3
    IFEI_RPM_R address = 0x74A2, length = 3

This module patches DCSBIOSReceiver in-place before the receiver thread starts.
The hardcoded IFEI RPM addresses are injected after every address-learning path,
including when an external Addresses.h / JSON file is found but does not contain
IFEI_RPM_L/R.
"""
from __future__ import annotations

import os
import re

from ufc.dcs_bios import DCSBIOSReceiver


IFEI_RPM_L_FIELD = "IFEI_RPM_L"
IFEI_RPM_L_INTERNAL = "left_engine_rpm"
IFEI_RPM_L_ADDR = 0x749E
IFEI_RPM_L_LEN = 3

IFEI_RPM_R_FIELD = "IFEI_RPM_R"
IFEI_RPM_R_INTERNAL = "right_engine_rpm"
IFEI_RPM_R_ADDR = 0x74A2
IFEI_RPM_R_LEN = 3

_RPM_FIELDS = {
    IFEI_RPM_L_FIELD: (IFEI_RPM_L_INTERNAL, IFEI_RPM_L_ADDR, IFEI_RPM_L_LEN),
    IFEI_RPM_R_FIELD: (IFEI_RPM_R_INTERNAL, IFEI_RPM_R_ADDR, IFEI_RPM_R_LEN),
}


def _force_inject_ifei_rpm_addresses(receiver: DCSBIOSReceiver, source: str) -> None:
    """Always add hardcoded IFEI RPM string fields to the receiver parser."""
    addr_map = dict(getattr(receiver.parser, "address_to_field", {}) or {})
    changed = False
    for field_name, (_internal, addr, length) in _RPM_FIELDS.items():
        expected = (field_name, length)
        if addr_map.get(addr) != expected:
            addr_map[addr] = expected
            changed = True
    receiver.parser.inject_address_map(addr_map)
    receiver._addr_map_built = True
    if changed:
        print(
            f"[DCS-BIOS] Forced IFEI RPM addresses after {source}: "
            f"{IFEI_RPM_L_FIELD}@0x{IFEI_RPM_L_ADDR:04X} len={IFEI_RPM_L_LEN}, "
            f"{IFEI_RPM_R_FIELD}@0x{IFEI_RPM_R_ADDR:04X} len={IFEI_RPM_R_LEN}"
        )


def install_ifei_rpm_fallback() -> None:
    """Install left/right engine RPM parsing and hardcoded addresses."""
    for field_name, (internal_name, _addr, length) in _RPM_FIELDS.items():
        DCSBIOSReceiver.UFC_FIELDS[field_name] = (internal_name, None, length)
        DCSBIOSReceiver.KNOWN_FIELDS[field_name] = length
    DCSBIOSReceiver._INTERNAL_TO_BIOS = {}

    if getattr(DCSBIOSReceiver, "_ifei_rpm_fallback_installed", False):
        return
    DCSBIOSReceiver._ifei_rpm_fallback_installed = True

    original_parse_addresses_h = DCSBIOSReceiver._parse_addresses_h
    original_use_fallback_addresses = DCSBIOSReceiver._use_fallback_addresses
    original_learn_addresses = DCSBIOSReceiver._learn_addresses

    @classmethod
    def _parse_addresses_h_with_ifei(cls, path: str):
        addr_map = original_parse_addresses_h(path)
        if not path or not os.path.exists(path):
            return addr_map
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    m = re.match(
                        r"#define\s+FA_18C_hornet_(IFEI_RPM_[LR])_A\s+(0x[0-9A-Fa-f]+)",
                        line.strip(),
                    )
                    if m:
                        field_name = m.group(1)
                        if field_name in _RPM_FIELDS:
                            _internal, _fallback_addr, length = _RPM_FIELDS[field_name]
                            addr_map[int(m.group(2), 16)] = (field_name, length)
        except Exception:
            pass
        return addr_map

    def _use_fallback_addresses_with_ifei(self):
        original_use_fallback_addresses(self)
        _force_inject_ifei_rpm_addresses(self, "fallback address map")

    def _learn_addresses_with_ifei(self):
        result = original_learn_addresses(self)
        # Critical: external Addresses.h / JSON may exist but omit IFEI_RPM_L/R.
        # The cold-start manager must still receive RPM callbacks, so inject the
        # hardcoded IFEI addresses after every successful or fallback learn path.
        _force_inject_ifei_rpm_addresses(self, "address learning")
        return result

    DCSBIOSReceiver._parse_addresses_h = _parse_addresses_h_with_ifei
    DCSBIOSReceiver._use_fallback_addresses = _use_fallback_addresses_with_ifei
    DCSBIOSReceiver._learn_addresses = _learn_addresses_with_ifei
