# -*- coding: utf-8 -*-
"""Window placement patch for reliable fullscreen output.

The patch keeps the existing SettingsWindow implementation intact while fixing
Qt flag ordering and providing localized status messages.
"""
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QApplication

from ufc.constants import WIN_H, WIN_W
from ufc.i18n import tr


def patch_settings_window_apply_screen(SettingsWindowClass):
    """Replace SettingsWindow.apply_screen with stable fullscreen placement."""

    def apply_screen(self):
        idx = self.screen_combo.currentData()
        if idx is None:
            return

        screens = QApplication.screens()
        if idx >= len(screens):
            self.status_label.setText(tr("settings.screen.missing"))
            return

        screen = screens[idx]
        geo = screen.geometry()
        fullscreen = self.fullscreen_cb.isChecked()
        always_top = self.always_top_cb.isChecked()

        panel = self.key_panel

        # Window flags must be changed while hidden. Changing them after
        # showFullScreen() can recreate the window and reintroduce a title-bar
        # offset of roughly 30 px.
        panel.hide()
        panel.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, always_top)
        panel.setWindowFlag(Qt.WindowType.FramelessWindowHint, fullscreen)

        if fullscreen:
            panel.setGeometry(geo)
            panel.showFullScreen()

            def _enforce_fullscreen_geometry():
                panel.setGeometry(geo)
                panel.resize(geo.width(), geo.height())
                panel._rescale_children(panel.width(), panel.height())
                if hasattr(panel, "_startup_overlay") and panel._startup_overlay is not None:
                    panel._startup_overlay.setGeometry(panel.rect())
                    panel._startup_overlay.raise_()

            QTimer.singleShot(0, _enforce_fullscreen_geometry)
            QTimer.singleShot(100, _enforce_fullscreen_geometry)
        else:
            ratio = self.scale_spin.value()
            scaled_w = int(round(WIN_W * ratio))
            scaled_h = int(round(WIN_H * ratio))
            panel.setGeometry(geo.x(), geo.y(), scaled_w, scaled_h)
            panel.showNormal()
            panel._rescale_children(panel.width(), panel.height())
            if hasattr(panel, "_startup_overlay") and panel._startup_overlay is not None:
                panel._startup_overlay.setGeometry(panel.rect())
                panel._startup_overlay.raise_()

        mode_key = (
            "settings.screen.mode_fullscreen"
            if fullscreen
            else "settings.screen.mode_windowed"
        )
        self.status_label.setText(
            tr(
                "settings.screen.applied",
                index=idx,
                name=screen.name(),
                mode=tr(mode_key),
            )
        )

    SettingsWindowClass.apply_screen = apply_screen
    return SettingsWindowClass
