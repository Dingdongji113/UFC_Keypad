# -*- coding: utf-8 -*-
"""Runtime localization patch for the existing SettingsWindow.

This module keeps the large legacy ui.py stable. It captures the settings
widgets after they are created, inserts a language selector, and retranslates
all application-facing settings text in place.
"""
from __future__ import annotations

from PyQt6.QtWidgets import QApplication, QComboBox, QGroupBox, QHBoxLayout, QLabel

from ufc.i18n import (
    LANG_EN,
    LANG_SYSTEM,
    LANG_ZH,
    configured_language,
    language_option_label,
    normalize_language,
    set_configured_language,
    tr,
)


def _find_by_text(parent, widget_type, text):
    for widget in parent.findChildren(widget_type):
        try:
            if widget.text() == text:
                return widget
        except Exception:
            continue
    return None


def _find_group(parent, title):
    for group in parent.findChildren(QGroupBox):
        if group.title() == title:
            return group
    return None


def _capture_base_widgets(window):
    window._i18n_refs = {
        "title": _find_by_text(window, QLabel, "UFC Keypad 设置面板"),
        "screen_group": _find_group(window, "显示器选择"),
        "screen_output": _find_by_text(window, QLabel, "输出到显示器:"),
        "fullscreen": getattr(window, "fullscreen_cb", None),
        "always_top": getattr(window, "always_top_cb", None),
        "scale_label": _find_by_text(window, QLabel, "倍率:"),
        "apply_screen": getattr(window, "apply_screen_btn", None),
        "refresh_screen": getattr(window, "refresh_screen_btn", None),
        "touch_group": _find_group(window, "触控隔离 (副屏触摸不抢主屏鼠标)"),
        "native_touch": getattr(window, "native_touch_cb", None),
        "log_group": _find_group(window, "按键输入记录 (最近 50 条)"),
    }


def _insert_language_group(window):
    layout = window.layout()
    if layout is None or hasattr(window, "language_combo"):
        return

    group = QGroupBox()
    row = QHBoxLayout(group)
    label = QLabel()
    combo = QComboBox()
    combo.setMinimumWidth(190)
    hint = QLabel()
    hint.setStyleSheet("color: #8888aa; font-size: 11px;")

    for value in (LANG_SYSTEM, LANG_EN, LANG_ZH):
        combo.addItem(value, userData=value)

    selected = configured_language()
    index = combo.findData(selected)
    combo.setCurrentIndex(index if index >= 0 else 0)

    row.addWidget(label)
    row.addWidget(combo)
    row.addWidget(hint)
    row.addStretch()

    # The title is item 0 in the current settings layout.
    layout.insertWidget(min(1, layout.count()), group)

    window.language_group = group
    window.language_label = label
    window.language_combo = combo
    window.language_hint = hint

    def _language_changed(index):
        selected_value = normalize_language(combo.itemData(index))
        set_configured_language(selected_value)
        retranslate_settings_window(window)
        window.refresh_screen_list()
        try:
            from ufc.startup_i18n import retranslate_startup_style_settings
            retranslate_startup_style_settings(window)
        except Exception:
            pass

    combo.currentIndexChanged.connect(_language_changed)


def retranslate_settings_window(window):
    """Apply the configured language to an existing SettingsWindow instance."""
    refs = getattr(window, "_i18n_refs", {})

    def set_text(name, key):
        widget = refs.get(name)
        if widget is not None:
            widget.setText(tr(key))

    title = refs.get("title")
    if title is not None:
        title.setText(tr("settings.title"))

    screen_group = refs.get("screen_group")
    if screen_group is not None:
        screen_group.setTitle(tr("settings.screen.group"))
    set_text("screen_output", "settings.screen.output")
    set_text("fullscreen", "settings.screen.fullscreen")
    set_text("always_top", "settings.screen.always_top")
    set_text("scale_label", "settings.screen.scale")
    set_text("apply_screen", "settings.screen.apply")
    set_text("refresh_screen", "settings.screen.refresh")

    scale_spin = getattr(window, "scale_spin", None)
    if scale_spin is not None:
        scale_spin.setToolTip(tr("settings.screen.scale_tip"))

    touch_group = refs.get("touch_group")
    if touch_group is not None:
        touch_group.setTitle(tr("settings.touch.group"))
    native_touch = refs.get("native_touch")
    if native_touch is not None:
        native_touch.setText(tr("settings.touch.enable"))
        native_touch.setToolTip(tr("settings.touch.tip"))

    log_group = refs.get("log_group")
    if log_group is not None:
        log_group.setTitle(tr("settings.log.group"))

    language_group = getattr(window, "language_group", None)
    if language_group is not None:
        language_group.setTitle(tr("settings.language.group"))
    language_label = getattr(window, "language_label", None)
    if language_label is not None:
        language_label.setText(tr("settings.language.label"))
    language_hint = getattr(window, "language_hint", None)
    if language_hint is not None:
        language_hint.setText(tr("settings.language.hint"))

    combo = getattr(window, "language_combo", None)
    if combo is not None:
        selected = combo.currentData()
        combo.blockSignals(True)
        for i in range(combo.count()):
            option = combo.itemData(i)
            combo.setItemText(i, language_option_label(option))
        restore = combo.findData(selected)
        if restore >= 0:
            combo.setCurrentIndex(restore)
        combo.blockSignals(False)


def install_settings_i18n(SettingsWindowClass):
    """Patch SettingsWindow before construction and add live EN/ZH switching."""
    if getattr(SettingsWindowClass, "_settings_i18n_installed", False):
        return SettingsWindowClass
    SettingsWindowClass._settings_i18n_installed = True

    original_init_ui = SettingsWindowClass.init_ui

    def init_ui(self):
        original_init_ui(self)
        _capture_base_widgets(self)
        _insert_language_group(self)
        retranslate_settings_window(self)

    def refresh_screen_list(self):
        current = self.screen_combo.currentData()
        self.screen_combo.clear()
        screens = QApplication.screens()
        for i, screen in enumerate(screens):
            geo = screen.geometry()
            self.screen_combo.addItem(
                tr(
                    "settings.screen.item",
                    index=i,
                    name=screen.name(),
                    width=geo.width(),
                    height=geo.height(),
                ),
                userData=i,
            )
        restore = self.screen_combo.findData(current)
        if restore >= 0:
            self.screen_combo.setCurrentIndex(restore)

    def _on_native_touch_toggled(self, checked):
        self.key_panel.enable_native_touch(checked)
        self.status_label.setText(
            tr("settings.touch.enabled") if checked else tr("settings.touch.disabled")
        )

    SettingsWindowClass.init_ui = init_ui
    SettingsWindowClass.refresh_screen_list = refresh_screen_list
    SettingsWindowClass._on_native_touch_toggled = _on_native_touch_toggled
    return SettingsWindowClass
