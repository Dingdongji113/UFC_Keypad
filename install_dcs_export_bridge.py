# -*- coding: utf-8 -*-
"""Install UFC_Keypad's DCS Export.lua bridge.

This script copies dcs_export/UFC_Keypad_CVTrim.lua into every detected
Saved Games\DCS*\Scripts directory and appends the required dofile(...) line to
Export.lua with a backup.

Usage:
    python install_dcs_export_bridge.py

It is intentionally conservative: existing Export.lua content is preserved, a
.timestamp.bak backup is created, and the dofile line is not duplicated.
"""
from __future__ import annotations

import datetime as _dt
import os
import shutil
from pathlib import Path

BRIDGE_NAME = "UFC_Keypad_CVTrim.lua"
DOFILE_LINE = "dofile(lfs.writedir() .. [[Scripts\\UFC_Keypad_CVTrim.lua]])"


def _repo_root() -> Path:
    return Path(__file__).resolve().parent


def _saved_games_root() -> Path:
    userprofile = os.environ.get("USERPROFILE")
    if not userprofile:
        raise RuntimeError("USERPROFILE is not set; cannot locate Saved Games")
    return Path(userprofile) / "Saved Games"


def _candidate_dcs_dirs() -> list[Path]:
    root = _saved_games_root()
    if not root.exists():
        return []
    candidates = []
    for child in root.iterdir():
        if not child.is_dir():
            continue
        name = child.name.lower()
        if name == "dcs" or name.startswith("dcs."):
            candidates.append(child)
    # Prefer openbeta first when both exist, but install to all detected dirs.
    candidates.sort(key=lambda p: ("openbeta" not in p.name.lower(), p.name.lower()))
    return candidates


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    for enc in ("utf-8-sig", "utf-8", "gbk"):
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    return path.read_text(errors="ignore")


def _write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def install_to(dcs_dir: Path) -> tuple[bool, str]:
    source = _repo_root() / "dcs_export" / BRIDGE_NAME
    if not source.exists():
        return False, f"missing source: {source}"

    scripts_dir = dcs_dir / "Scripts"
    logs_dir = dcs_dir / "Logs"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    target = scripts_dir / BRIDGE_NAME
    shutil.copy2(source, target)

    export_lua = scripts_dir / "Export.lua"
    old_text = _read_text(export_lua)
    normalized = old_text.replace("/", "\\")
    already = "UFC_Keypad_CVTrim.lua" in normalized

    if already:
        return True, f"installed bridge, Export.lua already references it: {dcs_dir}"

    if export_lua.exists():
        stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = export_lua.with_name(f"Export.lua.{stamp}.bak")
        shutil.copy2(export_lua, backup)
    else:
        backup = None

    new_text = old_text
    if new_text and not new_text.endswith(("\n", "\r")):
        new_text += "\n"
    new_text += "\n-- UFC_Keypad bridge for CV trim and direct cockpit commands\n"
    new_text += DOFILE_LINE + "\n"
    _write_text(export_lua, new_text)

    backup_msg = f", backup={backup.name}" if backup else ", created Export.lua"
    return True, f"installed bridge and patched Export.lua: {dcs_dir}{backup_msg}"


def main() -> int:
    print("UFC_Keypad DCS Export bridge installer")
    print("=" * 58)
    print(f"Repo: {_repo_root()}")
    print(f"Saved Games: {_saved_games_root()}")

    candidates = _candidate_dcs_dirs()
    if not candidates:
        print("[FAIL] No Saved Games\\DCS* directory found.")
        return 2

    ok_count = 0
    for dcs_dir in candidates:
        ok, message = install_to(dcs_dir)
        print(("[OK] " if ok else "[FAIL] ") + message)
        ok_count += 1 if ok else 0

    print("=" * 58)
    if ok_count:
        print("Next steps:")
        print("1. Restart DCS completely.")
        print("2. Enter an F/A-18C mission.")
        print("3. Check this file exists and updates:")
        for dcs_dir in candidates:
            print(f"   {dcs_dir / 'Logs' / 'UFC_Keypad_CVTrim.log'}")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
