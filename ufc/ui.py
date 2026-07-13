# -*- coding: utf-8 -*-
"""主面板窗口 (UFCKeypadWindow) 与设置窗口 (SettingsWindow)"""
import sys
import os
import json
import time
import threading

from PyQt6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel,
                             QPushButton, QSizePolicy, QComboBox, QLineEdit,
                             QTextEdit, QGroupBox, QScrollArea, QGridLayout,
                             QCheckBox, QMessageBox, QFrame, QDoubleSpinBox,
                             QApplication, QAbstractItemView)
from PyQt6.QtCore import Qt, QRect, pyqtSignal, QTimer
from PyQt6.QtGui import (QColor, QFont, QPainter, QFontDatabase,
                         QKeyEvent, QMouseEvent, QCursor)

import ufc.colors as _colors_mod
from ufc.colors import (text_color_br, border_color_br,
                        hover_bg_br, pressed_bg_br)
from ufc.constants import *
from ufc.crashlog import *
from ufc.config import *
from ufc.fonts import *
from ufc.morse import *
from ufc.dcs_bios import *
from ufc.input import *
from ufc.input import (_user32, _start_mouse_hook, _stop_mouse_hook,
                       _register_native_touch, _unregister_native_touch,
                       _find_dcs_window, _find_dcs_monitor)
from ufc.widgets import *

class UFCKeypadWindow(QWidget):
    """UFC键盘面板 - 自适应缩放，保持 1024x600 原始比例"""
    keyPressed = pyqtSignal(str)
    keyLogUpdated = pyqtSignal(str, str)  # (时间, 按键名) 按键日志
    _dcs_signal = pyqtSignal(str, str)  # 线程安全：DCS-BIOS 数据更新信号

    # 设计基准尺寸
    DESIGN_W = WIN_W   # 1024
    DESIGN_H = WIN_H   # 600

    def __init__(self):
        super().__init__()
        self.setWindowTitle("UFC Keypad - Panel")
        self.setMinimumSize(320, 188)   # 最小尺寸，保持比例下限
        self.resize(WIN_W, WIN_H)       # 初始大小 = 设计尺寸
        self.setStyleSheet(f"background-color: {BG_COLOR};")
        # 触摸屏优化
        self.setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents, True)
        
        self.cells = {}
        self.display_cells = {}  # 可变显示方块: {pos: UFCCell}
        self._brightness = 0.8   # TODO: 调试亮度，上线前改回 0.0
        self._blanks = []        # 有边框空白方块引用
        self._key_press_log = [] # 最近按键记录 (最多 5 条)
        # 缩放支持：原始坐标+字体列表
        # 格式: (widget, orig_x, orig_y, orig_w, orig_h, orig_font_size)
        self._widget_origins = []
        self._last_dcs_data_time = 0.0   # 最后一次收到 DCS-BIOS 数据的时间
        self._dcs_disconnected = True   # DCS 是否已断开（启动时默认断连）
        
        # ==== 多页面管理 ====
        self._current_page = "local_icp"   # "local_icp" | "morse_light" | "select"
        self._previous_page = "local_icp"  # 从选择页面返回时的目标页面
        self._morse_cells = {}             # Morse Light 页面按钮: {pos: UFCCell}
        self._morse_display = None         # Morse Light 显示区
        self._select_cells = {}            # 选择页面按钮: {pos: UFCCell}
        self._morse_pos_to_key = {}        # Morse 按键 pos → key_char 映射
        self._morse_text = ""              # 当前输入字符串
        self._morse_confirmed = False      # ENT 一次确认状态
        self._morse_outputting = False     # 正在输出摩尔斯码
        self._morse_blink_phase = False    # 确认闪烁相位
        
        # ==== 灯光控制状态 ====
        self._light_displays = {}          # 'ldg'/'form'/'pos'/'strobe' → UFCCell
        self._light_state = {
            'ldg': 0,       # 着陆/滑行: 0=OFF, 1=ON
            'form': 0,      # 编队灯旋钮: 0-65535
            'pos': 0,       # 航线灯旋钮: 0-65535
            'strobe': 1,    # 频闪灯: 0=BRIGHT, 1=OFF, 2=DIM
        }
        self._light_last_local = {}  # 本地操作时间戳, 抑制 DCS 回读闪烁
        
        # ==== DCS-BIOS 接收器 ====
        self._dcs_signal.connect(self._update_display)
        self.dcs_bios = DCSBIOSReceiver(callback=self.on_dcsbios_data)
        self.dcs_bios.start()
        
        # ==== DCS 连接看门狗（退出游戏后自动清空显示） ====
        self._dcs_watchdog = QTimer(self)
        self._dcs_watchdog.timeout.connect(self._check_dcs_timeout)
        self._dcs_watchdog.start(2000)  # 每2秒检查一次
        
        self.setStyleSheet(f"background-color: {BG_COLOR};")
        self.init_ui()

        # ==== WH_MOUSE_LL 光标锁定（启动钩子线程） ====
        self._native_touch_enabled = False
        self._noactivate_applied = False   # showEvent 里只应用一次
        _start_mouse_hook()

        # 每 2 秒刷新 DCS 显示器范围（应对 DCS 窗口移动/切换显示器）
        self._monitor_refresh_timer = QTimer(self)
        self._monitor_refresh_timer.timeout.connect(_find_dcs_monitor)
        self._monitor_refresh_timer.start(2000)

        config = load_config()
        if config.get("native_touch", False):
            self.enable_native_touch(True)

        # _apply_noactivate_style() 已移到 showEvent 中调用（确保窗口句柄已创建）

    def _apply_noactivate_style(self):
        """用 ctypes 设置 WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW，
        确保 Windows 不会因触摸/点击激活本窗口。
        同时调用 SetWindowPos(SWP_FRAMECHANGED) 强制样式生效。"""
        hwnd = int(self.winId())
        cur = _user32.GetWindowLongPtrW(ctypes.wintypes.HWND(hwnd), GWL_EXSTYLE)
        if cur == 0:
            err = ctypes.get_last_error()
            if err != 0:
                print(f"[窗口] GetWindowLongPtrW 失败: {err}")
                return
        new_style = cur
        changed = False
        if not (cur & WS_EX_NOACTIVATE):
            new_style |= WS_EX_NOACTIVATE
            changed = True
        if not (cur & WS_EX_TOOLWINDOW):
            new_style |= WS_EX_TOOLWINDOW
            changed = True
        if changed:
            _user32.SetWindowLongPtrW(
                ctypes.wintypes.HWND(hwnd), GWL_EXSTYLE,
                ctypes.c_longlong(new_style)
            )
            # 强制 Windows 重新应用窗口样式
            _user32.SetWindowPos(
                ctypes.wintypes.HWND(hwnd), None,
                0, 0, 0, 0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED
            )
            print("[窗口] ✓ WS_EX_NOACTIVATE + WS_EX_TOOLWINDOW 已设置")



    def showEvent(self, event):
        """窗口首次显示后应用 WS_EX_NOACTIVATE，确保句柄已创建"""
        super().showEvent(event)
        if not self._noactivate_applied:
            self._apply_noactivate_style()
            self._noactivate_applied = True

    def _on_activate(self, hwnd, msg_obj):
        """WM_ACTIVATE 兜底：如果窗口被意外激活，立即把前台交还给 DCS"""
        # wParam: 0=INACTIVE, 1=ACTIVE, 2=CLICKACTIVE
        wParam = msg_obj.wParam if hasattr(msg_obj, 'wParam') else 0
        if wParam in (1, 2):
            hwnd_dcs = _find_dcs_window()
            if hwnd_dcs:
                # 用 AttachThreadInput 避免跨线程前台切换被 Windows 阻止
                self._safe_activate_dcs(hwnd_dcs)

    def _safe_activate_dcs(self, hwnd_dcs):
        """尝试把前台切换回 DCS（降低权限强制切换）"""
        try:
            _user32.SetForegroundWindow(ctypes.wintypes.HWND(hwnd_dcs))
        except Exception:
            pass

    def nativeEvent(self, eventType, message):
        """Windows 原生消息处理"""
        if eventType == b"windows_generic_MSG":
            msg = ctypes.wintypes.MSG.from_address(int(message))
            # WM_ACTIVATE 兜底：如果窗口被意外激活，把前台交还 DCS
            if msg.message == WM_ACTIVATE:
                self._on_activate(None, msg)
                return True, 0
            # WM_MOUSEACTIVATE：在 Windows 激活窗口之前拦截
            if msg.message == WM_MOUSEACTIVATE:
                return True, MA_NOACTIVATE
            if self._native_touch_enabled and msg.message == WM_TOUCH:
                return False, 0
        return False, 0

    def enable_native_touch(self, enable):
        """启用/禁用原生触控隔离（阻止触摸→鼠标转换）"""
        if os.environ.get("QT_QPA_PLATFORM", "").lower() == "offscreen":
            self._native_touch_enabled = False
            return
        hwnd = int(self.winId())
        if enable:
            if _register_native_touch(hwnd):
                self._native_touch_enabled = True
                print("[触控] 原生触控隔离已启用（触摸不再模拟鼠标）")
                config = load_config()
                config["native_touch"] = True
                save_config(config)
            else:
                print("[触控] 原生触控注册失败（系统可能不支持）")
                self._native_touch_enabled = False
        else:
            if _unregister_native_touch(hwnd):
                self._native_touch_enabled = False
                print("[触控] 原生触控隔离已关闭")
                config = load_config()
                config["native_touch"] = False
                save_config(config)

    def on_dcsbios_data(self, field_name, value):
        """接收到 DCS-BIOS 数据，更新UI (线程安全)"""
        # 使用 signal.emit 确保线程安全（QTimer+lambda 存在跨线程捕获问题）
        self._dcs_signal.emit(field_name, value)
        
    def _update_display(self, field_name, value):
        """更新显示单元格 (主线程执行)"""
        # 每次收到数据都刷新时间戳
        self._last_dcs_data_time = time.time()
        if self._dcs_disconnected:
            self._dcs_disconnected = False
            print("[DCS-BIOS] 🟢 DCS 重新连接，恢复数据显示")
            # 立即从缓存恢复亮度（不依赖 ufc_brightness 回调，因为模拟量值未变时不触发）
            cached = self.dcs_bios.latest.get('ufc_brightness')
            if cached:
                try:
                    b = float(cached)
                    b = max(0.0, min(1.0, b))
                    self._brightness = b
                    self._refresh_brightness()
                except (ValueError, TypeError):
                    pass
        
        # ==== 亮度同步 ====
        if field_name == 'ufc_brightness':
            try:
                b = float(value)
                b = max(0.0, min(1.0, b))
                if abs(b - self._brightness) > 0.01:  # 去掉微小抖动
                    self._brightness = b
                    self._refresh_brightness()
            except (ValueError, TypeError):
                pass
            return
        
        # ==== 外部灯光状态同步 (DCS → UI) ====
        if field_name == 'formation_dimmer':
            if time.time() - self._light_last_local.get('form', 0) < 0.15:
                return
            self._light_state['form'] = int(value)
            self._update_light_display('form')
            return
        if field_name == 'position_dimmer':
            if time.time() - self._light_last_local.get('pos', 0) < 0.15:
                return
            self._light_state['pos'] = int(value)
            self._update_light_display('pos')
            return
        if field_name == 'ldg_taxi_sw':
            if time.time() - self._light_last_local.get('ldg', 0) < 0.15:
                return
            self._light_state['ldg'] = int(value)
            self._update_light_display('ldg')
            return
        if field_name == 'strobe_sw':
            if time.time() - self._light_last_local.get('strobe', 0) < 0.15:
                return
            self._light_state['strobe'] = int(value)
            self._update_light_display('strobe')
            return
        
        # 确保反向映射已构建
        DCSBIOSReceiver._build_maps()
        inv = DCSBIOSReceiver._INTERNAL_TO_BIOS
        
        # 1) 处理组合显示
        for pos, internal_list in DCSBIOSReceiver.COMBINED_DISPLAYS.items():
            if field_name in internal_list and pos in self.display_cells:
                cell = self.display_cells[pos]
                if pos == (0, "blank"):
                    # scratchpad 长条：三字段独立存储，不拼接
                    parts = []
                    for iname in internal_list:
                        bname = inv.get(iname)
                        val = self.dcs_bios.latest.get(bname, '') if bname else ''
                        # 清理：只保留可打印字符，去掉尾随空字符/空格后的垃圾
                        val = ''.join(c for c in str(val) if c in ' 0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz.,/-+')
                        parts.append(val)
                    cell._scratchpad_parts = parts
                    cell._var_text = "__SCRATCHPAD__"   # 标记，触发新渲染路径
                    cell.update()   # 触发 paintEvent
                else:
                    # 其他组合显示（OSB 旁的 cueing+option）：正常拼接
                    parts = []
                    for iname in internal_list:
                        bname = inv.get(iname)
                        parts.append(self.dcs_bios.latest.get(bname, '') if bname else '')
                    combined = ''.join(parts)
                    cell.setText(combined)
        
        # 2) 处理单独映射的字段
        if field_name in DCSBIOSReceiver.DISPLAY_POS_MAP:
            pos = DCSBIOSReceiver.DISPLAY_POS_MAP[field_name]
            # 跳过已在 COMBINED_DISPLAYS 中处理的位置
            if any(field_name in fl for fl in DCSBIOSReceiver.COMBINED_DISPLAYS.values()):
                pass
            elif pos in self.display_cells:
                self.display_cells[pos].setText(str(value))
        else:
            _uk = f"_uk_{field_name}"
            if not hasattr(self, _uk):
                setattr(self, _uk, True)
                print(f"[UI] 字段 {field_name} 不在 DISPLAY_POS_MAP 中")
    
    def _check_dcs_timeout(self):
        """看门狗：断连检测 + 自动恢复。使用 _last_packet_time（每次收包都更新，不受值去重影响）"""
        pkt_t = self.dcs_bios._last_packet_time
        # ── 恢复检测：断连状态下，UDP 包重新到达 ──
        if self._dcs_disconnected:
            if pkt_t > self._last_dcs_data_time:
                self._dcs_disconnected = False
                self._last_dcs_data_time = pkt_t
                print("[DCS-BIOS] 🟢 DCS 重新连接，恢复数据显示")
                # 恢复亮度
                cached = self.dcs_bios.latest.get('ufc_brightness')
                if cached:
                    try:
                        b = float(cached)
                        self._brightness = max(0.0, min(1.0, b))
                        self._refresh_brightness()
                    except (ValueError, TypeError):
                        pass
                # 恢复所有可变显示单元格（从 latest 缓存读取，值未变时回调不触发）
                DCSBIOSReceiver._build_maps()
                inv = DCSBIOSReceiver._INTERNAL_TO_BIOS
                # 1) 组合显示（scratchpad + OSB）
                for pos, internal_list in DCSBIOSReceiver.COMBINED_DISPLAYS.items():
                    if pos not in self.display_cells:
                        continue
                    cell = self.display_cells[pos]
                    if pos == (0, "blank"):
                        parts = []
                        for iname in internal_list:
                            bname = inv.get(iname)
                            val = self.dcs_bios.latest.get(bname, '') if bname else ''
                            val = ''.join(c for c in str(val) if c in ' 0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz.,/-+')
                            parts.append(val)
                        if any(p.strip() for p in parts):
                            cell._scratchpad_parts = parts
                            cell._var_text = "__SCRATCHPAD__"
                            cell.update()
                    else:
                        parts = [self.dcs_bios.latest.get(inv.get(iname), '') if inv.get(iname) else '' for iname in internal_list]
                        combined = ''.join(parts)
                        cell.setText(combined)
                # 2) 独立字段
                for internal_name, bios_name in inv.items():
                    val = self.dcs_bios.latest.get(bios_name, '')
                    if val and internal_name in DCSBIOSReceiver.DISPLAY_POS_MAP:
                        pos = DCSBIOSReceiver.DISPLAY_POS_MAP[internal_name]
                        if pos in self.display_cells:
                            self.display_cells[pos].setText(str(val))
                return
            return  # 断连且无新包，静默等待
        
        # ── 断连检测：超过10秒无包 ──
        if pkt_t == 0.0:
            return  # 尚未收到任何数据
        elapsed = time.time() - pkt_t
        if elapsed > 10.0:
            self._dcs_disconnected = True
            self._last_dcs_data_time = pkt_t  # 记录断开时的包时间，用于恢复比较
            print(f"[DCS-BIOS] 🔴 DCS 信号丢失 (已{elapsed:.0f}秒无包)，清空显示并熄灭亮度")
            self._brightness = 0.0
            self._refresh_brightness()
            for pos, cell in self.display_cells.items():
                if pos == (0, "blank"):
                    cell._scratchpad_parts = []
                cell._var_text = ""
                cell.update()
    
    def _refresh_brightness(self):
        """亮度变化 → 刷新所有页面的所有元素颜色"""
        _colors_mod._CURRENT_BRIGHTNESS = self._brightness
        b = self._brightness
        
        # 重新计算颜色
        tc = text_color_br(b)
        bc = border_color_br(b)
        hb = hover_bg_br(b)
        pb = pressed_bg_br(b)
        
        # 刷新所有页面的所有 UFCCell + UFCBlank (通过 _widget_origins 遍历)
        for widget, *_ in self._widget_origins:
            if isinstance(widget, UFCCell):
                widget._apply_brightness(b, tc, bc, hb, pb)
            elif isinstance(widget, UFCBlank) and getattr(widget, '_bordered', False):
                widget.setStyleSheet(f"background-color: {BG_COLOR}; border: 2px solid {bc};")
            elif isinstance(widget, TouchMenuScroll):
                widget.apply_brightness(b, tc, bc, hb, pb)
            
    def set_display(self, pos, text):
        """设置可变显示方块的文本"""
        if pos in self.display_cells:
            self.display_cells[pos].setText(text)

    def init_ui(self):
        """初始化所有页面 UI"""
        self._init_local_icp()
        self._init_morse_light()
        self._init_system_select()
        self._init_light_control()
        self._show_page("local_icp")

    def _show_page(self, page_name):
        """切换页面：隐藏所有控件，显示目标页面的控件"""
        prev = self._current_page
        self._current_page = page_name
        if page_name != "select":
            self._previous_page = page_name
        
        # 编队灯管理：进入 Morse 关灯并记录原值，退出时恢复
        if page_name == "morse_light" and prev != "morse_light":
            self._morse_form_lights_before = self._light_state['form']
            send_dcs_bios(MORSE_FORMATION_LIGHTS, 0)
        elif prev == "morse_light" and page_name != "morse_light":
            send_dcs_bios(MORSE_FORMATION_LIGHTS, self._morse_form_lights_before)
            # 清理 Morse 状态
            self._morse_text = ""
            self._morse_confirmed = False
            self._morse_outputting = False
            if hasattr(self, '_morse_blink_timer'):
                self._morse_blink_timer.stop()
        
        for widget, *_ in self._widget_origins:
            wpage = getattr(widget, '_page', 'local_icp')
            widget.setVisible(wpage == page_name)
        
        # 切换后刷新 DCS 缓存数据
        self._refresh_from_dcs()

    def _refresh_from_dcs(self):
        """从 DCS-BIOS 缓存刷新当前显示（灯光等）"""
        parser = self.dcs_bios.parser
        for addr, (internal_name, mask, shift) in parser.integer_addrs.items():
            lo = parser.state[addr]
            hi = parser.state[addr + 1]
            raw = lo | (hi << 8)
            val = (raw & mask) >> shift
            if internal_name == 'formation_dimmer':
                self._light_state['form'] = val
                self._update_light_display('form')
            elif internal_name == 'position_dimmer':
                self._light_state['pos'] = val
                self._update_light_display('pos')
            elif internal_name == 'ldg_taxi_sw':
                self._light_state['ldg'] = val
                self._update_light_display('ldg')
            elif internal_name == 'strobe_sw':
                self._light_state['strobe'] = val
                self._update_light_display('strobe')

    def _update_morse_display(self):
        """更新 Morse scratchpad 显示 (右对齐, 最长20字符)"""
        MAX_MORSE = 20
        text = self._morse_text[-MAX_MORSE:] if len(self._morse_text) > MAX_MORSE else self._morse_text
        if self._morse_display:
            self._morse_display._var_text = text
            self._morse_display.update()

    def _morse_start_blink(self):
        """启动确认闪烁 (500ms 间隔)"""
        if hasattr(self, '_morse_blink_timer'):
            self._morse_blink_timer.stop()
        self._morse_blink_phase = True
        self._morse_blink_timer = QTimer(self)
        self._morse_blink_timer.timeout.connect(self._morse_blink_tick)
        self._morse_blink_timer.start(500)
        self._morse_display._var_text = self._morse_text[-20:]
        self._morse_display.update()

    def _morse_blink_tick(self):
        """确认闪烁 tick"""
        self._morse_blink_phase = not self._morse_blink_phase
        if self._morse_display:
            self._morse_display._var_text = self._morse_text[-20:] if self._morse_blink_phase else ''
            self._morse_display.update()

    def _morse_start_output(self):
        """开始摩尔斯码输出 — 通过编队灯闪烁"""
        self._morse_outputting = True
        if hasattr(self, '_morse_blink_timer'):
            self._morse_blink_timer.stop()
        
        morse_str = text_to_morse(self._morse_text)
        if not morse_str.strip():
            self._morse_output_done()
            return
        
        # 构建信号序列: [(duration_ms, light_on), ...]
        self._morse_signals = []
        for ch in morse_str:
            if ch == '.':
                self._morse_signals.append((100, True))
                self._morse_signals.append((100, False))
            elif ch == '-':
                self._morse_signals.append((300, True))
                self._morse_signals.append((100, False))
            elif ch == ' ':
                if self._morse_signals:
                    d, on = self._morse_signals[-1]
                    if not on:
                        self._morse_signals[-1] = (d + 200, False)
            elif ch == '/':
                if self._morse_signals:
                    d, on = self._morse_signals[-1]
                    if not on:
                        self._morse_signals[-1] = (d + 400, False)
        
        self._morse_step = 0
        self._morse_total = len(self._morse_signals)
        self._morse_out_next()

    def _morse_out_next(self):
        """摩尔斯码输出下一步"""
        if self._morse_step >= self._morse_total:
            self._morse_output_done()
            return
        
        duration, light_on = self._morse_signals[self._morse_step]
        send_dcs_bios(MORSE_FORMATION_LIGHTS, 65535 if light_on else 0)
        
        done = int((self._morse_step + 1) / self._morse_total * 14)
        bar = '▓' * done + '░' * (14 - done)
        if self._morse_display:
            self._morse_display._var_text = bar
            self._morse_display.update()
        
        self._morse_step += 1
        QTimer.singleShot(duration, self._morse_out_next)

    def _morse_output_done(self):
        """输出完成: 显示 COMPLETE, 3秒后恢复"""
        self._morse_outputting = False
        send_dcs_bios(MORSE_FORMATION_LIGHTS, 0)
        if self._morse_display:
            self._morse_display._var_text = 'COMPLETE'
            self._morse_display.update()
        QTimer.singleShot(3000, self._morse_reset)

    def _morse_reset(self):
        """重置 Morse 状态"""
        self._morse_text = ''
        self._morse_confirmed = False
        self._update_morse_display()

    def _init_local_icp(self):
        """LOCAL ICP 页面 — 当前 UFC 布局"""

        # ============ 第0行: I/P(140) | 连体空白(425, 可变) | RTTH(255, 可变) | SETTINGS(140) ============
        self.place_cell("I/P", (0, 0), 8, 7, 140, 90, font_size=22)
        c = self.place_cell("", None, 164, 7, 425, 90, font_size=32, is_variable=True, register=False, no_feedback=True, var_align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.display_cells[(0, "blank")] = c
        c = self.place_cell("", (0, 4), 605, 7, 255, 90, font_size=28, is_variable=True)
        self.display_cells[(0, 4)] = c
        self.place_cell("SETTINGS", (0, 5), 876, 7, 140, 90, font_size=20)

        # ============ 第1行: SYSTEMS(140) | 1(121) | N2(121) | 3(121) | HSEL(255, 可变) | EM CON(140) ============
        self.place_cell("SYSTEMS", (1, 0), 8, 114, 140, 90, font_size=20)
        self.place_cell("1", (1, 1), 164, 114, 121, 90, font_size=22)
        self.place_cell("N\n2", (1, 2), 316, 114, 121, 90, font_size=18)
        self.place_cell("3", (1, 3), 468, 114, 121, 90, font_size=22)
        c = self.place_cell("", (1, 4), 605, 114, 255, 90, font_size=28, is_variable=True)
        self.display_cells[(1, 4)] = c
        self.place_cell("EM\nCON", (1, 5), 876, 114, 140, 90, font_size=20)

        # ============ 第2行: 空白(140) | W4(121) | 5(121) | E6(121) | BALT(255, 可变) | 空白(140) ============
        self.place_blank(8, 221, 140, 90)
        self.place_cell("W\n4", (2, 1), 164, 221, 121, 90, font_size=18)
        self.place_cell("5", (2, 2), 316, 221, 121, 90, font_size=22)
        self.place_cell("E\n6", (2, 3), 468, 221, 121, 90, font_size=18)
        c = self.place_cell("", (2, 4), 605, 221, 255, 90, font_size=28, is_variable=True)
        self.display_cells[(2, 4)] = c
        self.place_blank(876, 221, 140, 90)

        # ============ 第3行: COMM1(140) | 7(121) | S8(121) | 9(121) | RALT(255, 可变) | COMM2(140) ============
        self.place_cell("COMM 1", (3, 0), 8, 328, 140, 90, font_size=20)
        self.place_cell("7", (3, 1), 164, 328, 121, 90, font_size=22)
        self.place_cell("S\n8", (3, 2), 316, 328, 121, 90, font_size=18)
        self.place_cell("9", (3, 3), 468, 328, 121, 90, font_size=22)
        c = self.place_cell("", (3, 4), 605, 328, 255, 90, font_size=28, is_variable=True)
        self.display_cells[(3, 4)] = c
        self.place_cell("COMM 2", (3, 5), 876, 328, 140, 90, font_size=20)

        # ============ 第4行: COMM1(140,动态) | CLR(121) | 0(121) | ENT(121) | 空白(255, 可变) | COMM2(140,动态) ============
        c = self.place_cell("", (4, 0), 8, 435, 140, 90, font_size=32, is_variable=True, no_feedback=True)
        self.display_cells[(4, 0)] = c
        self.place_cell("CLR", (4, 1), 164, 435, 121, 90, font_size=18)
        self.place_cell("0", (4, 2), 316, 435, 121, 90, font_size=22)
        self.place_cell("ENT", (4, 3), 468, 435, 121, 90, font_size=18)
        c = self.place_cell("", (4, 4), 605, 435, 255, 90, font_size=28, is_variable=True)
        self.display_cells[(4, 4)] = c
        c = self.place_cell("", (4, 5), 876, 435, 140, 90, font_size=32, is_variable=True, no_feedback=True)
        self.display_cells[(4, 5)] = c

        # ============ 第5行: <(62) >(62) | A/P(80) | IFF(80) | TCN(80) | ILS(80) | D/L(80) | BCN(80) | ON(80) | <(62) >(62) ============
        y5 = 542
        h5 = 50
        self.place_cell("<", (5, 0), 8, y5, 62, h5, font_size=16)
        self.place_cell(">", (5, 1), 70, y5, 62, h5, font_size=16, bold=True)
        self.place_cell("A/P", (5, 2), 157, y5, 80, h5, font_size=13, bold=True)
        self.place_cell("IFF", (5, 3), 262, y5, 80, h5, font_size=13)
        self.place_cell("TCN", (5, 4), 367, y5, 80, h5, font_size=13)
        self.place_cell("ILS", (5, 5), 472, y5, 80, h5, font_size=13)
        self.place_cell("D/L", (5, 6), 577, y5, 80, h5, font_size=13)
        self.place_cell("BCN", (5, 7), 682, y5, 80, h5, font_size=13)
        self.place_cell("ON\nOFF", (5, 8), 787, y5, 80, h5, font_size=13)
        self.place_cell("<", (5, 9), 892, y5, 62, h5, font_size=16, bold=True)
        self.place_cell(">", (5, 10), 954, y5, 62, h5, font_size=16, bold=True)

    def _init_morse_light(self):
        """MORSE LIGHT 页面 — 左字母键盘 + 右小键盘(num lock) + 保留第5行"""
        # 字母区: 7列×102px, gap=6
        LX = [8, 116, 224, 332, 440, 548, 656]
        LW = 102
        # 小键盘区: 3列×79px, gap=6, 起始 x=766 (与字母区间隔 8px)
        NX = [766, 851, 936]
        NW = 79

        # Row 0: I/P(140) | SYSTEMS(140) | scratchpad空白长条(570) | EM CON(140)
        self.place_cell("I/P", (0, 0), 8, 7, 140, 90, font_size=20,
                        register=False, page="morse_light")
        self.place_cell("SYSTEMS", (1, 0), 154, 7, 140, 90, font_size=20,
                        register=False, page="morse_light")
        c = self.place_cell("", None, 300, 7, 570, 90, font_size=32, is_variable=True,
                            register=False, no_feedback=True, page="morse_light",
                            var_align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._morse_display = c
        self.place_cell("EM\nCON", (1, 5), 876, 7, 140, 90, font_size=20,
                        register=False, page="morse_light")

        # Row 1-3: 7字母 + 3小键盘数字 (共10键/行)
        letter_rows = [
            ['A','B','C','D','E','F','G'],   # Row 1
            ['H','I','J','K','L','M','N'],   # Row 2
            ['O','P','Q','R','S','T','U'],   # Row 3
        ]
        numpad_rows = [
            ['7','8','9'],  # Row 1 numpad
            ['4','5','6'],  # Row 2 numpad
            ['1','2','3'],  # Row 3 numpad
        ]
        row_ys = [114, 221, 328]
        key_idx = 0
        self._morse_pos_to_key = {}  # pos → key_char
        for row_i in range(3):
            y = row_ys[row_i]
            for col_i, key_text in enumerate(letter_rows[row_i]):
                pos = (20, key_idx)
                self._morse_pos_to_key[pos] = key_text
                self.place_cell(key_text, pos, LX[col_i], y, LW, 90,
                                font_size=22, page="morse_light")
                key_idx += 1
            for col_i, key_text in enumerate(numpad_rows[row_i]):
                pos = (20, key_idx)
                self._morse_pos_to_key[pos] = key_text
                self.place_cell(key_text, pos, NX[col_i], y, NW, 90,
                                font_size=22, page="morse_light")
                key_idx += 1

        # Row 4: V W X Y Z SPACE(跨2列=210) | CLR 0 ENT (小键盘底行)
        y4 = 435
        for col_i, key_text in enumerate(['V','W','X','Y','Z']):
            pos = (20, key_idx)
            self._morse_pos_to_key[pos] = key_text
            self.place_cell(key_text, pos, LX[col_i], y4, LW, 90,
                            font_size=22, page="morse_light")
            key_idx += 1
        # SPACE 跨字母区 col5+col6
        pos = (20, key_idx)
        self._morse_pos_to_key[pos] = "SPACE"
        self.place_cell("SPACE", pos, LX[5], y4, LW * 2 + 6, 90,
                        font_size=16, page="morse_light")
        key_idx += 1
        for col_i, key_text in enumerate(['CLR','0','ENT']):
            pos = (20, key_idx)
            self._morse_pos_to_key[pos] = key_text
            self.place_cell(key_text, pos, NX[col_i], y4, NW, 90,
                            font_size=18, page="morse_light")
            key_idx += 1

        # Row 5: COMM1/2 < > 用pos(50,x)禁用DCS-BIOS, A/P~ONOFF保持原pos直发DCS-BIOS
        y5, h5 = 542, 50
        self.place_cell("<", (50, 0), 8, y5, 62, h5, font_size=16,
                        register=False, page="morse_light")
        self.place_cell(">", (50, 1), 70, y5, 62, h5, font_size=16, bold=True,
                        register=False, page="morse_light")
        self.place_cell("A/P", (5, 2), 157, y5, 80, h5, font_size=13, bold=True,
                        register=False, page="morse_light")
        self.place_cell("IFF", (5, 3), 262, y5, 80, h5, font_size=13,
                        register=False, page="morse_light")
        self.place_cell("TCN", (5, 4), 367, y5, 80, h5, font_size=13,
                        register=False, page="morse_light")
        self.place_cell("ILS", (5, 5), 472, y5, 80, h5, font_size=13,
                        register=False, page="morse_light")
        self.place_cell("D/L", (5, 6), 577, y5, 80, h5, font_size=13,
                        register=False, page="morse_light")
        self.place_cell("BCN", (5, 7), 682, y5, 80, h5, font_size=13,
                        register=False, page="morse_light")
        self.place_cell("ON\nOFF", (5, 8), 787, y5, 80, h5, font_size=13,
                        register=False, page="morse_light")
        self.place_cell("<", (50, 9), 892, y5, 62, h5, font_size=16, bold=True,
                        register=False, page="morse_light")
        self.place_cell(">", (50, 10), 954, y5, 62, h5, font_size=16, bold=True,
                        register=False, page="morse_light")

    def _init_system_select(self):
        """系统选择页面 — 5个选项"""
        # Row 0: SYSTEMS(返回) | "SYSTEM SELECT" 显示
        self.place_cell("BACK", (200, 0), 8, 7, 140, 90, font_size=20,
                        register=False, page="select")
        self.place_cell("SYSTEM SELECT", None, 164, 7, 852, 90, font_size=28,
                        is_variable=True, register=False, no_feedback=True,
                        page="select")

        # 5个选项 (Row 1-5)
        menu = TouchMenuScroll(self)
        menu._page = "select"
        menu.setGeometry(8, 114, 1008, 478)
        menu.menuActivated.connect(self.on_cell_click)
        self._widget_origins.append((menu, 8, 114, 1008, 478, 0))
        self._select_menu = menu

        options = [
            ("1  LOCAL ICP",     (201, 0), True),
            ("2  MORSE LIGHT",   (201, 1), True),
            ("3  LIGHT CONTROL",  (201, 2), True),
            ("4  SYSTEM 4",       (201, 3), True),
        ]
        options.extend(
            (f"{number}  (RESERVED)", (201, number - 1), False)
            for number in range(5, 16)
        )
        for index, (text, pos, active) in enumerate(options):
            cell = menu.add_menu_item(text, pos, index, active=active, font_size=22)
            self._select_cells[pos] = cell

    def _init_light_control(self):
        """LIGHT CONTROL 页面 — 左侧手动控制 + 右侧预设模式"""
        COLS = [8, 164, 316, 468, 605, 876]
        CW   = [140, 121, 121, 121, 255, 140]
        RY   = [7, 114, 221, 328, 435, 542]
        RH   = [90, 90, 90, 90, 90, 50]

        # Row 0: I/P(140) | SYSTEMS(140) | LIGHT CONTROL title(712)
        self.place_cell("I/P", (0, 0), COLS[0], RY[0], CW[0], RH[0], font_size=20,
                        register=False, page="light_control")
        self.place_cell("SYSTEMS", (1, 0), COLS[1], RY[0], CW[1], RH[0], font_size=20,
                        register=False, page="light_control")
        self.place_cell("LIGHT\nCONTROL", None, COLS[2], RY[0], 700, RH[0],
                        font_size=28, is_variable=True, register=False, no_feedback=True, page="light_control")

        # 4行灯光手动控制 (Row 1-4)
        lights = [
            ('ldg',   "LDG\nTAXI",    LDG_STATES,    DCS_LDG_TAXI, 2),     # 2档: OFF/ON
            ('form',  "FORM\nLT",     None,          DCS_FORM,     11),    # 旋钮 0-65535
            ('pos',   "POS\nLT",      None,          DCS_POSITION, 11),    # 旋钮 0-65535
            ('strobe',"STROBE",       STROBE_STATES, DCS_STROBE_SW,3),     # 3档: OFF/DIM/BRIGHT
        ]
        for row_i, (key, label, states, dcs_id, n_states) in enumerate(lights):
            r = row_i + 1
            y = RY[r]; h = RH[r]
            # 标签
            self.place_cell(label, (30, row_i), COLS[0], y, CW[0], h, font_size=18,
                            register=False, page="light_control")
            # 状态显示 (variable)
            c = self.place_cell("", (31, row_i), COLS[1], y, CW[1], h, font_size=18,
                                is_variable=True, register=False, no_feedback=True, page="light_control")
            self._light_displays[key] = c
            # ◀ (减小/切换)
            self.place_cell("\u25C0", (32, row_i), COLS[2], y, CW[2], h, font_size=16,
                            register=False, page="light_control")
            # ▶ (增大/切换)
            self.place_cell("\u25B6", (33, row_i), COLS[3], y, CW[3], h, font_size=16,
                            register=False, page="light_control")

        # 右侧预设模式 (cols 4-5, 合并为宽按钮)
        presets = [
            ("COVERT",     (34, 0), {'ldg':0, 'form':0,     'pos':0,     'strobe':1}),
            ("DAY",        (34, 1), {'ldg':0, 'form':0,     'pos':0,     'strobe':0}),
            ("NIGHT",      (34, 2), {'ldg':0, 'form':65535, 'pos':65535, 'strobe':0}),
            ("LDG",        (34, 3), {'ldg':1, 'form':65535, 'pos':65535, 'strobe':0}),
        ]
        PR_X = COLS[4]  # 605
        PR_W = CW[4] + 16 + CW[5]  # 255+16+140=411
        for row_i, (text, pos, config) in enumerate(presets):
            r = row_i + 1
            self.place_cell(text, pos, PR_X, RY[r], PR_W, RH[r], font_size=20,
                            register=False, page="light_control", bold=True)

        # Row 5: 原底部功能按钮 (pos 保留, register=False)
        y5, h5 = RY[5], RH[5]
        r5_btns = [
            ("<", (50,0), 8,62), (">", (50,1), 70,62),
            ("A/P", (5,2), 157,80), ("IFF", (5,3), 262,80),
            ("TCN", (5,4), 367,80), ("ILS", (5,5), 472,80),
            ("D/L", (5,6), 577,80), ("BCN", (5,7), 682,80),
            ("ON\nOFF", (5,8), 787,80),
            ("<", (50,9), 892,62), (">", (50,10), 954,62),
        ]
        for text, pos, x, w in r5_btns:
            self.place_cell(text, pos, x, y5, w, h5, font_size=13 if w>=80 else 16,
                            register=False, page="light_control")
        
        # 初始化显示
        self._update_light_display('ldg')
        self._update_light_display('form')
        self._update_light_display('pos')
        self._update_light_display('strobe')

    def _update_light_display(self, key):
        """刷新指定灯的状态显示"""
        cell = self._light_displays.get(key)
        if not cell:
            return
        if key == 'ldg':
            cell._var_text = LDG_STATES[self._light_state['ldg']]
        elif key == 'form':
            cell._var_text = str(int(self._light_state['form'] / 65535 * 100))
        elif key == 'pos':
            cell._var_text = str(int(self._light_state['pos'] / 65535 * 100))
        elif key == 'strobe':
            cell._var_text = STROBE_STATES[self._light_state['strobe']]
        cell.update()

    def _light_button(self, light_key, direction):
        """灯光控制: direction='up' 或 'down'"""
        state = self._light_state
        if light_key == 'ldg':
            if direction == 'up':
                state['ldg'] = min(state['ldg'] + 1, 1)
            else:
                state['ldg'] = max(state['ldg'] - 1, 0)
            self._light_last_local['ldg'] = time.time()
            send_dcs_bios(DCS_LDG_TAXI, state['ldg'])
            self._update_light_display('ldg')
        elif light_key == 'form':
            if direction == 'up':
                state['form'] = min(state['form'] + FORM_STEP, 65535)
            else:
                state['form'] = max(state['form'] - FORM_STEP, 0)
            self._light_last_local['form'] = time.time()
            send_dcs_bios(DCS_FORM, state['form'])
            self._update_light_display('form')
        elif light_key == 'pos':
            if direction == 'up':
                state['pos'] = min(state['pos'] + FORM_STEP, 65535)
            else:
                state['pos'] = max(state['pos'] - FORM_STEP, 0)
            self._light_last_local['pos'] = time.time()
            send_dcs_bios(DCS_POSITION, state['pos'])
            self._update_light_display('pos')
        elif light_key == 'strobe':
            # 显示顺序: OFF(1)←→DIM(2)←→BRI(0), 两端不可越界
            cur = state['strobe']
            if direction == 'up':
                new_val = {1: 2, 2: 0}.get(cur, cur)  # OFF→DIM→BRI (stop)
            else:
                new_val = {0: 2, 2: 1}.get(cur, cur)  # BRI→DIM→OFF (stop)
            if new_val == cur:
                return
            state['strobe'] = new_val
            self._light_last_local['strobe'] = time.time()
            send_dcs_bios(DCS_STROBE_SW, new_val)
            self._update_light_display('strobe')

    def _light_preset(self, config: dict):
        """应用灯光预设"""
        now = time.time()
        for key, val in config.items():
            self._light_state[key] = val
            self._light_last_local[key] = now
            if key == 'ldg':
                send_dcs_bios(DCS_LDG_TAXI, val)
                self._update_light_display('ldg')
            elif key == 'form':
                send_dcs_bios(DCS_FORM, val)
                self._update_light_display('form')
            elif key == 'pos':
                send_dcs_bios(DCS_POSITION, val)
                self._update_light_display('pos')
            elif key == 'strobe':
                send_dcs_bios(DCS_STROBE_SW, val)
                self._update_light_display('strobe')

    def place_cell(self, text, pos, x, y, w, h, font_size=16, is_variable=False, bold=False, register=True, no_feedback=False, var_align=None, page="local_icp"):
        cell = UFCCell(text, pos, font_size=font_size, is_variable=is_variable, bold=bold, parent=self, no_feedback=no_feedback, var_align=var_align)
        cell._page = page
        cell.setGeometry(x, y, w, h)
        # 记录原始坐标用于缩放
        self._widget_origins.append((cell, x, y, w, h, font_size))
        if pos is not None:
            cell.clicked.connect(self.on_cell_click)
            if register:
                if page == "local_icp":
                    self.cells[pos] = cell
                elif page == "morse_light":
                    self._morse_cells[pos] = cell
                elif page == "select":
                    self._select_cells[pos] = cell
        return cell

    def place_blank(self, x, y, w, h, page="local_icp"):
        blank = UFCBlank(parent=self, bordered=False)
        blank._page = page
        blank.setGeometry(x, y, w, h)
        self._widget_origins.append((blank, x, y, w, h, 0))
        return blank

    def place_bordered_blank(self, x, y, w, h, page="local_icp"):
        """放置一个有边框的空白连体方块"""
        blank = UFCBlank(parent=self, bordered=True)
        blank._page = page
        blank.setGeometry(x, y, w, h)
        self._blanks.append(blank)
        self._widget_origins.append((blank, x, y, w, h, 0))
        return blank

    def on_cell_click(self, pos):
        """UFCCell 点击回调。DCS-BIOS press/release 已由 UFCCell 内部处理，
        这里管页面切换 + 日志。"""
        # ==== 页面切换逻辑 ====
        # SYSTEMS 按钮 (pos 1,0) — 任何页面都进入选择页
        if pos == (1, 0):
            self._show_page("select")
            return
        # 选择页面：SYSTEMS 返回 (pos 200,0)
        if pos == (200, 0):
            self._show_page(self._previous_page)
            return
        # 选择页面：选项点击
        if self._current_page == "select":
            if pos == (201, 0):      # LOCAL ICP
                self._show_page("local_icp")
                return
            elif pos == (201, 1):    # MORSE LIGHT
                self._show_page("morse_light")
                return
            elif pos == (201, 2):    # LIGHT CONTROL
                self._show_page("light_control")
                return
            # pos (201,3)~(201,4): 预留选项，暂不处理
            return

        # ==== LIGHT CONTROL 页面：灯光手动控制 + 预设 ====
        if self._current_page == "light_control":
            row_i = pos[1] if isinstance(pos, tuple) and len(pos) == 2 else None
            ts = time.strftime("%H:%M:%S", time.localtime())
            if pos[0] == 32 and row_i is not None:  # ◀
                keys = ['ldg', 'form', 'pos', 'strobe']
                if 0 <= row_i < len(keys):
                    self._light_button(keys[row_i], 'down')
            elif pos[0] == 33 and row_i is not None:  # ▶
                keys = ['ldg', 'form', 'pos', 'strobe']
                if 0 <= row_i < len(keys):
                    self._light_button(keys[row_i], 'up')
            elif pos[0] == 34 and row_i is not None:  # 预设
                presets_dicts = [
                    {'ldg':0, 'form':0,     'pos':0,     'strobe':1},   # COVERT
                    {'ldg':0, 'form':0,     'pos':0,     'strobe':0},   # DAY
                    {'ldg':0, 'form':65535, 'pos':65535, 'strobe':0},   # NIGHT
                    {'ldg':1, 'form':65535, 'pos':65535, 'strobe':0},   # LDG
                ]
                if 0 <= row_i < len(presets_dicts):
                    self._light_preset(presets_dicts[row_i])
            self._key_press_log.append((ts, f"LIGHT:{pos}"))
            if len(self._key_press_log) > 50:
                self._key_press_log.pop(0)
            self.keyLogUpdated.emit(ts, f"LIGHT:{pos}")
            return

        # ==== Morse Light 页面：输入/命令处理 ====
        if self._current_page == "morse_light":
            ts = time.strftime("%H:%M:%S", time.localtime())
            
            # 获取按键字符
            key_char = self._morse_pos_to_key.get(pos)
            if key_char is None:
                # Row 5 / Row 0 按钮
                key_char = BUTTON_TEXTS.get(pos, '').replace('\n', ' ')
            
            # 如果正在输出或确认中，按非 ENT 键取消确认
            if self._morse_confirmed and not self._morse_outputting:
                if key_char not in ('ENT',):
                    self._morse_confirmed = False
                    if hasattr(self, '_morse_blink_timer'):
                        self._morse_blink_timer.stop()
                    self._morse_display._var_text = self._morse_text
                    self._morse_display.update()
                    self._key_press_log.append((ts, f"MORSE:CANCEL"))
                    return
            
            if self._morse_outputting:
                return  # 输出中忽略所有输入
            
            # -- 字母/数字/空格 → 追加到 scratchpad --
            if key_char == 'SPACE':
                self._morse_text += ' '
                self._update_morse_display()
            elif key_char is not None and len(key_char) == 1 and key_char in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789':
                self._morse_text += key_char
                self._update_morse_display()
            # -- CLR → 清空 --
            elif key_char == 'CLR':
                self._morse_text = ''
                self._morse_confirmed = False
                if hasattr(self, '_morse_blink_timer'):
                    self._morse_blink_timer.stop()
                self._update_morse_display()
            # -- ENT → 确认 / 输出 --
            elif key_char == 'ENT':
                if not self._morse_text:
                    return
                if not self._morse_confirmed:
                    self._morse_confirmed = True
                    self._morse_start_blink()
                elif not self._morse_outputting:
                    self._morse_start_output()
            # -- 其他键 (I/P, EM CON, Row 5) — 不做 Morse 处理 --
            
            if len(self._key_press_log) > 50:
                self._key_press_log.pop(0)
            self.keyLogUpdated.emit(ts, f"MORSE:{key_char}")
            return

        # ==== LOCAL ICP 页面：原有日志逻辑 ====
        bios_entry = UFC_BIOS_MAP.get(pos)

        # 记录按键日志
        ts = time.strftime("%H:%M:%S", time.localtime())
        if isinstance(bios_entry, tuple):
            log_key = f"{bios_entry[0]} {bios_entry[1]}"
        else:
            log_key = bios_entry or "—"
        self._key_press_log.append((ts, log_key))
        if len(self._key_press_log) > 50:
            self._key_press_log.pop(0)
        self.keyLogUpdated.emit(ts, log_key)

    def simulate_keypress(self, key):
        """使用 Windows SendInput API 发送系统级按键到前台窗口（DCS）。
        支持组合键: Ctrl+C, LAlt+C, Shift+Tab 等。"""
        inject_key_combo(key)

    def keyPressEvent(self, event: QKeyEvent):
        super().keyPressEvent(event)

    def resizeEvent(self, event):
        """窗口尺寸变化时，等比缩放所有子控件，始终保持 1024x600 原始比例"""
        super().resizeEvent(event)
        new_w = event.size().width()
        new_h = event.size().height()
        self._rescale_children(new_w, new_h)

    def _rescale_children(self, win_w, win_h):
        """
        根据窗口实际尺寸计算缩放因子，重新排布所有子控件。
        保持原始 1024x600 比例不变：用 min(sx, sy) 作为统一缩放系数，
        并将内容居中（letterbox 黑边填充）。
        """
        if not self._widget_origins:
            return

        sx = win_w / self.DESIGN_W
        sy = win_h / self.DESIGN_H
        # 等比缩放：取较小方向，防止内容拉伸
        s = min(sx, sy)

        # 内容区域实际大小
        content_w = int(self.DESIGN_W * s)
        content_h = int(self.DESIGN_H * s)

        # 居中偏移（letterbox 黑边）
        offset_x = (win_w - content_w) // 2
        offset_y = (win_h - content_h) // 2

        for widget, ox, oy, ow, oh, ofont in self._widget_origins:
            nx = offset_x + int(ox * s)
            ny = offset_y + int(oy * s)
            nw = max(1, int(ow * s))
            nh = max(1, int(oh * s))
            widget.setGeometry(nx, ny, nw, nh)

            # 更新字体大小（仅 UFCCell）
            if ofont > 0 and isinstance(widget, UFCCell):
                new_font_size = max(6, int(ofont * s))
                widget.rescale_font(new_font_size)
            elif isinstance(widget, TouchMenuScroll):
                widget.rescale_content(s)

    def closeEvent(self, event):
        """窗口关闭时停止所有后台线程"""
        print("[UFC] Stopping DCS-BIOS receiver...")
        if hasattr(self, 'dcs_bios'):
            self.dcs_bios.stop()
        print("[UFC] Stopping WH_MOUSE_LL hook...")
        _stop_mouse_hook()
        event.accept()


class SettingsWindow(QWidget):
    """设置窗口 - 始终在主屏显示"""
    def __init__(self, key_panel):
        super().__init__()
        self.setWindowTitle("UFC Keypad - Settings")
        self.setMinimumSize(850, 600)
        self.resize(750, 650)

        self.key_panel = key_panel
        self._key_log_lines = []  # 按键日志行缓存

        self.setStyleSheet("""
            QWidget {
                background-color: #1a1a2e;
                color: #e0e0e0;
                font-family: 'Microsoft YaHei', 'Segoe UI';
                font-size: 12px;
            }
            QGroupBox {
                border: 1px solid #3a3a6a;
                border-radius: 6px;
                margin-top: 10px;
                font-weight: bold;
                padding: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
                color: #a78bfa;
            }
            QComboBox {
                background: #16162a;
                border: 1px solid #3a3a6a;
                border-radius: 3px;
                padding: 3px 6px;
                color: #e0e0e0;
            }
            QComboBox QAbstractItemView {
                background: #16162a;
                border: 1px solid #3a3a6a;
                color: #e0e0e0;
                selection-background-color: #3d3d6a;
            }
            QPushButton {
                background: #2d2d4a;
                border: 1px solid #4a4a7a;
                border-radius: 4px;
                padding: 6px 14px;
                min-width: 80px;
            }
            QPushButton:hover { background: #3d3d6a; }
            QPushButton#primary {
                background: #5a3daa;
                color: white;
                font-weight: bold;
            }
            QPushButton#primary:hover { background: #7a5dca; }
            QPushButton#danger {
                background: #aa3d3d;
                color: white;
            }
            QPushButton#danger:hover { background: #cc5555; }
        """)

        self.init_ui()
        self.refresh_screen_list()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 12, 12, 12)

        title = QLabel("UFC Keypad 设置面板")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #a78bfa;")
        layout.addWidget(title)

        # 显示器选择
        screen_group = QGroupBox("显示器选择")
        screen_lo = QHBoxLayout(screen_group)

        screen_lo.addWidget(QLabel("输出到显示器:"))
        self.screen_combo = QComboBox()
        self.screen_combo.setMinimumWidth(200)
        screen_lo.addWidget(self.screen_combo)

        self.fullscreen_cb = QCheckBox("全屏")
        self.fullscreen_cb.setChecked(True)
        screen_lo.addWidget(self.fullscreen_cb)

        self.always_top_cb = QCheckBox("置顶")
        self.always_top_cb.setChecked(False)
        screen_lo.addWidget(self.always_top_cb)

        # 缩放倍率（非全屏时有效）
        screen_lo.addWidget(QLabel("倍率:"))
        self.scale_spin = QDoubleSpinBox()
        self.scale_spin.setRange(0.25, 4.0)
        self.scale_spin.setSingleStep(0.25)
        self.scale_spin.setValue(1.0)
        self.scale_spin.setDecimals(2)
        self.scale_spin.setFixedWidth(70)
        self.scale_spin.setToolTip(
            "窗口缩放倍率（仅非全屏模式有效）\n"
            "1.0 = 1024×600 原始尺寸\n"
            "1.5 = 1536×900\n"
            "全屏模式下倍率由屏幕分辨率决定"
        )
        # 全屏勾选时灰掉倍率输入框
        self.fullscreen_cb.toggled.connect(lambda checked: self.scale_spin.setEnabled(not checked))
        self.scale_spin.setEnabled(not self.fullscreen_cb.isChecked())
        screen_lo.addWidget(self.scale_spin)

        screen_lo.addStretch()

        self.apply_screen_btn = QPushButton("应用显示器")
        self.apply_screen_btn.clicked.connect(self.apply_screen)
        screen_lo.addWidget(self.apply_screen_btn)

        self.refresh_screen_btn = QPushButton("刷新")
        self.refresh_screen_btn.clicked.connect(self.refresh_screen_list)
        screen_lo.addWidget(self.refresh_screen_btn)

        layout.addWidget(screen_group)

        # ==== 原生触控隔离（方案四：保底手段） ====
        touch_group = QGroupBox("触控隔离 (副屏触摸不抢主屏鼠标)")
        touch_lo = QHBoxLayout(touch_group)
        self.native_touch_cb = QCheckBox("启用原生触控隔离 (RegisterTouchWindow + FINETOUCH)")
        self.native_touch_cb.setToolTip(
            "阻止 Windows 将副屏触摸转换为鼠标事件，避免光标跳到副屏导致 DCS 失焦。\n"
            "启用后副屏触摸仅操作 UFC 面板，不会影响主屏游戏。\n"
            "⚠ 需要管理员权限运行才能生效。"
        )
        # 加载已保存的偏好
        config = load_config()
        self.native_touch_cb.setChecked(config.get("native_touch", False))
        self.native_touch_cb.toggled.connect(self._on_native_touch_toggled)
        touch_lo.addWidget(self.native_touch_cb)
        touch_lo.addStretch()
        layout.addWidget(touch_group)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #8888aa; font-size: 11px;")
        layout.addWidget(self.status_label)

        # ==== 按键输入日志 ====
        log_group = QGroupBox("按键输入记录 (最近 50 条)")
        log_lo = QVBoxLayout(log_group)
        self.key_log_text = QTextEdit()
        self.key_log_text.setReadOnly(True)
        self.key_log_text.setMaximumHeight(150)
        self.key_log_text.setStyleSheet("""
            QTextEdit {
                background: #0d0d1a;
                color: #a0a0c0;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 11px;
                border: 1px solid #2a2a4a;
                border-radius: 4px;
                padding: 4px;
            }
        """)
        log_lo.addWidget(self.key_log_text)
        layout.addWidget(log_group)

        # 连接 UFC 面板的按键日志信号
        self.key_panel.keyLogUpdated.connect(self._on_key_log)
        self._flush_log()  # 显示已有的日志（如果有）

    def _on_key_log(self, ts, key):
        """接收 UFC 面板按键日志"""
        self._key_log_lines.append(f"[{ts}] {key}")
        if len(self._key_log_lines) > 50:
            self._key_log_lines.pop(0)
        self._flush_log()

    def _flush_log(self):
        """刷新日志显示（最新在最上面）"""
        if self._key_log_lines:
            # _key_log_lines 存的是已格式化的字符串
            text = "\n".join(reversed(self._key_log_lines[-50:]))
        else:
            # 回退：_key_press_log 存的是 (ts, key) 元组
            lines = self.key_panel._key_press_log
            text = "\n".join(f"[{t}] {k}" for t, k in reversed(lines[-50:]))
        self.key_log_text.setPlainText(text)

    def refresh_screen_list(self):
        self.screen_combo.clear()
        screens = QApplication.screens()
        for i, screen in enumerate(screens):
            geo = screen.geometry()
            name = screen.name()
            self.screen_combo.addItem(
                f"显示器 {i}: {name} ({geo.width()}x{geo.height()})",
                userData=i
            )

    def _on_native_touch_toggled(self, checked):
        """原生触控隔离开关"""
        self.key_panel.enable_native_touch(checked)
        if checked:
            self.status_label.setText("原生触控隔离已启用 — 触摸不再抢鼠标")
        else:
            self.status_label.setText("原生触控隔离已关闭")

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

        self.key_panel.showNormal()
        self.key_panel.move(geo.x(), geo.y())
        # 不再 setFixedSize，让窗口自适应目标屏幕分辨率
        # 非全屏时设为原始设计尺寸，全屏时由 showFullScreen 决定

        if self.fullscreen_cb.isChecked():
            self.key_panel.showFullScreen()
        else:
            ratio = self.scale_spin.value()
            scaled_w = int(round(WIN_W * ratio))
            scaled_h = int(round(WIN_H * ratio))
            self.key_panel.resize(scaled_w, scaled_h)

        if self.always_top_cb.isChecked():
            self.key_panel.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        else:
            self.key_panel.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, False)

        self.key_panel.show()

        self.status_label.setText(f"已输出到显示器 {idx}: {screen.name()} "
                                  f"{'全屏' if self.fullscreen_cb.isChecked() else '窗口'}")

    def closeEvent(self, event):
        """关闭设置窗口 → 退出整个程序"""
        QApplication.quit()


# ============ 入口 ============
