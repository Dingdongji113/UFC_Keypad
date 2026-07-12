# -*- coding: utf-8 -*-
"""Authoritative SYSTEM 4 control and feedback mapping.

The values here are taken from the locally installed DCS F/A-18C
``clickabledata.lua`` and DCS-BIOS ``FA-18C_hornet.lua``/``Addresses.h``.
Keeping the mapping outside the layout prevents safety-sensitive command
details from being duplicated in UI code.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class ControlMapping:
    identifier: str
    kind: str
    labels: Tuple[str, ...] = ()
    values: Tuple[object, ...] = ()
    feedback: Optional[str] = None
    device: Optional[int] = None
    command: Optional[int] = None
    argument: Optional[int] = None
    address: Optional[int] = None
    mask: int = 0xFFFF
    shift: int = 0


def _m(identifier: str, kind: str, labels=(), values=(), *, device=None,
       command=None, argument=None, address=None, mask=0xFFFF, shift=0,
       feedback=None) -> ControlMapping:
    return ControlMapping(
        identifier=identifier,
        kind=kind,
        labels=tuple(labels),
        values=tuple(values),
        feedback=feedback or identifier.lower(),
        device=device,
        command=command,
        argument=argument,
        address=address,
        mask=mask,
        shift=shift,
    )


CONTROLS = {
    # SYSTEM 4A - HUD / NAV
    "hud_rej": _m("HUD_SYM_REJ_SW", "stable3", ("NORM", "REJ 1", "REJ 2"), (0, 1, 2),
                  device=34, command=3001, argument=140, address=0x742C, mask=0x0600, shift=9),
    "hud_mode": _m("HUD_SYM_BRT_SELECT", "stable2", ("DAY", "NIGHT"), (0, 1),
                   device=34, command=3003, argument=142, address=0x742C, mask=0x0800, shift=11),
    "hud_alt": _m("HUD_ALT_SW", "stable2", ("BARO", "RDR"), (0, 1),
                  device=34, command=3008, argument=147, address=0x742C, mask=0x4000, shift=14),
    "hud_att": _m("HUD_ATT_SW", "stable3", ("INS", "AUTO", "STBY"), (0, 1, 2),
                  device=34, command=3009, argument=148, address=0x742E, mask=0x0300, shift=8),
    "hud_video": _m("HUD_VIDEO_CONTROL_SW", "stable3", ("W/B", "VID", "OFF"), (0, 1, 2),
                    device=34, command=3005, argument=144, address=0x742C, mask=0x3000, shift=12),
    "hud_brt": _m("HUD_SYM_BRT", "analog", device=34, command=3002, argument=141, address=0x7458),
    "hud_black": _m("HUD_BLACK_LVL", "analog", device=34, command=3004, argument=143, address=0x745A),
    "hud_balance": _m("HUD_BALANCE", "analog", device=34, command=3006, argument=145, address=0x745C),
    "hud_aoa": _m("HUD_AOA_INDEXER", "analog", device=34, command=3007, argument=146, address=0x745E),
    "adf": _m("UFC_ADF", "stable3", ("1", "OFF", "2"), (0, 1, 2),
              device=25, command=3016, argument=107, address=0x7416, mask=0x00C0, shift=6),

    # SYSTEM 4A - AMPCD. Bottom bezel is PB15..PB11 from left to right.
    "ampcd_brt": _m("AMPCD_BRT_CTL", "analog", device=37, command=3001, argument=203, address=0x74E0),
    "ampcd_mode": _m("AMPCD_NIGHT_DAY", "stable3", ("NGT", "AUTO", "DAY"), (0, 1, 2),
                    device=37, command=3002, argument=177, address=0x7466, mask=0x6000, shift=13),
    "ampcd_sym": _m("AMPCD_SYM_SW", "spring3", ("-", "CTR", "+"), (0, 1, 2),
                   device=37, command=3004, argument=179, address=0x746C, mask=0x0300, shift=8),
    "ampcd_cont": _m("AMPCD_CONT_SW", "spring3", ("-", "CTR", "+"), (0, 1, 2),
                    device=37, command=3006, argument=182, address=0x746C, mask=0x0C00, shift=10),
    "ampcd_gain": _m("AMPCD_GAIN_SW", "spring3", ("-", "CTR", "+"), (0, 1, 2),
                    device=37, command=3008, argument=180, address=0x746C, mask=0x3000, shift=12),
    "hdg": _m("LEFT_DDI_HDG_SW", "rocker", ("-", "CTR", "+"), ("DEC", None, "INC"),
              device=35, command=3004, argument=312, feedback=None),
    "crs": _m("LEFT_DDI_CRS_SW", "rocker", ("-", "CTR", "+"), ("DEC", None, "INC"),
              device=35, command=3006, argument=313, feedback=None),
    **{
        f"pb{number}": _m(f"AMPCD_PB_{number}", "button", device=37,
                           command=3010 + number, argument=182 + number, feedback=None)
        for number in range(11, 16)
    },

    # SYSTEM 4B - ALR-67
    "rwr_power": _m("RWR_POWER_BTN", "power_button", device=53, command=3001, argument=277,
                    feedback="rwr_lower_lt"),
    "rwr_display": _m("RWR_DISPLAY_BTN", "button", device=53, command=3002, argument=275,
                      feedback="rwr_display_lt"),
    "rwr_special": _m("RWR_SPECIAL_BTN", "button", device=53, command=3003, argument=272,
                      feedback="rwr_special_lt"),
    "rwr_offset": _m("RWR_OFFSET_BTN", "button", device=53, command=3004, argument=269,
                     feedback="rwr_offset_lt"),
    "rwr_bit": _m("RWR_BIT_BTN", "button", device=53, command=3005, argument=266,
                  feedback="rwr_bit_lt"),

    # SYSTEM 4B - ECM / release / jettison
    "ecm_mode": _m("ECM_MODE_SW", "detent5", ("OFF", "STBY", "BIT", "REC", "XMIT"), range(5),
                   device=66, command=3001, argument=248, address=0x7488, mask=0x0700, shift=8),
    "dispenser": _m("CMSD_DISPENSE_SW", "stable3", ("OFF", "ON", "BYPASS"), (0, 1, 2),
                    device=54, command=3001, argument=517, address=0x7484, mask=0x6000, shift=13),
    "ecm_jett": _m("CMSD_JET_SEL_BTN", "guarded", device=54, command=3003, argument=515, feedback=None),
    "aux_rel": _m("AUX_REL_SW", "confirmed2", ("NORM", "ENABLE"), (0, 1),
                  device=23, command=3012, argument=258, address=0x7488, mask=0x0800, shift=11),
    "emer_jett": _m("EMER_JETT_BTN", "armed_guarded", device=23, command=3004, argument=50, feedback=None),
}


# Additional state lamps do not have user controls.
FEEDBACK_FIELDS = {
    "rwr_lower_lt": (0x7498, 0x1000, 12),
    "rwr_display_lt": (0x7498, 0x4000, 14),
    "rwr_special_en_lt": (0x7498, 0x8000, 15),
    "rwr_special_lt": (0x749C, 0x0100, 8),
    "rwr_offset_lt": (0x749C, 0x0400, 10),
    "rwr_bit_lt": (0x749C, 0x1000, 12),
}


AMPCD_BOTTOM_LEFT_TO_RIGHT = (15, 14, 13, 12, 11)


def integer_feedback_fields():
    fields = dict(FEEDBACK_FIELDS)
    for spec in CONTROLS.values():
        if spec.address is not None and spec.kind != "analog":
            fields[spec.feedback] = (spec.address, spec.mask, spec.shift)
    return fields


def analog_feedback_fields():
    return {
        spec.feedback: spec.address
        for spec in CONTROLS.values()
        if spec.kind == "analog" and spec.address is not None
    }
