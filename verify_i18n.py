# -*- coding: utf-8 -*-
"""Dependency-light verification for the UFC Keypad localization core."""
from ufc.i18n import (
    LANG_EN,
    LANG_SYSTEM,
    LANG_ZH,
    SUPPORTED_LANGUAGES,
    _TRANSLATIONS,
    language_option_label,
    normalize_language,
    tr,
)


def main():
    assert normalize_language("en") == LANG_EN
    assert normalize_language("en-US") == LANG_EN
    assert normalize_language("zh-CN") == LANG_ZH
    assert normalize_language("简体中文") == LANG_ZH
    assert normalize_language("auto") == LANG_SYSTEM
    assert normalize_language("unknown") == LANG_SYSTEM

    assert tr("settings.title", LANG_EN) == "UFC Keypad Settings"
    assert tr("settings.title", LANG_ZH) == "UFC Keypad 设置面板"
    assert tr(
        "settings.screen.item",
        LANG_EN,
        index=2,
        name="DISPLAY2",
        width=1024,
        height=600,
    ) == "Display 2: DISPLAY2 (1024x600)"
    assert tr(
        "settings.screen.item",
        LANG_ZH,
        index=2,
        name="DISPLAY2",
        width=1024,
        height=600,
    ) == "显示器 2: DISPLAY2 (1024x600)"

    assert language_option_label(LANG_SYSTEM, LANG_EN) == "System"
    assert language_option_label(LANG_SYSTEM, LANG_ZH) == "跟随系统"
    assert language_option_label(LANG_ZH, LANG_EN) == "Simplified Chinese"

    for key, values in _TRANSLATIONS.items():
        assert LANG_EN in values, f"missing English translation: {key}"
        assert LANG_ZH in values, f"missing Chinese translation: {key}"
        assert values[LANG_EN].strip(), f"empty English translation: {key}"
        assert values[LANG_ZH].strip(), f"empty Chinese translation: {key}"

    assert set(SUPPORTED_LANGUAGES) == {LANG_SYSTEM, LANG_EN, LANG_ZH}
    print("ALL I18N CHECKS PASSED")


if __name__ == "__main__":
    main()
