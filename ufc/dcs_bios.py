# -*- coding: utf-8 -*-
"""DCS-BIOS 通信层：UDP 解析器 + 接收线程 + 指令发送"""
import json
import os
import socket
import struct
import threading
import time
from collections import defaultdict

_DCS_BIOS_CMD_ADDR = ("127.0.0.1", 7778)
_dcs_bios_cmd_sock = None

# DCS Saved Games 目录候选。用户可以通过环境变量覆盖：
#   UFC_DCSBIOS_DOC=<...>\Scripts\DCS-BIOS\doc
#   DCS_BIOS_DOC=<...>\Scripts\DCS-BIOS\doc
#   SAVED_GAMES=<...>\Saved Games
_DCS_SAVED_GAMES_DIRS = (
    "DCS",
    "DCS.openbeta",
    "DCS.openbeta_server",
)


def _get_bios_cmd_sock():
    """获取 DCS-BIOS 命令发送 socket（单例）"""
    global _dcs_bios_cmd_sock
    if _dcs_bios_cmd_sock is None:
        _dcs_bios_cmd_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    return _dcs_bios_cmd_sock


def send_dcs_bios(identifier: str, value):
    """发送 DCS-BIOS 控制命令。
    value: int (1/0 模拟按钮按下/释放) 或 str (INC/DEC 步进, TOGGLE 切换)"""
    try:
        sock = _get_bios_cmd_sock()
        msg = f"{identifier} {value}\n".encode("utf-8")
        sock.sendto(msg, _DCS_BIOS_CMD_ADDR)
        return True
    except Exception as e:
        print(f"[DCS-BIOS] 发送失败: {e}")
        return False


def dcs_bios_click(identifier: str):
    """模拟一次完整点击（按下+释放）。DCS-BIOS 处理时序，无需 delay。"""
    send_dcs_bios(identifier, 1)
    send_dcs_bios(identifier, 0)



def _send_release(identifier: str):
    """发送 release(0) 命令（由 QTimer.singleShot 延迟调用）"""
    send_dcs_bios(identifier, 0)


# 最小按压时间（毫秒），确保 press/release 两个 UDP 包落在不同 DCS 帧
_MIN_PRESS_MS = 50


# UFC 格子位置 → DCS-BIOS 按钮标识符映射
# 值类型:
#   str           → PushButton: press 发 "1", release 发 "0"（UFCCell 内部处理）
#   (str, str)    → 单次命令: 如 ("UFC_COMM1_PULL", "TOGGLE") 或 ("...", "INC")
UFC_BIOS_MAP = {
    # 数字键（PushButton → press/release 1/0，UFCCell 内部处理）
    (1, 1): "UFC_1",
    (1, 2): "UFC_2",
    (1, 3): "UFC_3",
    (2, 1): "UFC_4",
    (2, 2): "UFC_5",
    (2, 3): "UFC_6",
    (3, 1): "UFC_7",
    (3, 2): "UFC_8",
    (3, 3): "UFC_9",
    (4, 2): "UFC_0",
    # 功能键（PushButton → press/release）
    (4, 1): "UFC_CLR",
    (4, 3): "UFC_ENT",
    # 顶部功能键（PushButton → press/release）
    (0, 0): "UFC_IP",
    # 底部功能键（PushButton → press/release）
    (5, 2): "UFC_AP",
    (5, 3): "UFC_IFF",
    (5, 4): "UFC_TCN",
    (5, 5): "UFC_ILS",
    (5, 6): "UFC_DL",
    (5, 7): "UFC_BCN",
    (5, 8): "UFC_ONOFF",
    # 选项选择按钮（OSB 1-5，PushButton → press/release）
    (0, 4): "UFC_OS1",
    (1, 4): "UFC_OS2",
    (2, 4): "UFC_OS3",
    (3, 4): "UFC_OS4",
    (4, 4): "UFC_OS5",
    # EM CON（无线电静默，PushButton → press/release）
    (1, 5): "UFC_EMCON",
    # COMM 频道旋钮（左右转，FixedStepInput → INC/DEC）
    (5, 0): ("UFC_COMM1_CHANNEL_SELECT", "DEC"),
    (5, 1): ("UFC_COMM1_CHANNEL_SELECT", "INC"),
    (5, 9): ("UFC_COMM2_CHANNEL_SELECT", "DEC"),
    (5, 10): ("UFC_COMM2_CHANNEL_SELECT", "INC"),
    # COMM Pull（拉起/按下 → press/release：按住拉出，松开放下）
    (3, 0): "UFC_COMM1_PULL",
    (3, 5): "UFC_COMM2_PULL",
}


def _candidate_dcs_bios_doc_dirs():
    """返回可能包含 Addresses.h / json/FA-18C_hornet.json 的 DCS-BIOS doc 目录。"""
    seen = set()
    candidates = []

    # 1) 显式覆盖：直接指向 DCS-BIOS/doc
    for env_name in ("UFC_DCSBIOS_DOC", "DCS_BIOS_DOC"):
        value = os.environ.get(env_name)
        if value:
            path = os.path.abspath(os.path.expandvars(os.path.expanduser(value)))
            if path not in seen:
                seen.add(path)
                candidates.append(path)

    # 2) Saved Games 根目录：默认 ~/Saved Games，可用 SAVED_GAMES 覆盖
    saved_games_roots = []
    env_saved_games = os.environ.get("SAVED_GAMES")
    if env_saved_games:
        saved_games_roots.append(env_saved_games)
    userprofile = os.environ.get("USERPROFILE")
    if userprofile:
        saved_games_roots.append(os.path.join(userprofile, "Saved Games"))
    saved_games_roots.append(os.path.expanduser(os.path.join("~", "Saved Games")))

    for root in saved_games_roots:
        root = os.path.abspath(os.path.expandvars(os.path.expanduser(root)))
        for dcs_dir in _DCS_SAVED_GAMES_DIRS:
            doc_dir = os.path.join(root, dcs_dir, "Scripts", "DCS-BIOS", "doc")
            if doc_dir not in seen:
                seen.add(doc_dir)
                candidates.append(doc_dir)

    return candidates


def _address_file_candidates():
    """返回 (Addresses.h, FA-18C_hornet.json) 候选路径列表。"""
    pairs = []
    for doc_dir in _candidate_dcs_bios_doc_dirs():
        pairs.append((
            os.path.join(doc_dir, "Addresses.h"),
            os.path.join(doc_dir, "json", "FA-18C_hornet.json"),
        ))
    return pairs


def _decode_json_address(addr):
    """兼容 DCS-BIOS JSON 中 int / 十进制字符串 / 0x 十六进制字符串地址。"""
    if isinstance(addr, int):
        return addr
    if isinstance(addr, str):
        text = addr.strip()
        if not text:
            return None
        try:
            return int(text, 16) if text.lower().startswith("0x") else int(text)
        except ValueError:
            return None
    return None


class DCSBIOSParser:
    """
    DCS-BIOS Skunkworks 协议解析器

    帧结构（BIOSStateMachine:step + MemoryMap:flushData）：
      - 帧同步：4字节 0x55 0x55 0x55 0x55
      - 数据记录：[Address:2LE][Length:2LE][Data:N_bytes]
        - Address/Data 都是 2-byte word 编码（encodeInt: lowbyte, highbyte）
        - Length 是字节数（2的倍数）
        - Data 中每个 word 的低字节=ASCII字符，高字节=0x00（字符串）

    多个模块的 flushData 输出拼接在一起，每个模块可能产生多个数据记录
    """

    # Skunkworks 版帧同步：4个 0x55 连续字节
    FRAME_SYNC = b'\x55\x55\x55\x55'

    def __init__(self):
        self.buffer = bytearray()
        # 状态内存：address -> word value（每个地址2字节）
        self.state = bytearray(65536)
        # 地址→字段名 映射
        self.address_to_field = {}  # {address: (field_name, length)} — 字符串字段
        self.analog_addresses = {}   # {address: internal_name} — 模拟量字段 (uint16 → 0.0~1.0)
        self.integer_addrs = {}      # {address: (internal_name, mask, shift)} — 整数字段
        self.synced = False

    def inject_address_map(self, addr_map: dict):
        """注入地址→字段名映射，格式: {address: (field_name, length)}"""
        self.address_to_field = addr_map

    def _find_sync(self) -> int:
        """在 buffer 中搜索帧同步字节序列，返回其起始位置"""
        try:
            return self.buffer.index(self.FRAME_SYNC)
        except ValueError:
            return -1

    def _extract_record(self, offset: int):
        """
        从 buffer[offset:] 提取一条数据记录
        返回 (address, consumed_bytes, written_addresses) 或 None
        """
        if offset + 4 > len(self.buffer):
            return None

        addr_lo = self.buffer[offset]
        addr_hi = self.buffer[offset + 1]
        address = addr_lo | (addr_hi << 8)

        len_lo = self.buffer[offset + 2]
        len_hi = self.buffer[offset + 3]
        length = len_lo | (len_hi << 8)

        if offset + 4 + length > len(self.buffer):
            return None  # 数据不完整

        data = self.buffer[offset + 4 : offset + 4 + length]
        written = []  # 记录写入的地址

        # Length 是字节数，每次写 2 字节（一个 word）
        for i in range(0, length, 2):
            if i + 2 <= len(data):
                word_addr = address + i
                self.state[word_addr] = data[i]
                self.state[word_addr + 1] = data[i + 1]
                written.append(word_addr)

        return (4 + length, written)  # consumed, written addresses

    def parse(self, data: bytes, debug=False):
        """
        解析一个 UDP 包，返回本次更新的字段列表
        返回: [(field_name, value_str), ...]
        """
        self.buffer.extend(data)
        updated_fields = []  # [(field_name, value_str)]
        updated_addrs = set()

        while True:
            # 搜索帧同步
            sync_pos = self._find_sync()
            if sync_pos < 0:
                if not self.synced:
                    # 还没同步，保留最后3字节（可能是部分同步字）
                    if len(self.buffer) > 3:
                        del self.buffer[:-3]
                    break
                else:
                    break

            # 找到帧同步
            self.synced = True
            # 丢弃帧同步之前的字节 + 同步字本身
            del self.buffer[:sync_pos + 4]

            # 帧同步后是一系列数据记录
            while len(self.buffer) >= 4:
                # 检查是否遇到下一个帧同步
                if self.buffer[:4] == self.FRAME_SYNC:
                    break

                result = self._extract_record(0)
                if result is None:
                    break

                consumed, written = result
                del self.buffer[:consumed]
                for addr in written:
                    updated_addrs.add(addr)

            # 如果缓冲区不完整，break 外层等待更多数据
            if len(self.buffer) < 4 or self.buffer[:4] != self.FRAME_SYNC:
                break

        # 批量提取字符串值（只提取可打印 ASCII，去重）
        # DCS-BIOS Skunkworks: 每个16-bit word含2个8-bit字符，连续字节存储
        _reported = set()
        for field_addr, (field_name, field_len) in self.address_to_field.items():
            field_touched = False
            # 检查 field_addr ~ field_addr+field_len-1 之间的字节是否有更新
            for i in range(field_len):
                # 判断该字节所在的 word 地址是否被更新过
                word_addr = field_addr + (i & ~1)  # i=0,1→word0, i=2,3→word2, ...
                if word_addr in updated_addrs:
                    field_touched = True
                    break

            if field_touched and field_name not in _reported:
                _reported.add(field_name)
                chars = []
                # DCS-BIOS Skunkworks 位打包: 每个16-bit word 含2个8-bit字符（低字节=char[0], 高字节=char[1]）
                # 内存是连续字节布局，直接 field_addr + i 读取
                for i in range(field_len):
                    ch = self.state[field_addr + i]  # 连续字节读取（非跳字节）
                    if 0x20 <= ch <= 0x7E:  # 仅可打印 ASCII
                        chars.append(chr(ch))
                    elif ch != 0:
                        chars.append(' ')  # 控制字符 → 空格
                val_str = ''.join(chars)
                updated_fields.append((field_name, val_str))

        return updated_fields


class DCSBIOSReceiver(threading.Thread):
    """
    DCS-BIOS UDP 数据接收线程

    工作流程：
      1. 监听 UDP 组播 239.255.50.10:5010
      2. 从 DCS-BIOS 生成的 Addresses.h / FA-18C_hornet.json 读取字段地址
      3. 将地址映射注入解析器；找不到外部文件时使用内嵌 fallback 地址
      4. 持续解析数据并回调
    """

    DCS_BIOS_IP   = "239.255.50.10"
    DCS_BIOS_PORT = 5010

    # 最近成功使用的外部地址文件路径，仅用于日志/状态判断；不再硬编码到特定 Windows 用户。
    ADDRESS_H_PATH = None
    JSON_PATH = None

    # F/A-18C UFC 感兴趣的字段（从 DCS-BIOS 源码提取的实际字段名）
    # 格式: { 'DCS-BIOS字段名': ('内部变量名', UI_pos) }
    UFC_FIELDS = {
        'UFC_SCRATCHPAD_NUMBER_DISPLAY': ('scratchpad_number', (0, "blank"), 8),
        'UFC_SCRATCHPAD_STRING_1_DISPLAY': ('scratchpad_str1',  (0, "blank"), 2),
        'UFC_SCRATCHPAD_STRING_2_DISPLAY': ('scratchpad_str2',  (0, "blank"), 2),
        'UFC_COMM1_DISPLAY':              ('comm1',             (4, 0),       2),
        'UFC_COMM2_DISPLAY':              ('comm2',             (4, 5),       2),
        'UFC_OPTION_DISPLAY_1':           ('option_1',          (0, 4),       4),
        'UFC_OPTION_DISPLAY_2':           ('option_2',          (1, 4),       4),
        'UFC_OPTION_DISPLAY_3':           ('option_3',          (2, 4),       4),
        'UFC_OPTION_DISPLAY_4':           ('option_4',          (3, 4),       4),
        'UFC_OPTION_DISPLAY_5':           ('option_5',          (4, 4),       4),
        'UFC_OPTION_CUEING_1':            ('cueing_1',          (0, 4),       1),
        'UFC_OPTION_CUEING_2':            ('cueing_2',          (1, 4),       1),
        'UFC_OPTION_CUEING_3':            ('cueing_3',          (2, 4),       1),
        'UFC_OPTION_CUEING_4':            ('cueing_4',          (3, 4),       1),
        'UFC_OPTION_CUEING_5':            ('cueing_5',          (4, 4),       1),
        'UFC_BRT':                        ('ufc_brightness',    None,         0),  # UFC 亮度旋钮 0.0~1.0
        'IFEI_BINGO':                     ('ifei_bingo',        None,         6),
    }

    # 需要拼接成组合字符串的位置 → 需要合并的内部字段名列表
    # (内部名 → BIOS字段名的反向映射在 __init__ 时构建)
    COMBINED_DISPLAYS = {
        (0, "blank"): ('scratchpad_str1', 'scratchpad_str2', 'scratchpad_number'),  # 长条
        (0, 4):       ('cueing_1', 'option_1'),  # 第0行右侧: cuing + 选项
        (1, 4):       ('cueing_2', 'option_2'),
        (2, 4):       ('cueing_3', 'option_3'),
        (3, 4):       ('cueing_4', 'option_4'),
        (4, 4):       ('cueing_5', 'option_5'),
    }

    # 每个位置的期望字符数（用于单字居中补齐）
    SLOT_WIDTHS = {
        (4, 0): 2,
        (4, 5): 2,
    }

    @staticmethod
    def pad_text(value, pos):
        """按位置期望宽度居中。单字用 HTML div 绕过 Hornet 字体空格问题"""
        w = DCSBIOSReceiver.SLOT_WIDTHS.get(pos, 0)
        if w <= 1:
            return value
        s = str(value).strip()
        if len(s) >= w:
            return s
        # 补齐空格后用 HTML div + text-align:center 强制居中
        padded = s.center(w)
        return f'<div style="text-align:center;">{padded}</div>'

    # 字段名 → UI 位置映射（供外部查询）
    DISPLAY_POS_MAP = {
        info[0]: info[1]
        for info in UFC_FIELDS.values()
        if info[1] is not None
    }

    # 内部名 → BIOS字段名 反向映射（用于从 latest 获取值）
    _INTERNAL_TO_BIOS = {}

    @classmethod
    def _build_maps(cls):
        """构建反向映射（首次用）"""
        if not cls._INTERNAL_TO_BIOS:
            for bios_name, (internal, _pos, _len) in cls.UFC_FIELDS.items():
                cls._INTERNAL_TO_BIOS[internal] = bios_name

    def __init__(self, callback=None):
        super().__init__(daemon=True)
        self.callback = callback
        self.parser   = DCSBIOSParser()
        self.sock     = None
        self.running  = False
        self.latest   = {}
        self._addr_map_built = False
        self._last_packet_time = 0.0   # 任何数据包到达都更新（不受值去重影响）

    def _build_address_map_from_metadata(self, raw_udp: bytes):
        """
        从 MetadataStart 帧的 JSON 中提取字段地址。

        DCS-BIOS 新版使用 TCP(42674) 提供完整 JSON，UDP 不含元数据，
        所以当前实现优先读取本地 Addresses.h / JSON，失败则使用 fallback。
        """
        pass  # 见 _learn_addresses

    @classmethod
    def _parse_addresses_h(cls, path: str):
        """从 Addresses.h 解析 FA_18C_hornet_ 开头的 string 字段地址"""
        import re
        addr_map = {}
        if not path or not os.path.exists(path):
            return addr_map
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                # 匹配: #define FA_18C_hornet_UFC_SCRATCHPAD_NUMBER_DISPLAY_A 0x7446
                m = re.match(
                    r'#define\s+FA_18C_hornet_(UFC_\w+)_A\s+(0x[0-9A-Fa-f]+)',
                    line.strip()
                )
                if m:
                    field_name = m.group(1)
                    addr_str   = m.group(2)
                    if field_name in cls.KNOWN_FIELDS:
                        length = cls.KNOWN_FIELDS[field_name]
                        addr_map[int(addr_str, 16)] = (field_name, length)
        return addr_map

    @classmethod
    def _parse_json_file(cls, path: str):
        """从 DCS-BIOS JSON 解析 UFC 字符串字段地址"""
        addr_map = {}
        if not path or not os.path.exists(path):
            return addr_map
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        for category_name, controls in data.items():
            if not isinstance(controls, dict):
                continue
            for control_id, control in controls.items():
                outputs = control.get('outputs', [])
                for output in outputs:
                    if output.get('type') == 'string':
                        addr = _decode_json_address(output.get('address'))
                        length = output.get('max_length', 2)
                        if addr is not None and control_id in cls.UFC_FIELDS:
                            addr_map[addr] = (control_id, length)
        return addr_map

    @staticmethod
    def _external_address_available():
        """任一候选 Addresses.h / JSON 存在即认为外部地址源可用。"""
        for address_h, json_path in _address_file_candidates():
            if os.path.exists(address_h) or os.path.exists(json_path):
                return True
        return False

    # 直接从 Lua 模块提取的字段名 → 长度（不需要地址）
    KNOWN_FIELDS = {
        'UFC_SCRATCHPAD_NUMBER_DISPLAY':  8,
        'UFC_SCRATCHPAD_STRING_1_DISPLAY': 2,
        'UFC_SCRATCHPAD_STRING_2_DISPLAY': 2,
        'UFC_COMM1_DISPLAY':               2,
        'UFC_COMM2_DISPLAY':               2,
        'UFC_OPTION_DISPLAY_1':            4,
        'UFC_OPTION_DISPLAY_2':            4,
        'UFC_OPTION_DISPLAY_3':            4,
        'UFC_OPTION_DISPLAY_4':            4,
        'UFC_OPTION_DISPLAY_5':            4,
        'UFC_OPTION_CUEING_1':             1,
        'UFC_OPTION_CUEING_2':             1,
        'UFC_OPTION_CUEING_3':             1,
        'UFC_OPTION_CUEING_4':             1,
        'UFC_OPTION_CUEING_5':             1,
    }

    def _learn_addresses(self):
        """
        从 DCS-BIOS 生成的文件读取字段地址映射。
        优先扫描 Addresses.h，其次扫描 JSON。
        """
        # 方法1: 读 Addresses.h（最可靠，dev_mode=true 时始终生成）
        for address_h, json_path in _address_file_candidates():
            addr_map = self._parse_addresses_h(address_h)
            if addr_map:
                self.parser.inject_address_map(addr_map)
                self.ADDRESS_H_PATH = address_h
                self.JSON_PATH = json_path
                print(f"[DCS-BIOS] Loaded {len(addr_map)} field addresses from Addresses.h: {address_h}")
                self._addr_map_built = True
                self._inject_analog_addresses()
                return True

        # 方法2: 读 JSON（可选）
        for address_h, json_path in _address_file_candidates():
            try:
                addr_map = self._parse_json_file(json_path)
                if addr_map:
                    self.parser.inject_address_map(addr_map)
                    self.ADDRESS_H_PATH = address_h
                    self.JSON_PATH = json_path
                    print(f"[DCS-BIOS] Loaded {len(addr_map)} field addresses from JSON: {json_path}")
                    self._addr_map_built = True
                    self._inject_analog_addresses()
                    return True
            except Exception as e:
                if json_path and os.path.exists(json_path):
                    print(f"[DCS-BIOS] Failed to read JSON {json_path}: {e}")

        # 方法3: 使用内嵌的真实地址（从 Addresses.h 硬编码备份）
        print("[DCS-BIOS] No external source found, using embedded addresses (synced from Addresses.h)")
        self._use_fallback_addresses()
        return False

    def _use_fallback_addresses(self):
        """
        嵌入式地址备份 — 与 Addresses.h 同步。
        当 DCS-BIOS 生成 Addresses.h 后，会被 _parse_addresses_h() 自动读取并覆盖。
        """
        # ⚠️ 这些地址必须与 DCS-BIOS 生成的 Addresses.h 保持一致！
        # 最后同步: 2025-06-10 (DCS-BIOS skunkworks, F/A-18C hornet)
        fallback = {
            0x7424: ('UFC_COMM1_DISPLAY',              2),
            0x7426: ('UFC_COMM2_DISPLAY',              2),
            0x7428: ('UFC_OPTION_CUEING_1',            1),
            0x742a: ('UFC_OPTION_CUEING_2',            1),
            0x742c: ('UFC_OPTION_CUEING_3',            1),
            0x742e: ('UFC_OPTION_CUEING_4',            1),
            0x7430: ('UFC_OPTION_CUEING_5',            1),
            0x7432: ('UFC_OPTION_DISPLAY_1',           4),
            0x7436: ('UFC_OPTION_DISPLAY_2',           4),
            0x743a: ('UFC_OPTION_DISPLAY_3',           4),
            0x743e: ('UFC_OPTION_DISPLAY_4',           4),
            0x7442: ('UFC_OPTION_DISPLAY_5',           4),
            0x7446: ('UFC_SCRATCHPAD_NUMBER_DISPLAY',  8),
            0x744e: ('UFC_SCRATCHPAD_STRING_1_DISPLAY',2),
            0x7450: ('UFC_SCRATCHPAD_STRING_2_DISPLAY',2),
            0x7468: ('IFEI_BINGO',                     6),
        }

        addr_map = {}
        for addr, (field_name, length) in fallback.items():
            if field_name in self.UFC_FIELDS:
                addr_map[addr] = (field_name, length)

        self.parser.inject_address_map(addr_map)
        print(f"[DCS-BIOS] Using fallback address map ({len(addr_map)} fields)")
        self._addr_map_built = True
        self._inject_analog_addresses()

    def _inject_analog_addresses(self):
        """注入模拟量+灯光整数字段地址"""
        self.parser.analog_addresses[0x741E] = 'ufc_brightness'
        self.parser.analog_addresses[0x74E8] = 'sai_att_warning'
        self.parser.analog_addresses[0x7518] = 'radalt_min_ptr'
        self.parser.analog_addresses[0x751C] = 'radalt_off_flag'
        # 外部灯光输出地址 (来源: Addresses.h)
        self.parser.integer_addrs[0x7526] = ('formation_dimmer', 0xFFFF, 0)   # 编队灯 0-65535
        self.parser.integer_addrs[0x7524] = ('position_dimmer',  0xFFFF, 0)   # 航线灯 0-65535
        self.parser.integer_addrs[0x7480] = ('ldg_taxi_sw',      0x8000, 15)  # 着陆/滑行灯 bit15
        self.parser.integer_addrs[0x74B0] = ('strobe_sw',        0x3000, 12)  # 频闪灯 bits12-13
        print(f"[DCS-BIOS] Injected 8 address-mapped fields (UFC_BRT, SAI, RADALT + 4 lights)")

    def run(self):
        """线程主循环"""
        self.running = True

        # 先尝试从 DCS-BIOS 生成文件获取地址映射；失败则使用 fallback。
        self._learn_addresses()

        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.bind(("", self.DCS_BIOS_PORT))

            mreq = struct.pack("4sL", socket.inet_aton(self.DCS_BIOS_IP), socket.INADDR_ANY)
            self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
            self.sock.settimeout(0.5)

            print(f"[DCS-BIOS] Listening on {self.DCS_BIOS_IP}:{self.DCS_BIOS_PORT}")

            _last_retry = time.time()
            _last_value = {}  # 记录每个字段上次的值，只在变化时打印
            _addr_file_loaded = self._external_address_available()

            while self.running:
                try:
                    data, _ = self.sock.recvfrom(65535)
                    self._last_packet_time = time.time()  # 包级心跳，不受值去重影响

                    # 如果还在用 fallback 地址，定期重试读外部文件（DCS 可能已经生成了）
                    if not _addr_file_loaded and time.time() - _last_retry > 10.0:
                        _last_retry = time.time()
                        if self._external_address_available():
                            print("[DCS-BIOS] External address file now available, reloading...")
                            self._learn_addresses()
                            _addr_file_loaded = True

                    updated = self.parser.parse(data)

                    for field_name, value in updated:
                        self.latest[field_name] = value
                        # 只在值变化时回调（避免刷屏）
                        prev = _last_value.get(field_name)
                        if value != prev:
                            _last_value[field_name] = value
                            if self.callback and field_name in self.UFC_FIELDS:
                                internal_name = self.UFC_FIELDS[field_name][0]
                                self.callback(internal_name, value)

                    # ==== 模拟量字段（如 UFC_BRT）====
                    for addr, internal_name in self.parser.analog_addresses.items():
                        # 读 2 字节 uint16 little-endian
                        lo = self.parser.state[addr]
                        hi = self.parser.state[addr + 1]
                        raw = lo | (hi << 8)
                        val = raw / 65535.0  # 0.0 ~ 1.0
                        val = round(val, 3)
                        self.latest[internal_name] = str(val)  # 存入 latest 供查询
                        prev_a = _last_value.get(internal_name)
                        if val != prev_a:
                            _last_value[internal_name] = val
                            if self.callback:
                                self.callback(internal_name, str(val))

                    # ==== 整数字段（灯光控制等，含 bit mask）====
                    for addr, (internal_name, mask, shift) in self.parser.integer_addrs.items():
                        lo = self.parser.state[addr]
                        hi = self.parser.state[addr + 1]
                        raw = lo | (hi << 8)
                        val = (raw & mask) >> shift
                        prev_i = _last_value.get(internal_name)
                        if val != prev_i:
                            _last_value[internal_name] = val
                            if self.callback:
                                self.callback(internal_name, str(val))

                except socket.timeout:
                    continue
                except Exception as e:
                    if self.running:
                        print(f"[DCS-BIOS] Receive error: {e}")

        except Exception as e:
            print(f"[DCS-BIOS] Failed to start: {e}")
        finally:
            self.stop()

    def stop(self):
        """停止接收"""
        self.running = False
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None
        print("[DCS-BIOS] Stopped")
