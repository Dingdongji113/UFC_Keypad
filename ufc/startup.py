# -*- coding: utf-8 -*-
"""UFC 上电 / BIT 启动画面与可选启动风格。

启动覆盖层在 UFCKeypadWindow 上方显示，直到收到第一条 DCS-BIOS 信号。
默认风格为黑底绿字 UFC BIT；另提供架空千禧日本动画风格终端启动画面。

如果 DCS 尚未输出数据，用户可点击 / 触摸覆盖层手动跳过，避免遮挡 SYSTEMS 主菜单。
"""
import time

from PyQt6.QtCore import QEvent, QRect, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QComboBox, QGroupBox, QHBoxLayout, QLabel, QWidget

from ufc.config import load_config, save_config
from ufc.constants import BG_COLOR
from ufc.fonts import get_hornet_font

STARTUP_STYLE_UFC_BIT = "ufc_bit"
STARTUP_STYLE_ANIME_MILLENNIUM = "anime_millennium_jp"
STARTUP_STYLE_DEFAULT = STARTUP_STYLE_UFC_BIT

STARTUP_STYLE_OPTIONS = [
    ("UFC BIT（军机自检风格）", STARTUP_STYLE_UFC_BIT),
    ("千禧日式动画风格", STARTUP_STYLE_ANIME_MILLENNIUM),
]


class StartupOverlayBase(QWidget):
    """启动覆盖层基类：负责生命周期、尺寸跟随、收到 DCS 信号后隐藏。"""

    ready_hold_seconds = 0.85

    def __init__(self, parent=None):
        super().__init__(parent)
        # 不再透明传鼠标：overlay 视觉覆盖时应先吃掉一次点击并自行关闭，
        # 避免“菜单已经切到背后但被 overlay 遮住”的错觉。
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

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

    def event(self, event):
        if event.type() in (QEvent.Type.TouchBegin, QEvent.Type.TouchUpdate):
            self._finish()
            event.accept()
            return True
        return super().event(event)

    def mousePressEvent(self, event):
        """无 DCS 信号时允许点击 / 触摸跳过启动画面。"""
        self._finish()
        event.accept()

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
            if time.time() - self._ready_started_at > self.ready_hold_seconds:
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
        """结束覆盖层。

        重要：收到首个 DCS 信号后 overlay 会自行结束；此时必须清理 key_panel 上的
        _startup_overlay 引用，否则后续在设置窗口切换风格时可能访问到已删除的 Qt 对象。
        """
        if self._finished:
            return
        self._finished = True

        parent = self.parentWidget()
        if parent is not None:
            try:
                parent._dcs_signal.disconnect(self.on_dcs_signal)
            except Exception:
                pass
            if getattr(parent, "_startup_overlay", None) is self:
                parent._startup_overlay = None

        self.hide()
        if self._timer.isActive():
            self._timer.stop()
        self.deleteLater()

    def _scale(self):
        w = max(1, self.width())
        h = max(1, self.height())
        sx = w / 1024.0
        sy = h / 600.0
        s = min(sx, sy)
        ox = int((w - 1024 * s) / 2)
        oy = int((h - 600 * s) / 2)
        return s, ox, oy


class UFCBitStartupOverlay(StartupOverlayBase):
    """默认 UFC BIT 自检启动动画：黑底绿字、总线扫描。"""

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        p.fillRect(self.rect(), QColor(BG_COLOR))

        s, ox, oy = self._scale()
        def rx(x): return int(ox + x * s)
        def ry(y): return int(oy + y * s)
        def rw(v): return int(v * s)
        def rh(v): return int(v * s)

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

        p.setFont(small_font)
        p.setPen(dim_green)
        p.drawText(QRect(rx(270), ry(462), rw(484), rh(24)), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "RX  239.255.50.10:5010")
        p.drawText(QRect(rx(270), ry(488), rw(484), rh(24)), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "TX  127.0.0.1:7778")

        if self._connected:
            p.setPen(bright_green)
            p.drawText(QRect(rx(0), ry(528), rw(1024), rh(34)), Qt.AlignmentFlag.AlignCenter, "DCS-BIOS ONLINE   UFC READY")
        elif time.time() - self._started_at > 5.0:
            p.setPen(dim_green)
            p.drawText(QRect(rx(0), ry(518), rw(1024), rh(28)), Qt.AlignmentFlag.AlignCenter, "NO DATA   CHECK DCS / EXPORT")
            p.drawText(QRect(rx(0), ry(548), rw(1024), rh(26)), Qt.AlignmentFlag.AlignCenter, "TOUCH / CLICK TO SKIP")
        else:
            p.setPen(dim_green)
            p.drawText(QRect(rx(0), ry(548), rw(1024), rh(26)), Qt.AlignmentFlag.AlignCenter, "TOUCH / CLICK TO SKIP")


# 向后兼容旧导入名。
UFCStartupOverlay = UFCBitStartupOverlay


class AnimeMillenniumStartupOverlay(StartupOverlayBase):
    """架空千禧日本动画风格启动动画：蓝黑终端、青色 HUD、日文状态字。"""

    ready_hold_seconds = 1.05

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        s, ox, oy = self._scale()
        def rx(x): return int(ox + x * s)
        def ry(y): return int(oy + y * s)
        def rw(v): return int(v * s)
        def rh(v): return int(v * s)

        bg = QColor(3, 6, 20)
        p.fillRect(self.rect(), bg)

        scan_color = QColor(30, 230, 210, 20)
        p.setPen(QPen(scan_color, max(1, rh(1))))
        step = max(4, rh(6))
        for y in range(0, self.height(), step):
            p.drawLine(0, y, self.width(), y)

        pulse = 0.45 + 0.20 * ((self._tick % 24) / 23.0)
        if self._tick % 48 >= 24:
            pulse = 0.65 - 0.20 * (((self._tick - 24) % 24) / 23.0)
        cyan = QColor(40, int(220 * pulse), 220)
        dim_cyan = QColor(20, 120, 130)
        blue = QColor(35, 80, 190)
        white = QColor(215, 235, 240)
        hot = QColor(115, 255, 235) if self._connected else cyan

        title_font = QFont("MS Gothic", max(12, int(32 * s)))
        sub_font = QFont("MS Gothic", max(9, int(18 * s)))
        body_font = QFont("Consolas", max(9, int(20 * s)))
        jp_font = QFont("MS Gothic", max(9, int(18 * s)))
        small_font = QFont("Consolas", max(8, int(14 * s)))

        p.setPen(QPen(dim_cyan, max(1, rw(1))))
        p.drawRect(QRect(rx(96), ry(58), rw(832), rh(484)))
        p.drawLine(rx(96), ry(116), rx(928), ry(116))
        p.drawLine(rx(96), ry(472), rx(928), ry(472))
        p.setPen(QPen(blue, max(1, rw(2))))
        p.drawLine(rx(126), ry(86), rx(238), ry(86))
        p.drawLine(rx(786), ry(86), rx(898), ry(86))
        p.drawLine(rx(126), ry(514), rx(238), ry(514))
        p.drawLine(rx(786), ry(514), rx(898), ry(514))

        p.setFont(title_font)
        p.setPen(hot)
        p.drawText(QRect(rx(0), ry(128), rw(1024), rh(44)), Qt.AlignmentFlag.AlignCenter, "UFC INTERFACE SYSTEM")
        p.setFont(sub_font)
        p.setPen(white)
        p.drawText(QRect(rx(0), ry(170), rw(1024), rh(28)), Qt.AlignmentFlag.AlignCenter, "起動シーケンス / TACTICAL AVIONICS TERMINAL")

        rows = [
            ("DISPLAY", "INIT", "表示系統"),
            ("INPUT", "READY", "入力待機"),
            ("DATALINK", "ONLINE" if self._connected else "SEARCH", "戦術端末接続"),
            ("DATA BUS", "SYNC" if self._connected else "WAIT", "同期待機"),
        ]
        visible_rows = min(len(rows), max(0, (self._tick - 5) // 4))
        for i, (left, right, jp) in enumerate(rows[:visible_rows]):
            y = 228 + i * 46
            row_hot = self._connected and i >= 2
            p.setFont(body_font)
            p.setPen(hot if row_hot else cyan)
            p.drawText(QRect(rx(222), ry(y), rw(190), rh(30)), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, left)
            p.drawText(QRect(rx(480), ry(y), rw(160), rh(30)), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, right)
            p.setFont(jp_font)
            p.setPen(white if row_hot else dim_cyan)
            p.drawText(QRect(rx(660), ry(y), rw(180), rh(30)), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, jp)

        p.setFont(small_font)
        if self._connected:
            trace = "LINK ESTABLISHED // SYSTEM READY"
        else:
            arrows = ">" * (4 + self._tick % 9)
            trace = f"CONNECTING {arrows:<13}"
        p.setPen(hot)
        p.drawText(QRect(rx(222), ry(424), rw(600), rh(26)), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, trace)

        p.setPen(dim_cyan)
        p.drawText(QRect(rx(126), ry(486), rw(360), rh(22)), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "RX 239.255.50.10:5010")
        p.drawText(QRect(rx(538), ry(486), rw(360), rh(22)), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, "TX 127.0.0.1:7778")

        if self._connected:
            p.setFont(jp_font)
            p.setPen(hot)
            p.drawText(QRect(rx(0), ry(520), rw(1024), rh(34)), Qt.AlignmentFlag.AlignCenter, "接続完了    SYSTEM READY")
        elif time.time() - self._started_at > 5.0:
            p.setFont(jp_font)
            p.setPen(dim_cyan)
            p.drawText(QRect(rx(0), ry(510), rw(1024), rh(30)), Qt.AlignmentFlag.AlignCenter, "信号待機    CHECK DCS / EXPORT")
            p.drawText(QRect(rx(0), ry(542), rw(1024), rh(28)), Qt.AlignmentFlag.AlignCenter, "TOUCH / CLICK TO SKIP")
        else:
            p.setFont(jp_font)
            p.setPen(dim_cyan)
            p.drawText(QRect(rx(0), ry(542), rw(1024), rh(28)), Qt.AlignmentFlag.AlignCenter, "TOUCH / CLICK TO SKIP")


def normalize_startup_style(style_name):
    """规范化启动动画样式名，未知值回落默认 UFC BIT。"""
    allowed = {value for _label, value in STARTUP_STYLE_OPTIONS}
    return style_name if style_name in allowed else STARTUP_STYLE_DEFAULT


def get_configured_startup_style():
    """从配置读取启动动画样式。"""
    cfg = load_config()
    return normalize_startup_style(cfg.get("startup_style", STARTUP_STYLE_DEFAULT))


def create_startup_overlay(style_name, parent=None):
    """按样式名创建启动动画覆盖层。"""
    style_name = normalize_startup_style(style_name)
    if style_name == STARTUP_STYLE_ANIME_MILLENNIUM:
        return AnimeMillenniumStartupOverlay(parent)
    return UFCBitStartupOverlay(parent)


def install_startup_overlay(key_panel, style_name=None):
    """安装或替换当前启动动画覆盖层，并统一管理 DCS 信号连接。"""
    style_name = normalize_startup_style(style_name or get_configured_startup_style())

    old_overlay = getattr(key_panel, "_startup_overlay", None)
    if old_overlay is not None:
        try:
            key_panel._dcs_signal.disconnect(old_overlay.on_dcs_signal)
        except Exception:
            pass
        try:
            old_overlay._finish()
        except Exception:
            try:
                old_overlay.hide()
                old_overlay.deleteLater()
            except Exception:
                pass
        if getattr(key_panel, "_startup_overlay", None) is old_overlay:
            key_panel._startup_overlay = None

    overlay = create_startup_overlay(style_name, key_panel)
    key_panel._dcs_signal.connect(overlay.on_dcs_signal)
    key_panel._startup_overlay = overlay
    key_panel._startup_style = style_name
    return overlay


def attach_startup_style_settings(settings_window):
    """给现有 SettingsWindow 动态添加启动动画选择项，不侵入 ui.py 主体。"""
    layout = settings_window.layout()
    if layout is None:
        return None

    group = QGroupBox("启动动画")
    row = QHBoxLayout(group)
    row.addWidget(QLabel("风格:"))

    combo = QComboBox()
    combo.setMinimumWidth(240)
    for label, value in STARTUP_STYLE_OPTIONS:
        combo.addItem(label, userData=value)

    current = get_configured_startup_style()
    idx = combo.findData(current)
    if idx >= 0:
        combo.setCurrentIndex(idx)
    row.addWidget(combo)

    hint = QLabel("切换后立即预览，并保存为下次启动默认")
    hint.setStyleSheet("color: #8888aa; font-size: 11px;")
    row.addWidget(hint)
    row.addStretch()

    def _on_changed(index):
        style = normalize_startup_style(combo.itemData(index))
        cfg = load_config()
        cfg["startup_style"] = style
        save_config(cfg)

        key_panel = getattr(settings_window, "key_panel", None)
        if key_panel is not None:
            install_startup_overlay(key_panel, style)
            if key_panel.isVisible():
                key_panel.raise_()

        if hasattr(settings_window, "status_label"):
            settings_window.status_label.setText(f"启动动画已切换为: {combo.currentText()}（已立即替换并保存）")

    combo.currentIndexChanged.connect(_on_changed)

    # 插入到触控隔离之后；若布局结构变化，则退化为追加。
    insert_index = min(3, layout.count())
    layout.insertWidget(insert_index, group)
    settings_window.startup_style_combo = combo
    return combo
