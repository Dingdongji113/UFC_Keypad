# -*- coding: utf-8 -*-
"""自定义控件：UFCCell (可点击方块) / UFCBlank (带边框空白)"""
import os
import sys

from PyQt6.QtWidgets import (QFrame, QWidget, QLabel, QApplication,
                             QVBoxLayout, QSizePolicy, QScrollArea)
from PyQt6.QtCore import Qt, QRect, pyqtSignal, QTimer
from PyQt6 import QtCore, QtGui
from PyQt6.QtGui import (QColor, QFont, QPainter, QKeyEvent,
                         QMouseEvent, QCursor)

import ufc.colors as colors
from ufc.colors import (text_color_br, border_color_br, _dim,
                        hover_bg_br, pressed_bg_br,
                        TEXT_COLOR, BORDER_COLOR, HOVER_BG, PRESSED_BG)
from ufc.fonts import get_hornet_font
from ufc.constants import BG_COLOR, WIN_W, WIN_H
from ufc.dcs_bios import UFC_BIOS_MAP, _MIN_PRESS_MS, _send_release, send_dcs_bios

class UFCCell(QFrame):
    """UFC 按钮单元格 - 有边框可点击"""
    clicked = pyqtSignal(tuple)
    action_pressed = pyqtSignal(tuple)
    action_released = pyqtSignal(tuple)

    def __init__(self, text, pos, font_size=16, is_variable=False, bold=False, parent=None, no_feedback=False, var_align=None):
        super().__init__(parent)
        self.pos = pos
        self._no_feedback = no_feedback  # True → 不显示按压/触摸视觉反馈
        self._is_variable = is_variable  # 必须在 _refresh_stylesheet() 之前！Qt 事件可能提前触发
        # 可变显示文本对齐（None=默认居中, 如 AlignRight|TextDontClip）
        self._var_align = var_align
        self._bios_pressed = False  # 当前是否已发送 press(1) 等待 release(0)
        
        # 存储当前颜色（由 _apply_brightness 更新）
        self._tc = TEXT_COLOR
        self._bc = BORDER_COLOR
        self._hb = HOVER_BG
        self._pb = PRESSED_BG
        
        self._refresh_stylesheet()
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # 触摸屏支持
        self.setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents, True)
        self._touch_active = False

        if is_variable:
            # 可变显示单元格：用 QPainter 直接绘制文本
            self.label = None
            self._var_text = text
            self._var_font = get_hornet_font(font_size)
            self._var_font.setBold(bold)
            self._label_font = None
            self._label_font_size = font_size
            self._label_bold = bold
        else:
            layout = QVBoxLayout(self)
            layout.setContentsMargins(2, 2, 2, 2)
            layout.setSpacing(0)
            self.label = QLabel(text)
            self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.label.setWordWrap(True)
            self.label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            font = QFont("B612", font_size)
            font.setBold(bold)
            self.label.setFont(font)
            self.label.setStyleSheet(f"color: {self._tc}; background: transparent;")
            layout.addWidget(self.label)
            self._var_text = None
            self._var_font = None
            self._label_font = font
            self._label_font_size = font_size
            self._label_bold = bold

    def event(self, e):
        """触摸事件处理 + 视觉反馈。
        注意：return True 接受触摸会阻止 Qt 自动合成 mousePressEvent，
        所以 TouchBegin/TouchEnd 中直接应用/恢复样式并 emit clicked。"""
        t = e.type()
        # 诊断：OSB 相关格子（column 4 的可变显示区）打印触控事件
        if self._is_variable and self.pos is not None and self.pos[1] == 4:
            pass  # 第4行可变显示：跳过 TouchBegin/TouchEnd 日志（已移除调试打印）
        # ── 触控按下 → DCS-BIOS press ──
        if t == QtCore.QEvent.Type.TouchBegin:
            self._touch_active = True
            if not self._no_feedback:
                self.setStyleSheet(f"""
                    UFCCell {{ background-color: {self._pb}; border: 2px solid {self._bc}; border-radius: 0px; }}
                """)
            # 发送 DCS-BIOS press (1)
            if self.pos is not None:
                self.action_pressed.emit(self.pos)
                bios_entry = UFC_BIOS_MAP.get(self.pos)
                if isinstance(bios_entry, str):
                    send_dcs_bios(bios_entry, 1)
                    self._bios_pressed = True
            e.accept()
            return True
        # ── 触控移动 ──
        elif t == QtCore.QEvent.Type.TouchUpdate:
            e.accept()
            return True
        # ── 触控松开 → DCS-BIOS release (延迟保证分帧) → emit clicked ──
        elif t == QtCore.QEvent.Type.TouchEnd:
            self._touch_active = False
            if not self._no_feedback:
                self._refresh_stylesheet()
            if self.pos is not None:
                self.action_released.emit(self.pos)
                bios_entry = UFC_BIOS_MAP.get(self.pos)
                if isinstance(bios_entry, str) and self._bios_pressed:
                    identifier = bios_entry
                    QTimer.singleShot(_MIN_PRESS_MS, lambda id=identifier: _send_release(id))
                    self._bios_pressed = False
                elif isinstance(bios_entry, tuple):
                    identifier, value = bios_entry
                    send_dcs_bios(identifier, value)
                self.clicked.emit(self.pos)
            e.accept()
            return True
        return super().event(e)

    def contextMenuEvent(self, event):
        """触摸屏长按禁止右键菜单 / 右键菜单"""
        if self._touch_active:
            event.accept()  # 吃掉触摸产生的右键事件
        else:
            super().contextMenuEvent(event)

    def setText(self, text):
        """设置可变显示文本（仅 is_variable=True 时有效）"""
        if self._is_variable:
            self._var_text = text
            self.repaint()  # 强制立即重绘（亮度变化后 setText 立即生效）
        elif self.label:
            self.label.setText(text)

    def rescale_font(self, new_size):
        """缩放时更新字体大小，保持字体族不变"""
        if self._var_font is not None:
            self._var_font.setPointSize(new_size)
            self._label_font_size = new_size
            self.update()
        elif self.label is not None and self._label_font is not None:
            self._label_font.setPointSize(new_size)
            self._label_font_size = new_size
            self.label.setFont(self._label_font)
            self.update()

    def paintEvent(self, event):
        """可变显示单元格：QPainter 手动绘制。"""
        super().paintEvent(event)
        if not self._is_variable or self._var_font is None:
            return
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setFont(self._var_font)
        brightness = colors._CURRENT_BRIGHTNESS
        f = _dim(brightness)
        green = int(255 * f)
        painter.setPen(QtGui.QColor(0, green, 0))

        # ── scratchpad 长条：三字段独立渲染，不用拼接 ──
        if self._var_text == "__SCRATCHPAD__" and hasattr(self, '_scratchpad_parts') and self._scratchpad_parts:
            # 三字段宽度比例（按 UFC 实际布局）：str1=2ch, str2=2ch, number=8ch → 共12ch
            # 用字体等宽假设估算每字符宽度，实际用 fontMetrics 量
            metrics = QtGui.QFontMetrics(self._var_font)
            ch_w = metrics.horizontalAdvance('0')   # 数字0的宽度作为参考等宽宽度
            if ch_w == 0:
                ch_w = 22   # fallback
            h = self.height()
            baseline = (h + metrics.ascent() - metrics.descent()) // 2

            # str1: 左侧起始，左对齐，取2字符
            str1 = self._scratchpad_parts[0]
            if len(str1) < 2:
                str1 = str1.ljust(2)
            else:
                str1 = str1[:2]
            painter.drawText(6, baseline, str1)

            # str2: str1 后留一字符间距，左对齐，取2字符
            str2 = self._scratchpad_parts[1]
            if len(str2) < 2:
                str2 = str2.ljust(2)
            else:
                str2 = str2[:2]
            x2 = 6 + ch_w * 3   # str1 2ch + 1ch 间距
            painter.drawText(x2, baseline, str2)

            # number: 右对齐，最后一个数字固定在右侧边距
            num = self._scratchpad_parts[2]
            num = num.rjust(8)[-8:]
            num_rect = QRect(0, 0, self.width() - 4, h)
            painter.drawText(num_rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, num)
        else:
            # 普通可变显示：按 var_align 渲染
            align = self._var_align if self._var_align is not None else Qt.AlignmentFlag.AlignCenter
            draw_rect = self.contentsRect()
            painter.drawText(draw_rect, align, self._var_text)
        painter.end()

    def enterEvent(self, event):
        """触摸模式下跳过 hover 效果"""
        if not self._touch_active:
            super().enterEvent(event)

    def leaveEvent(self, event):
        if not self._touch_active:
            super().leaveEvent(event)

    def mousePressEvent(self, event):
        """鼠标/触控板点击反馈 → DCS-BIOS press(1)。
        注意：原生触控开启时触摸走 event(TouchEnd) 路径，不会经过这里。
        原生触控关闭时 Windows 合成鼠标事件走这个路径。"""
        if self._touch_active or self._no_feedback:
            super().mousePressEvent(event)
            return
        self.setStyleSheet(f"""
            UFCCell {{ background-color: {self._pb}; border: 2px solid {self._bc}; border-radius: 0px; }}
        """)
        # 发送 DCS-BIOS press (1)
        if self.pos is not None:
            self.action_pressed.emit(self.pos)
            bios_entry = UFC_BIOS_MAP.get(self.pos)
            if isinstance(bios_entry, str):
                send_dcs_bios(bios_entry, 1)
                self._bios_pressed = True
        # 不再 emit clicked on press — 等 release
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        """鼠标松开 → DCS-BIOS release(0) 延迟 → emit clicked"""
        if not self._no_feedback:
            self._refresh_stylesheet()
        if self.pos is not None:
            self.action_released.emit(self.pos)
            bios_entry = UFC_BIOS_MAP.get(self.pos)
            if isinstance(bios_entry, str) and self._bios_pressed:
                identifier = bios_entry
                QTimer.singleShot(_MIN_PRESS_MS, lambda id=identifier: _send_release(id))
                self._bios_pressed = False
            elif isinstance(bios_entry, tuple):
                identifier, value = bios_entry
                send_dcs_bios(identifier, value)
            self.clicked.emit(self.pos)
        super().mouseReleaseEvent(event)

    def _refresh_stylesheet(self):
        """重建 stylesheet（用于亮度变化或重置样式）"""
        self.setStyleSheet(f"""
            UFCCell {{
                background-color: {BG_COLOR};
                border: 2px solid {self._bc};
                border-radius: 0px;
            }}
            UFCCell:hover {{
                background-color: {self._hb};
            }}
        """)
        # 刷新 QLabel 文字颜色（可变显示单元格无 QLabel，走 QPainter）
        if hasattr(self, 'label') and self.label:
            self.label.setStyleSheet(f"color: {self._tc}; background: transparent;")

    def _apply_brightness(self, brightness, tc, bc, hb, pb):
        """亮度变化时更新颜色并强制重绘"""
        self._tc = tc
        self._bc = bc
        self._hb = hb
        self._pb = pb
        self._refresh_stylesheet()
        self.repaint()  # 强制立即同步重绘（update 可能被 setStyleSheet 的内部重绘覆盖）


class TouchMenuScroll(QScrollArea):
    """Touch-drag menu viewport with hidden scroll bars and tap hit-testing."""

    menuActivated = pyqtSignal(tuple)
    ITEM_H = 90
    ITEM_GAP = 17
    DRAG_THRESHOLD = 12

    def __init__(self, parent=None):
        super().__init__(parent)
        self._page = "select"
        self._items = []
        self._content_base_h = 0
        self._content_scale = 1.0
        self._drag_active = False
        self._drag_start_y = 0.0
        self._drag_last_pos = None
        self._drag_start_scroll = 0
        self._drag_distance = 0.0

        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setWidgetResizable(False)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet(f"QScrollArea {{ background:{BG_COLOR}; border:none; }}")
        self.viewport().setStyleSheet(f"background:{BG_COLOR}; border:none;")
        self.viewport().setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents, True)
        self.viewport().installEventFilter(self)

        self.content = QWidget()
        self.content.setStyleSheet(f"background:{BG_COLOR};")
        self.content.setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents, False)
        self.content.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setWidget(self.content)

    def add_menu_item(self, text, pos, index: int, *, active: bool, font_size=22):
        y = int(index) * (self.ITEM_H + self.ITEM_GAP)
        cell = UFCCell(
            text, pos, font_size=font_size, bold=bool(active),
            parent=self.content, no_feedback=not active,
        )
        cell._menu_active = bool(active)
        cell._menu_base_geometry = (0, y, 1008, self.ITEM_H)
        cell._menu_base_font = int(font_size)
        cell.setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents, False)
        cell.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._items.append(cell)
        self._content_base_h = y + self.ITEM_H
        self.rescale_content(self._content_scale)
        return cell

    @staticmethod
    def _event_position(event):
        try:
            points = event.points()
            if points:
                return points[0].position()
        except (AttributeError, IndexError, TypeError):
            pass
        try:
            return event.position()
        except AttributeError:
            return None

    def _begin_drag(self, point) -> None:
        if point is None:
            return
        self._drag_active = True
        self._drag_start_y = float(point.y())
        self._drag_last_pos = point
        self._drag_start_scroll = self.verticalScrollBar().value()
        self._drag_distance = 0.0

    def _move_drag(self, point) -> None:
        if not self._drag_active or point is None:
            return
        self._drag_last_pos = point
        delta = float(point.y()) - self._drag_start_y
        self._drag_distance = max(self._drag_distance, abs(delta))
        self.verticalScrollBar().setValue(round(self._drag_start_scroll - delta))

    def _tile_at(self, point):
        if point is None:
            return None
        content_x = round(float(point.x()))
        content_y = round(float(point.y())) + self.verticalScrollBar().value()
        for cell in self._items:
            if cell.geometry().contains(content_x, content_y):
                return cell
        return None

    def _end_drag(self, point) -> None:
        if not self._drag_active:
            return
        if point is None:
            point = self._drag_last_pos
        if point is not None:
            self._drag_distance = max(
                self._drag_distance,
                abs(float(point.y()) - self._drag_start_y),
            )
        self._drag_active = False
        if self._drag_distance <= self.DRAG_THRESHOLD:
            cell = self._tile_at(point)
            if cell is not None and getattr(cell, "_menu_active", False):
                self.menuActivated.emit(cell.pos)

    def eventFilter(self, watched, event):
        if watched is self.viewport():
            event_type = event.type()
            if event_type in (QtCore.QEvent.Type.TouchBegin, QtCore.QEvent.Type.MouseButtonPress):
                if event_type == QtCore.QEvent.Type.MouseButtonPress and event.button() != Qt.MouseButton.LeftButton:
                    return False
                self._begin_drag(self._event_position(event))
                event.accept()
                return True
            if event_type in (QtCore.QEvent.Type.TouchUpdate, QtCore.QEvent.Type.MouseMove):
                if self._drag_active:
                    self._move_drag(self._event_position(event))
                    event.accept()
                    return True
            if event_type in (QtCore.QEvent.Type.TouchEnd, QtCore.QEvent.Type.MouseButtonRelease):
                if self._drag_active:
                    self._end_drag(self._event_position(event))
                    event.accept()
                    return True
            if event_type in (QtCore.QEvent.Type.TouchCancel, QtCore.QEvent.Type.Leave):
                self._drag_active = False
        return super().eventFilter(watched, event)

    def rescale_content(self, scale: float) -> None:
        scale = max(0.1, float(scale))
        old_max = self.verticalScrollBar().maximum()
        old_fraction = self.verticalScrollBar().value() / old_max if old_max else 0.0
        self._content_scale = scale
        self.content.resize(max(1, round(1008 * scale)),
                            max(1, round(self._content_base_h * scale)))
        for cell in self._items:
            x, y, w, h = cell._menu_base_geometry
            cell.setGeometry(round(x * scale), round(y * scale),
                             max(1, round(w * scale)), max(1, round(h * scale)))
            cell.rescale_font(max(10, round(cell._menu_base_font * scale)))
        new_max = self.verticalScrollBar().maximum()
        self.verticalScrollBar().setValue(round(old_fraction * new_max))

    def apply_brightness(self, brightness, tc, bc, hb, pb) -> None:
        for cell in self._items:
            cell._apply_brightness(brightness, tc, bc, hb, pb)


class UFCBlank(QFrame):
    """空白占位方块 - 无边框不可点击"""
    def __init__(self, parent=None, bordered=False):
        super().__init__(parent)
        self._bordered = bordered
        self._page = "local_icp"  # 默认属于 LOCAL ICP 页面
        if bordered:
            self.setStyleSheet(f"background-color: {BG_COLOR}; border: 2px solid {border_color_br()};")
        else:
            self.setStyleSheet(f"background-color: {BG_COLOR}; border: none;")
