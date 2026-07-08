# -*- coding: utf-8 -*-
"""UFC 上电 / BIT 启动画面。

该覆盖层在 UFCKeypadWindow 上方显示，直到收到第一条 DCS-BIOS 信号。
风格保持与 UFC 面板一致：黑底、暗绿色字符、BIT 自检、DATA BUS 等待。
"""
import time

from PyQt6.QtCore import QEvent, QRect, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QWidget

from ufc.constants import BG_COLOR
from ufc.fonts import get_hornet_font


class UFCStartupOverlay(QWidget):
    """覆盖在主 UFC 面板上的启动自检动画。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)

        self._tick = 0
        self._connected = False
        self._finished = False
        self._ready_started_at = None
        self._started_at = time.time()
        self._last_field = ""

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)
        self._timer.start(90)

        if parent is not None:
            parent.installEventFilter(self)
            self.setGeometry(parent.rect())

        self.show()
        self.raise_()

    def eventFilter(self, obj, event):
        parent = self.parentWidget()
        if obj is parent and event.type() in (QEvent.Type.Resize, QEvent.Type.Show):
            self.setGeometry(parent.rect())
            if not self._finished:
                self.show()
                self.raise_()
        return super().eventFilter(obj, event)

    def _on_tick(self):
        if self._finished:
            self._timer.stop()
            return

        self._tick += 1
        if self._connected and self._ready_started_at is not None:
            # 收到信号后保留短暂 READY / SYNC 转场，再让 LOCAL ICP 露出。
            if time.time() - self._ready_started_at > 0.85:
                self._finish()
                return
        self.update()

    def on_dcs_signal(self, field_name, value):
        """收到第一条 DCS-BIOS 信号后进入 ONLINE / READY 转场。"""
        if self._finished:
            return
        self._last_field = str(field_name or "")
        if not self._connected:
            self._connected = True
            self._ready_started_at = time.time()
            self.update()

    def _finish(self):
        self._finished = True
        self.hide()
        self.deleteLater()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        p.fillRect(self.rect(), QColor(BG_COLOR))

        w = max(1, self.width())
        h = max(1, self.height())
        sx = w / 1024.0
        sy = h / 600.0
        s = min(sx, sy)
        ox = int((w - 1024 * s) / 2)
        oy = int((h - 600 * s) / 2)

        def rx(x): return int(ox + x * s)
        def ry(y): return int(oy + y * s)
        def rw(v): return int(v * s)
        def rh(v): return int(v * s)

        # 低亮度呼吸，保持航电 LED 感，不做现代 UI 霓虹。
        pulse = 0.34 + 0.16 * ((self._tick % 18) / 17.0)
        if self._tick % 36 >= 18:
            pulse = 0.50 - 0.16 * (((self._tick - 18) % 18) / 17.0)
        base = int(255 * pulse)
        dim = max(32, int(base * 0.45))
        bright = 255 if self._connected else max(96, base)

        green = QColor(0, base, 0)
        dim_green = QColor(0, dim, 0)
        bright_green = QColor(0, bright, 0)

        p.setPen(QPen(dim_green, max(1, rw(2))))
        p.drawRect(QRect(rx(148), ry(72), rw(728), rh(456)))
        p.drawRect(QRect(rx(164), ry(88), rw(696), rh(424)))

        title_font = get_hornet_font(max(12, int(34 * s)))
        body_font = get_hornet_font(max(10, int(22 * s)))
        small_font = get_hornet_font(max(8, int(16 * s)))
        mono_font = QFont("Consolas", max(8, int(15 * s)))

        p.setFont(title_font)
        p.setPen(bright_green)
        p.drawText(QRect(rx(0), ry(112), rw(1024), rh(48)), Qt.AlignmentFlag.AlignCenter, "UFC KEYPAD V5")

        # 自检行：逐行点亮。
        status_rows = [
            ("POWER", "ON"),
            ("DISPLAY", "CHECK"),
            ("TOUCH", "ARMED"),
            ("DCS-BIOS", "ONLINE" if self._connected else "STANDBY"),
            ("DATA BUS", "SYNC" if self._connected else "SEARCH"),
        ]
        visible_rows = min(len(status_rows), max(0, (self._tick - 4) // 3))
        p.setFont(body_font)
        for i, (left, right) in enumerate(status_rows[:visible_rows]):
            y = 190 + i * 42
            row_color = bright_green if self._connected and i >= 3 else green
            p.setPen(row_color)
            p.drawText(QRect(rx(270), ry(y), rw(220), rh(32)), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, left)
            p.drawText(QRect(rx(540), ry(y), rw(240), rh(32)), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, right)

        # 总线扫描条。
        p.setFont(mono_font)
        if self._connected:
            scan = "SYNC  READY"
        else:
            bar_len = 18
            head = self._tick % bar_len
            chars = ["░"] * bar_len
            chars[head] = "█"
            if head - 1 >= 0:
                chars[head - 1] = "▓"
            if head - 2 >= 0:
                chars[head - 2] = "▒"
            scan = "".join(chars)
        p.setPen(bright_green if self._connected else green)
        p.drawText(QRect(rx(270), ry(420), rw(484), rh(28)), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, f"BUS SCAN   {scan}")

        # 端口信息，以当前代码为准。
        p.setFont(small_font)
        p.setPen(dim_green)
        p.drawText(QRect(rx(270), ry(462), rw(484), rh(24)), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "RX  239.255.50.10:5010")
        p.drawText(QRect(rx(270), ry(488), rw(484), rh(24)), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "TX  127.0.0.1:7778")

        if self._connected:
            p.setPen(bright_green)
            p.drawText(QRect(rx(0), ry(528), rw(1024), rh(34)), Qt.AlignmentFlag.AlignCenter, "DCS-BIOS ONLINE   UFC READY")
        elif time.time() - self._started_at > 5.0:
            p.setPen(dim_green)
            p.drawText(QRect(rx(0), ry(528), rw(1024), rh(34)), Qt.AlignmentFlag.AlignCenter, "NO DATA   CHECK DCS / EXPORT")
