# -*- coding: utf-8 -*-
"""Off-screen integration checks for live SettingsWindow localization."""
from __future__ import annotations

import os
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QApplication, QGroupBox, QWidget

import ufc.config as config_module
from ufc.i18n import LANG_EN, LANG_ZH
from ufc.i18n_ui import install_settings_i18n
from ufc.startup import attach_startup_style_settings
from ufc.startup_i18n import attach_startup_settings_i18n
from ufc.ui import SettingsWindow
from ufc.windowing import patch_settings_window_apply_screen


class FakePanel(QWidget):
    keyLogUpdated = pyqtSignal(str, str)

    def __init__(self):
        super().__init__()
        self._key_press_log = []
        self.touch_enabled = False
        self._startup_overlay = None

    def enable_native_touch(self, checked):
        self.touch_enabled = bool(checked)

    def _rescale_children(self, _width, _height):
        pass


def group_titles(window):
    return {group.title() for group in window.findChildren(QGroupBox)}


def main():
    app = QApplication.instance() or QApplication([])

    with tempfile.TemporaryDirectory() as temp_dir:
        config_module.CONFIG_FILE = os.path.join(temp_dir, "ufc_config.json")

        patch_settings_window_apply_screen(SettingsWindow)
        install_settings_i18n(SettingsWindow)

        panel = FakePanel()
        settings = SettingsWindow(panel)
        attach_startup_style_settings(settings)
        attach_startup_settings_i18n(settings)
        app.processEvents()

        assert settings.language_combo.currentData() in ("system", LANG_EN, LANG_ZH)

        english_index = settings.language_combo.findData(LANG_EN)
        assert english_index >= 0
        settings.language_combo.setCurrentIndex(english_index)
        app.processEvents()

        assert settings.language_combo.currentData() == LANG_EN
        assert settings.findChildren(QGroupBox)
        assert "Display Output" in group_titles(settings)
        assert "Language" in group_titles(settings)
        assert "Startup Animation" in group_titles(settings)
        assert settings.apply_screen_btn.text() == "Apply Display"
        assert settings.refresh_screen_btn.text() == "Refresh"
        assert settings.fullscreen_cb.text() == "Fullscreen"
        assert settings.always_top_cb.text() == "Always on top"
        assert settings.startup_style_combo.itemText(0) == "UFC BIT (military self-test)"
        assert settings.startup_style_combo.itemText(1) == "Millennium-era Japanese anime"

        chinese_index = settings.language_combo.findData(LANG_ZH)
        assert chinese_index >= 0
        settings.language_combo.setCurrentIndex(chinese_index)
        app.processEvents()

        assert settings.language_combo.currentData() == LANG_ZH
        assert "显示器选择" in group_titles(settings)
        assert "语言" in group_titles(settings)
        assert "启动动画" in group_titles(settings)
        assert settings.apply_screen_btn.text() == "应用显示器"
        assert settings.refresh_screen_btn.text() == "刷新"
        assert settings.fullscreen_cb.text() == "全屏"
        assert settings.always_top_cb.text() == "置顶"

        settings.deleteLater()
        panel.deleteLater()
        app.processEvents()

    print("ALL I18N UI CHECKS PASSED")


if __name__ == "__main__":
    main()
