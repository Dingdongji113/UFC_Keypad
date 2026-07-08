# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

spec_dir = Path(__file__).resolve().parent


a = Analysis(
    [str(spec_dir / 'ufc_keypad.py')],
    pathex=[str(spec_dir)],
    binaries=[],
    datas=[(str(spec_dir / 'FA-18C_Hornet_Up_Front_Controller.ttf'), '.')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='UFC_Keypad_v5',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(spec_dir / 'ufc_icon.ico'),
)
