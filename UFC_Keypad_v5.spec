# -*- mode: python ; coding: utf-8 -*-
# 模块化版打包 spec：入口 main.py，自动收集 ufc/ 包
from pathlib import Path

spec_dir = Path(__file__).resolve().parent


a = Analysis(
    [str(spec_dir / 'main.py')],
    pathex=[str(spec_dir)],
    binaries=[],
    datas=[
        (str(spec_dir / 'FA-18C_Hornet_Up_Front_Controller.ttf'), '.'),
        (str(spec_dir / 'ufc_config.json'), '.'),
        (str(spec_dir / 'dcs_export' / 'UFC_Keypad_CVTrim.lua'), 'dcs_export'),
    ],
    hiddenimports=[
        'ufc',
        'ufc.constants',
        'ufc.crashlog',
        'ufc.config',
        'ufc.fonts',
        'ufc.morse',
        'ufc.colors',
        'ufc.dcs_bios',
        'ufc.input',
        'ufc.widgets',
        'ufc.startup',
        'ufc.windowing',
        'ufc.ifei_rpm',
        'ufc.realtime_rpm',
        'ufc.cold_start',
        'ufc.cold_direct_entry',
        'ufc.cold_setup_split',
        'ufc.cold_ui_fixups',
        'ufc.cv_trim_auto',
        'ufc.direct_command_fixups',
        'ufc.hmd_osb_timing',
        'ufc.radar_ins_steps',
        'ufc.manual_setup_auto',
        'ufc.cold_lighting_auto',
        'ufc.cold_control_check',
        'ufc.startup_rpm_guard',
        'ufc.cold_prompt_polish',
        'ufc.ui',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter', 'tk', 'turtle', 'curses', 'PyQt5', 'PySide2', 'PySide6',
        'numpy', 'scipy', 'pandas', 'matplotlib', 'seaborn', 'plotly',
        'torch', 'tensorflow', 'keras',
        'pydoc_data', 'pdb', 'profile', 'unittest', 'doctest', 'pytest',
        'email', 'xml', 'xmlrpc', 'http', 'urllib',
        'sqlite3', 'cryptography', 'requests', 'urllib3',
        'win32api', 'win32con', 'win32gui', 'pywin32',
    ],
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
