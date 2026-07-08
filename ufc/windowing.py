# -*- coding: utf-8 -*-
"""窗口显示器应用补丁。

修复现象：UFC 面板整体下移约 30px、底部显示不全。

原因：原 apply_screen() 在 showFullScreen() 之后再 setWindowFlag()，Qt 在已显示窗口上
修改 window flags 会重建窗口，随后 show() 可能把全屏态退回普通带标题栏窗口。标题栏
高度约 30px，表现为内容整体下移且底部被裁切。

这里以运行时 monkey patch 的方式替换 SettingsWindow.apply_screen，避免直接改动巨大的
ui.py 文件。
"""
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QApplication

from ufc.constants import WIN_H, WIN_W


def patch_settings_window_apply_screen(SettingsWindowClass):
    """替换 SettingsWindow.apply_screen，使全屏窗口先设 flag 后 show。"""

    def apply_screen(self):
        idx = self.screen_combo.currentData()
        if idx is None:
            return

        screens = QApplication.screens()
        if idx >= len(screens):
            self.status_label.setText("所选显示器不存在!")
            return

        screen = screens[idx]
        geo = screen.geometry()
        fullscreen = self.fullscreen_cb.isChecked()
        always_top = self.always_top_cb.isChecked()

        panel = self.key_panel

        # 必须先隐藏，再调整 flags。Qt 对已显示窗口 setWindowFlag 会重建窗口，
        # 如果发生在 showFullScreen() 之后，会丢失全屏状态并留下标题栏偏移。
        panel.hide()
        panel.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, always_top)
        panel.setWindowFlag(Qt.WindowType.FramelessWindowHint, fullscreen)

        if fullscreen:
            # 先给出目标屏幕 geometry，再 showFullScreen。之后再延迟校正一次，
            # 防止 Windows/Qt 在多显示器和 DPI 缩放下返回普通窗口位置。
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

        self.status_label.setText(
            f"已输出到显示器 {idx}: {screen.name()} "
            f"{'全屏' if fullscreen else '窗口'}"
        )

    SettingsWindowClass.apply_screen = apply_screen
    return SettingsWindowClass
