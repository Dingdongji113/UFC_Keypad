# -*- coding: utf-8 -*-
"""Small runtime localization layer for UFC Keypad.

The project deliberately keeps avionics labels and DCS control identifiers in
English.  This module localizes application chrome, settings, hints and status
messages without changing any DCS-BIOS behavior.
"""
from __future__ import annotations

import locale
import os
from typing import Dict

from ufc.config import load_config, save_config

LANG_SYSTEM = "system"
LANG_EN = "en_US"
LANG_ZH = "zh_CN"
DEFAULT_LANGUAGE = LANG_SYSTEM
SUPPORTED_LANGUAGES = (LANG_SYSTEM, LANG_EN, LANG_ZH)

_LANGUAGE_LABELS = {
    LANG_SYSTEM: {LANG_EN: "System", LANG_ZH: "跟随系统"},
    LANG_EN: {LANG_EN: "English", LANG_ZH: "English"},
    LANG_ZH: {LANG_EN: "Simplified Chinese", LANG_ZH: "简体中文"},
}

_TRANSLATIONS: Dict[str, Dict[str, str]] = {
    "settings.title": {
        LANG_EN: "UFC Keypad Settings",
        LANG_ZH: "UFC Keypad 设置面板",
    },
    "settings.language.group": {
        LANG_EN: "Language",
        LANG_ZH: "语言",
    },
    "settings.language.label": {
        LANG_EN: "Interface language:",
        LANG_ZH: "界面语言:",
    },
    "settings.language.hint": {
        LANG_EN: "Changes apply immediately and are saved for the next launch.",
        LANG_ZH: "切换后立即生效，并保存为下次启动默认。",
    },
    "settings.screen.group": {
        LANG_EN: "Display Output",
        LANG_ZH: "显示器选择",
    },
    "settings.screen.output": {
        LANG_EN: "Output display:",
        LANG_ZH: "输出到显示器:",
    },
    "settings.screen.fullscreen": {
        LANG_EN: "Fullscreen",
        LANG_ZH: "全屏",
    },
    "settings.screen.always_top": {
        LANG_EN: "Always on top",
        LANG_ZH: "置顶",
    },
    "settings.screen.scale": {
        LANG_EN: "Scale:",
        LANG_ZH: "倍率:",
    },
    "settings.screen.scale_tip": {
        LANG_EN: (
            "Window scale (windowed mode only)\n"
            "1.0 = native 1024×600\n"
            "1.5 = 1536×900\n"
            "Fullscreen scale follows the selected display resolution."
        ),
        LANG_ZH: (
            "窗口缩放倍率（仅非全屏模式有效）\n"
            "1.0 = 1024×600 原始尺寸\n"
            "1.5 = 1536×900\n"
            "全屏模式下倍率由屏幕分辨率决定"
        ),
    },
    "settings.screen.apply": {
        LANG_EN: "Apply Display",
        LANG_ZH: "应用显示器",
    },
    "settings.screen.refresh": {
        LANG_EN: "Refresh",
        LANG_ZH: "刷新",
    },
    "settings.screen.item": {
        LANG_EN: "Display {index}: {name} ({width}x{height})",
        LANG_ZH: "显示器 {index}: {name} ({width}x{height})",
    },
    "settings.screen.missing": {
        LANG_EN: "The selected display is no longer available.",
        LANG_ZH: "所选显示器不存在!",
    },
    "settings.screen.applied": {
        LANG_EN: "Output set to display {index}: {name} ({mode})",
        LANG_ZH: "已输出到显示器 {index}: {name} {mode}",
    },
    "settings.screen.mode_fullscreen": {
        LANG_EN: "fullscreen",
        LANG_ZH: "全屏",
    },
    "settings.screen.mode_windowed": {
        LANG_EN: "windowed",
        LANG_ZH: "窗口",
    },
    "settings.touch.group": {
        LANG_EN: "Touch Isolation (keep the main-screen pointer in DCS)",
        LANG_ZH: "触控隔离 (副屏触摸不抢主屏鼠标)",
    },
    "settings.touch.enable": {
        LANG_EN: "Enable native touch isolation (RegisterTouchWindow + FINETOUCH)",
        LANG_ZH: "启用原生触控隔离 (RegisterTouchWindow + FINETOUCH)",
    },
    "settings.touch.tip": {
        LANG_EN: (
            "Prevents Windows from converting secondary-display touch input into mouse events, "
            "so DCS does not lose focus.\n"
            "Touch input remains available to the UFC panel without moving the main-screen pointer.\n"
            "Administrator privileges may be required."
        ),
        LANG_ZH: (
            "阻止 Windows 将副屏触摸转换为鼠标事件，避免光标跳到副屏导致 DCS 失焦。\n"
            "启用后副屏触摸仅操作 UFC 面板，不会影响主屏游戏。\n"
            "⚠ 需要管理员权限运行才能生效。"
        ),
    },
    "settings.touch.enabled": {
        LANG_EN: "Native touch isolation enabled — touch will no longer take the mouse pointer.",
        LANG_ZH: "原生触控隔离已启用 — 触摸不再抢鼠标",
    },
    "settings.touch.disabled": {
        LANG_EN: "Native touch isolation disabled.",
        LANG_ZH: "原生触控隔离已关闭",
    },
    "settings.log.group": {
        LANG_EN: "Key Input Log (latest 50)",
        LANG_ZH: "按键输入记录 (最近 50 条)",
    },
    "startup.group": {
        LANG_EN: "Startup Animation",
        LANG_ZH: "启动动画",
    },
    "startup.style": {
        LANG_EN: "Style:",
        LANG_ZH: "风格:",
    },
    "startup.option.ufc_bit": {
        LANG_EN: "UFC BIT (military self-test)",
        LANG_ZH: "UFC BIT（军机自检风格）",
    },
    "startup.option.anime": {
        LANG_EN: "Millennium-era Japanese anime",
        LANG_ZH: "千禧日式动画风格",
    },
    "startup.hint": {
        LANG_EN: "Changes preview immediately and are saved for the next launch.",
        LANG_ZH: "切换后立即预览，并保存为下次启动默认",
    },
    "startup.changed": {
        LANG_EN: "Startup animation changed to: {style} (previewed and saved)",
        LANG_ZH: "启动动画已切换为: {style}（已立即替换并保存）",
    },
}


def normalize_language(value: object) -> str:
    text = str(value or "").strip()
    aliases = {
        "en": LANG_EN,
        "en-us": LANG_EN,
        "en_us": LANG_EN,
        "english": LANG_EN,
        "zh": LANG_ZH,
        "zh-cn": LANG_ZH,
        "zh_cn": LANG_ZH,
        "chinese": LANG_ZH,
        "简体中文": LANG_ZH,
        "auto": LANG_SYSTEM,
    }
    normalized = aliases.get(text.lower(), text)
    return normalized if normalized in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE


def system_language() -> str:
    candidates = []
    try:
        candidates.append(locale.getlocale()[0])
    except Exception:
        pass
    candidates.extend((os.environ.get("LANG"), os.environ.get("LC_ALL"), os.environ.get("LC_MESSAGES")))
    for value in candidates:
        if value and str(value).lower().replace("-", "_").startswith("zh"):
            return LANG_ZH
    return LANG_EN


def configured_language() -> str:
    cfg = load_config()
    return normalize_language(cfg.get("language", DEFAULT_LANGUAGE))


def active_language(configured: object = None) -> str:
    selected = normalize_language(configured if configured is not None else configured_language())
    return system_language() if selected == LANG_SYSTEM else selected


def set_configured_language(language: object) -> str:
    selected = normalize_language(language)
    cfg = load_config()
    cfg["language"] = selected
    save_config(cfg)
    return selected


def language_option_label(option: str, display_language: object = None) -> str:
    option = normalize_language(option)
    lang = active_language(display_language)
    return _LANGUAGE_LABELS[option][lang]


def tr(key: str, language: object = None, **values) -> str:
    lang = active_language(language)
    table = _TRANSLATIONS.get(key)
    if table is None:
        return key.format(**values) if values else key
    text = table.get(lang) or table.get(LANG_EN) or key
    return text.format(**values) if values else text
