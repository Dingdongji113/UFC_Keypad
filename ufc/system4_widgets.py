# -*- coding: utf-8 -*-
"""Reusable square, touch-sized SYSTEM 4 avionics controls."""
from __future__ import annotations

import time
from typing import Callable, Iterable, Optional

from PyQt6.QtCore import QEvent, QPoint, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QPolygon
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget,
)


GREEN = "#00e65c"
GREEN_DIM = "#087c38"
GREY = "#53615a"
BG = "#030705"
AMBER = "#d89a28"
RED = "#cf3434"


class TouchButton(QPushButton):
    """QPushButton with a native-touch-first press lifecycle.

    The panel registers for native Windows touch, so SYSTEM 4 cannot depend on
    Windows synthesizing mouse events.  Accepting the touch here also prevents
    Qt from generating a second mouse click after the explicit touch action.
    """
    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents, True)
        self._touch_active = False
        self._touch_cancelled = False

    def _touch_inside(self, event) -> bool:
        try:
            points = event.points()
            if points:
                return self.rect().contains(points[0].position().toPoint())
        except (AttributeError, IndexError, TypeError):
            pass
        return True

    def _release_touch(self, *, click: bool) -> None:
        if not self._touch_active:
            return
        self._touch_active = False
        self.setDown(False)
        self.released.emit()
        if click and self.isEnabled():
            if self.isCheckable():
                self.toggle()
            self.clicked.emit(self.isChecked())

    def event(self, event) -> bool:
        event_type = event.type()
        if event_type == QEvent.Type.TouchBegin:
            if not self.isEnabled() or self._touch_active:
                event.accept()
                return True
            self._touch_active = True
            self._touch_cancelled = False
            self.setDown(True)
            self.pressed.emit()
            event.accept()
            return True
        if event_type == QEvent.Type.TouchUpdate and self._touch_active:
            if not self._touch_inside(event):
                self._touch_cancelled = True
                self._release_touch(click=False)
            event.accept()
            return True
        if event_type == QEvent.Type.TouchEnd:
            click = self._touch_active and not self._touch_cancelled and self._touch_inside(event)
            self._release_touch(click=click)
            self._touch_cancelled = False
            event.accept()
            return True
        if event_type == QEvent.Type.TouchCancel:
            self._touch_cancelled = True
            self._release_touch(click=False)
            self._touch_cancelled = False
            event.accept()
            return True
        return super().event(event)


CONTROL_STYLE = f"""
QFrame[system4Control="true"] {{ background: {BG}; border: 1px solid {GREY}; }}
QLabel {{ color: {GREEN}; background: transparent; border: none; }}
QPushButton {{ color: {GREEN}; background: #07100b; border: 2px solid {GREEN_DIM}; padding: 2px; }}
QPushButton:pressed {{ background: #123a22; border: 2px solid {GREEN}; }}
QPushButton:checked {{ color: #e7fff0; background: #115b2e; border: 2px solid {GREEN}; }}
QPushButton:disabled {{ color: #56625b; border-color: #303a34; }}
"""


class CutCornerFrame(QWidget):
    """Low-glow military frame with small 45-degree clipped corners."""
    def __init__(self, *, danger=False, double=False, parent=None):
        super().__init__(parent)
        self.danger = bool(danger)
        self.double = bool(double)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    @staticmethod
    def _polygon(width: int, height: int, cut: int, inset: int = 0) -> QPolygon:
        left, top = inset, inset
        right, bottom = max(inset, width - 1 - inset), max(inset, height - 1 - inset)
        c = max(2, cut)
        return QPolygon([
            # clockwise from top-left cut
            QPoint(left + c, top), QPoint(right - c, top),
            QPoint(right, top + c), QPoint(right, bottom - c),
            QPoint(right - c, bottom), QPoint(left + c, bottom),
            QPoint(left, bottom - c), QPoint(left, top + c),
        ])

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        outer = QColor("#9b2d2d" if self.danger else "#66776e")
        inner = QColor("#5d1d1d" if self.danger else "#233f31")
        polygon = self._polygon(self.width(), self.height(), 8)
        painter.setPen(QPen(outer, 2))
        painter.setBrush(QColor("#100505" if self.danger else "#020604"))
        painter.drawPolygon(polygon)
        if self.double and self.width() > 16 and self.height() > 16:
            painter.setPen(QPen(inner, 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPolygon(self._polygon(self.width(), self.height(), 7, 5))
        painter.end()


class AvionicsControl(QFrame):
    def __init__(self, title: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setProperty("system4Control", True)
        self.setStyleSheet(CONTROL_STYLE)
        self._base_font = 12
        self._title = QLabel(title, self)
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title.setFont(QFont("B612", 11, QFont.Weight.Bold))
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(4, 3, 4, 4)
        self._layout.setSpacing(3)
        self._layout.addWidget(self._title)

    def _button(self, text: str, checkable: bool = False) -> TouchButton:
        button = TouchButton(text, self)
        button.setCheckable(checkable)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.setMinimumSize(56, 44)
        button.setFont(QFont("B612", self._base_font, QFont.Weight.Bold))
        return button

    def rescale_font(self, point_size: int) -> None:
        size = max(6, int(point_size))
        self._title.setFont(QFont("B612", max(6, size - 1), QFont.Weight.Bold))
        for button in self.findChildren(QPushButton):
            button.setFont(QFont("B612", size, QFont.Weight.Bold))
        for label in self.findChildren(QLabel):
            if label is not self._title:
                label.setFont(QFont("B612", size))


class StableToggle(AvionicsControl):
    def __init__(self, title: str, labels: Iterable[str], values: Iterable[object],
                 sender: Callable[[object], None], parent=None):
        super().__init__(title, parent)
        self.labels = tuple(labels)
        self.values = tuple(values)
        self.sender = sender
        self.buttons = []
        row = QHBoxLayout()
        row.setSpacing(3)
        for index, label in enumerate(self.labels):
            button = self._button(label, True)
            button.clicked.connect(lambda _checked=False, i=index: self.select_index(i))
            row.addWidget(button, 1)
            self.buttons.append(button)
        self._layout.addLayout(row, 1)
        self.set_state_index(0)

    def select_index(self, index: int) -> None:
        if not 0 <= index < len(self.values):
            return
        if index == getattr(self, "current_index", None):
            self.set_state_index(index)
            return
        self.set_state_index(index)
        self.sender(self.values[index])

    def set_state_index(self, index: int) -> None:
        index = max(0, min(len(self.buttons) - 1, int(index)))
        for i, button in enumerate(self.buttons):
            button.setChecked(i == index)
        self.current_index = index

    def set_feedback(self, value) -> None:
        try:
            self.set_state_index(self.values.index(int(float(value))))
        except (ValueError, TypeError):
            pass


class TwoPositionToggle(StableToggle):
    """Two-position selector with optional DCS-BIOS toggle semantics."""
    def __init__(self, title: str, labels: Iterable[str], values: Iterable[object],
                 sender: Callable[[object], None], parent=None, *, use_toggle=False):
        self.use_toggle = bool(use_toggle)
        super().__init__(title, labels, values, sender, parent)

    def select_index(self, index: int) -> None:
        if not 0 <= index < len(self.values):
            return
        if index == getattr(self, "current_index", None):
            self.set_state_index(index)
            return
        self.set_state_index(index)
        self.sender("TOGGLE" if self.use_toggle else self.values[index])


class ThreePositionToggle(StableToggle):
    pass


class SpringThreePositionToggle(AvionicsControl):
    def __init__(self, title: str, sender: Callable[[object], None], *, rocker=False, parent=None):
        super().__init__(title, parent)
        self.sender = sender
        self.rocker = bool(rocker)
        row = QHBoxLayout()
        self.left = self._button("DEC")
        self.center = QLabel("CENTER", self)
        self.center.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.right = self._button("INC")
        row.addWidget(self.left, 2)
        row.addWidget(self.center, 3)
        row.addWidget(self.right, 2)
        self._layout.addLayout(row, 1)
        self.left.pressed.connect(lambda: self._press(-1))
        self.right.pressed.connect(lambda: self._press(1))
        self.left.released.connect(self._release)
        self.right.released.connect(self._release)
        self.position = 0

    def _press(self, direction: int) -> None:
        self.position = -1 if direction < 0 else 1
        self.center.setText("LEFT" if direction < 0 else "RIGHT")
        self.sender("DEC" if self.rocker and direction < 0 else
                    "INC" if self.rocker else 0 if direction < 0 else 2)

    def _release(self) -> None:
        self.position = 0
        self.center.setText("CENTER")
        if not self.rocker:
            self.sender(1)

    def set_feedback(self, value) -> None:
        try:
            numeric = int(float(value))
        except (TypeError, ValueError):
            return
        self.position = numeric - 1
        self.center.setText(("LEFT", "CENTER", "RIGHT")[max(0, min(2, numeric))])


class AnalogKnob(AvionicsControl):
    REPEAT_DELAY_MS = 360
    REPEAT_INTERVAL_MS = 110
    RAW_MAX = 65535
    STEP_RAW = 3277  # approximately 5 percent per click

    def __init__(self, title: str, sender: Callable[[object], None], parent=None):
        super().__init__(title, parent)
        self.sender = sender
        self.value = 0.0
        row = QHBoxLayout()
        self.left = self._button("DEC")
        self.value_label = QLabel("0%", self)
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.right = self._button("INC")
        row.addWidget(self.left, 2)
        row.addWidget(self.value_label, 3)
        row.addWidget(self.right, 2)
        self._layout.addLayout(row, 1)
        self._repeat_direction = None
        self._delay = QTimer(self)
        self._delay.setSingleShot(True)
        self._delay.timeout.connect(self._begin_repeat)
        self._repeat = QTimer(self)
        self._repeat.timeout.connect(self._send_repeat)
        self.left.pressed.connect(lambda: self._start(-1))
        self.right.pressed.connect(lambda: self._start(1))
        self.left.released.connect(self.stop_repeat)
        self.right.released.connect(self.stop_repeat)

    def _start(self, direction: int) -> None:
        self._repeat_direction = -1 if direction < 0 else 1
        self._send_repeat()
        self._delay.start(self.REPEAT_DELAY_MS)

    def _begin_repeat(self) -> None:
        if self._repeat_direction:
            self._repeat.start(self.REPEAT_INTERVAL_MS)

    def _send_repeat(self) -> None:
        if self._repeat_direction:
            raw = round(self.value * self.RAW_MAX)
            raw = max(0, min(self.RAW_MAX, raw + self._repeat_direction * self.STEP_RAW))
            self.value = raw / self.RAW_MAX
            self.value_label.setText(f"{round(self.value * 100):d}%")
            self.sender(raw)

    def stop_repeat(self) -> None:
        self._repeat_direction = None
        self._delay.stop()
        self._repeat.stop()

    def set_feedback(self, value) -> None:
        try:
            self.value = max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            return
        self.value_label.setText(f"{round(self.value * 100):d}%")


class DetentRotary(StableToggle):
    def __init__(self, title: str, labels, values, sender, parent=None):
        AvionicsControl.__init__(self, title, parent)
        self.labels = tuple(labels)
        self.values = tuple(values)
        self.sender = sender
        self.current_index = 0
        row = QHBoxLayout()
        self.left = self._button("DEC")
        self.value_label = QLabel(self.labels[0], self)
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.right = self._button("INC")
        row.addWidget(self.left, 2)
        row.addWidget(self.value_label, 4)
        row.addWidget(self.right, 2)
        self._layout.addLayout(row, 1)
        self.left.clicked.connect(lambda: self.step(-1))
        self.right.clicked.connect(lambda: self.step(1))

    def step(self, direction: int) -> None:
        target = max(0, min(len(self.values) - 1, self.current_index + (-1 if direction < 0 else 1)))
        if target == self.current_index:
            return
        self.set_state_index(target)
        self.sender(self.values[target])

    def set_state_index(self, index: int) -> None:
        self.current_index = max(0, min(len(self.labels) - 1, int(index)))
        self.value_label.setText(self.labels[self.current_index])

    def set_feedback(self, value) -> None:
        try:
            self.set_state_index(self.values.index(int(float(value))))
        except (TypeError, ValueError):
            pass


class PushButton(AvionicsControl):
    def __init__(self, title: str, sender: Callable[[object], None], *, press_only=False,
                 latching=False, show_lamp=False, button_text=None, parent=None):
        super().__init__(title, parent)
        self.sender = sender
        self.press_only = bool(press_only)
        self.latching = bool(latching)
        self.lamp_on = False
        self.button = self._button(button_text or title, self.latching)
        self.lamp = QLabel("OFF", self)
        self.lamp.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lamp.setMinimumSize(46, 30)
        self.lamp.setFont(QFont("B612", 10, QFont.Weight.Bold))
        self.lamp.setStyleSheet("background:#18221b; border:1px solid #304036;")
        row = QHBoxLayout()
        row.addWidget(self.button, 5)
        if show_lamp:
            row.addWidget(self.lamp, 1)
        else:
            self.lamp.hide()
        self._layout.addLayout(row, 1)
        if self.latching:
            self.button.clicked.connect(self._toggle_latched)
        elif self.press_only:
            self.button.clicked.connect(lambda: self.sender(1))
        else:
            self.button.pressed.connect(lambda: self.sender(1))
            self.button.released.connect(lambda: self.sender(0))

    def _toggle_latched(self) -> None:
        target = 0 if self.lamp_on else 1
        self.sender(target)
        # Keep touch feedback responsive while the next DCS-BIOS frame arrives.
        self.set_feedback(target)

    def set_feedback(self, value) -> None:
        try:
            on = float(value) >= 0.5
        except (TypeError, ValueError):
            on = False
        self.lamp.setStyleSheet(
            f"background:{GREEN if on else '#18221b'}; border:1px solid {GREEN_DIM if on else '#304036'};"
        )
        self.lamp.setText("ON" if on else "OFF")
        if self.latching:
            self.button.setChecked(on)
        self.lamp_on = on


class Alr67Button(AvionicsControl):
    """Square ALR-67 annunciator/touch face with feedback-driven legends."""

    def __init__(self, sender: Callable[[object], None], legends, *, primary_field: str,
                 latching=False, parent=None):
        super().__init__("", parent)
        self._title.hide()
        self.sender = sender
        self.legends = tuple((str(field), str(text)) for field, text in legends)
        self.primary_field = str(primary_field)
        self.latching = bool(latching)
        self.lamp_on = False
        self._lamp_states = {field: False for field, _text in self.legends}
        self._layout.setContentsMargins(7, 7, 7, 7)
        self.button = self._button("", self.latching)
        self.button.setMinimumSize(116, 116)
        self.button.setMaximumSize(126, 126)
        self._legend_labels = {}
        face_layout = QVBoxLayout(self.button)
        face_layout.setContentsMargins(8, 8, 8, 8)
        face_layout.setSpacing(0)
        for field, _text in self.legends:
            label = QLabel("", self.button)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            label.setFont(QFont("B612", self._base_font, QFont.Weight.Bold))
            face_layout.addWidget(label, 1)
            self._legend_labels[field] = label
        self._layout.addWidget(
            self.button, 1,
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
        )
        self._refresh_face()
        if self.latching:
            self.button.clicked.connect(self._toggle_latched)
        else:
            self.button.pressed.connect(lambda: self.sender(1))
            self.button.released.connect(lambda: self.sender(0))

    def _toggle_latched(self) -> None:
        target = 0 if self.lamp_on else 1
        self.sender(target)
        self.set_lamp_feedback(self.primary_field, target)

    def _refresh_face(self) -> None:
        active = [text for field, text in self.legends if self._lamp_states.get(field, False)]
        failed = any(text == "FAIL" and self._lamp_states.get(field, False)
                     for field, text in self.legends)
        self.button.setText("")
        for field, text in self.legends:
            on = self._lamp_states.get(field, False)
            label = self._legend_labels[field]
            label.setText(text if on else "")
            color = RED if text == "FAIL" else GREEN
            label.setStyleSheet(f"color:{color if on else 'transparent'}; background:transparent; border:none;")
        if failed:
            border, background = "#cf3434", "#100707"
        elif active:
            border, background = GREEN, "#07150d"
        else:
            border, background = GREEN_DIM, "#07100b"
        self.button.setStyleSheet(
            f"QPushButton {{ color:transparent; background:{background}; border:3px solid {border}; padding:4px; }}"
            f"QPushButton:pressed {{ background:#123a22; border-color:{GREEN}; }}"
        )
        self.lamp_on = bool(self._lamp_states.get(self.primary_field, False))
        if self.latching:
            self.button.setChecked(self.lamp_on)

    def set_lamp_feedback(self, field: str, value) -> None:
        if field not in self._lamp_states:
            return
        try:
            self._lamp_states[field] = float(value) >= 0.5
        except (TypeError, ValueError):
            self._lamp_states[field] = False
        self._refresh_face()

    def set_feedback(self, value) -> None:
        self.set_lamp_feedback(self.primary_field, value)

    def legend_texts(self):
        return tuple(self._legend_labels[field].text() for field, _text in self.legends)

    def rescale_font(self, point_size: int) -> None:
        super().rescale_font(point_size)
        size = max(10, int(point_size))
        for label in self._legend_labels.values():
            label.setFont(QFont("B612", size, QFont.Weight.Bold))


class GuardedHoldButton(AvionicsControl):
    def __init__(self, title: str, hold_ms: int, completed: Callable[[], None], *, danger=False, parent=None):
        super().__init__(title, parent)
        self.hold_ms = max(1, int(hold_ms))
        self.completed = completed
        self._started = 0.0
        self._completed = False
        button_text = "HOLD\nECM JETT" if title == "ECM JETT" else f"HOLD {title}"
        self.button = self._button(button_text)
        self.progress = QProgressBar(self)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        color = RED if danger else AMBER
        self.button.setStyleSheet(
            f"QPushButton {{ color:{color}; background:#100806; border:2px solid {color}; }}"
            f"QPushButton:pressed {{ background:#3a130d; }}"
        )
        self.progress.setStyleSheet(
            f"QProgressBar {{ background:#120b08; border:1px solid {color}; }}"
            f"QProgressBar::chunk {{ background:{color}; }}"
        )
        self._layout.addWidget(self.button, 2)
        self._layout.addWidget(self.progress, 1)
        self._timer = QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._tick)
        self.button.pressed.connect(self.begin_hold)
        self.button.released.connect(self.cancel_hold)

    def begin_hold(self) -> None:
        self._started = time.monotonic()
        self._completed = False
        self.progress.setValue(0)
        self._timer.start()

    def _tick(self) -> None:
        elapsed = (time.monotonic() - self._started) * 1000
        self.progress.setValue(min(100, round(elapsed * 100 / self.hold_ms)))
        if elapsed >= self.hold_ms:
            self._timer.stop()
            self._completed = True
            self.progress.setValue(100)
            self.completed()

    def cancel_hold(self) -> None:
        self._timer.stop()
        if not self._completed:
            self.progress.setValue(0)

    def reset(self) -> None:
        self._timer.stop()
        self._completed = False
        self.progress.setValue(0)
