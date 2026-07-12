# SYSTEM 4 Mapping Baseline

Sources checked on 2026-07-13:

- `D:\DCS World\Mods\aircraft\FA-18C\Cockpit\Scripts\clickabledata.lua`
- `D:\DCS World\Mods\aircraft\FA-18C\Input\FA-18C\keyboard\default.lua`
- `%USERPROFILE%\Saved Games\DCS\Scripts\DCS-BIOS\Scripts\DCS-BIOS\lib\modules\aircraft_modules\FA-18C_hornet.lua`
- `%USERPROFILE%\Saved Games\DCS\Scripts\DCS-BIOS\doc\Addresses.h`

The executable mapping is centralized in `ufc/system4_mapping.py`.

## Control source table

| Control group | DCS-BIOS identifier | Device | Command | Argument |
|---|---|---:|---:|---:|
| HUD reject | `HUD_SYM_REJ_SW` | 34 | 3001 | 140 |
| HUD brightness | `HUD_SYM_BRT` | 34 | 3002 | 141 |
| HUD day/night | `HUD_SYM_BRT_SELECT` | 34 | 3003 | 142 |
| HUD black level | `HUD_BLACK_LVL` | 34 | 3004 | 143 |
| HUD video | `HUD_VIDEO_CONTROL_SW` | 34 | 3005 | 144 |
| HUD balance | `HUD_BALANCE` | 34 | 3006 | 145 |
| AOA indexer brightness | `HUD_AOA_INDEXER` | 34 | 3007 | 146 |
| HUD altitude source | `HUD_ALT_SW` | 34 | 3008 | 147 |
| HUD attitude source | `HUD_ATT_SW` | 34 | 3009 | 148 |
| ADF | `UFC_ADF` | 25 | 3016 | 107 |
| AMPCD brightness/mode | `AMPCD_BRT_CTL`, `AMPCD_NIGHT_DAY` | 37 | 3001, 3002 | 203, 177 |
| AMPCD SYM/CONT/GAIN | `AMPCD_SYM_SW`, `AMPCD_CONT_SW`, `AMPCD_GAIN_SW` | 37 | 3004, 3006, 3008 | 179, 182, 180 |
| AMPCD bottom PB11–15 | `AMPCD_PB_11` … `AMPCD_PB_15` | 37 | 3021–3025 | 193–197 |
| HDG/CRS rockers | `LEFT_DDI_HDG_SW`, `LEFT_DDI_CRS_SW` | 35 | 3004/3005, 3006/3007 | 312, 313 |
| ALR-67 buttons | `RWR_POWER_BTN` … `RWR_BIT_BTN` | 53 | 3001–3005 | 277, 275, 272, 269, 266 |
| DISPENSER | `CMSD_DISPENSE_SW` | 54 | 3001 | 517 |
| ECM JETT | `CMSD_JET_SEL_BTN` | 54 | 3003 | 515 |
| ECM mode | `ECM_MODE_SW` | 66 | 3001 | 248 |
| AUX release | `AUX_REL_SW` | 23 | 3012 | 258 |
| Emergency jettison | `EMER_JETT_BTN` | 23 | 3004 | 50 |

ALR-67 lamp feedback comes from arguments 276, 274, 271/270, 268, and 265. Exact DCS-BIOS addresses and masks are stored beside the control definitions in `system4_mapping.py`.

## Verified conventions

- AMPCD bottom bezel is rendered left-to-right as PB15, PB14, PB13, PB12, PB11. DCS clickable arguments 193 through 197 and commands 3021 through 3025 identify PB11 through PB15.
- AMPCD HDG and CRS use DCS-BIOS rocker commands `DEC` on the left and `INC` on the right; the UI returns to center on release.
- AMPCD SYM, CONT, and GAIN use states 0/1/2 and send state 1 on release.
- ECM mode raw detents are OFF=0, STBY=1, BIT=2, REC=3, XMIT=4. The DCS keyboard mapping independently confirms cockpit values 0.0 through 0.4.
- DISPENSER raw detents are OFF=0, ON=1, BYPASS=2. The DCS keyboard mapping confirms cockpit values 0.0, 0.1, and 0.2.
- AUX REL is NORM=0 and ENABLE=1.
- ALR-67 lamps are independent feedback fields. SPECIAL displays the union of SPECIAL and SPECIAL ENABLE lamps.

## Safety contract

- ECM JETT requires a continuous 1.0 second hold before one press/release pulse.
- AUX REL requires a second confirmation before ENABLE; returning to NORM is immediate.
- EMER JETT requires ARM, then a continuous 1.5 second hold inside a 3 second arm window.
- Page change, reset, DCS disconnect, timeout, and application close disarm every pending dangerous action.

No device or command number is inferred in the UI layout; all are sourced from the files listed above.
