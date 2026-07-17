# -*- coding: utf-8 -*-
"""Localization adapter for the dynamically attached startup-style settings."""
from __future__ import annotations

from PyQt6.QtWidgets import QGroupBox, QLabel

from ufc.i18n import tr
from ufc.startup import STARTUP_STYLE_ANIME_MILLENNIUM, STARTUP_STYLE_UFC_BIT


def _find_group(window, title):
    for group in window.findChildren(QGroupBox):
        if group.title() == title:
            return group
    return None


def _find_label(group, text):
    if group is None:
        return None
    for label in group.findChildren(QLabel):
        if label.text() == text:
            return label
    return None


def retranslate_startup_style_settings(settings_window):
    refs = getattr(settings_window, "_startup_i18n_refs", {})
    group = refs.get("group")
    label = refs.get("label")
    hint = refs.get("hint")
    combo = getattr(settings_window, "startup_style_combo", None)

    if group is not None:
        group.setTitle(tr("startup.group"))
    if label is not None:
        label.setText(tr("startup.style"))
    if hint is not None:
        hint.setText(tr("startup.hint"))

    if combo is not None:
        current = combo.currentData()
        combo.blockSignals(True)
        for i in range(combo.count()):
            value = combo.itemData(i)
            if value == STARTUP_STYLE_UFC_BIT:
                combo.setItemText(i, tr("startup.option.ufc_bit"))
            elif value == STARTUP_STYLE_ANIME_MILLENNIUM:
                combo.setItemText(i, tr("startup.option.anime"))
        restore = combo.findData(current)
        if restore >= 0:
            combo.setCurrentIndex(restore)
        combo.blockSignals(False)


def attach_startup_settings_i18n(settings_window):
    """Capture the existing startup settings and add live retranslation."""
    if getattr(settings_window, "_startup_settings_i18n_attached", False):
        retranslate_startup_style_settings(settings_window)
        return
    settings_window._startup_settings_i18n_attached = True

    group = _find_group(settings_window, "启动动画")
    label = _find_label(group, "风格:")
    hint = _find_label(group, "切换后立即预览，并保存为下次启动默认")
    settings_window._startup_i18n_refs = {
        "group": group,
        "label": label,
        "hint": hint,
    }

    combo = getattr(settings_window, "startup_style_combo", None)
    if combo is not None:
        def _localized_status(_index):
            if hasattr(settings_window, "status_label"):
                settings_window.status_label.setText(
                    tr("startup.changed", style=combo.currentText())
                )
        combo.currentIndexChanged.connect(_localized_status)

    retranslate_startup_style_settings(settings_window)
