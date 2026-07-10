# UFC Keypad (模块化版)

F/A-18C Hornet **Up Front Controller** 触控面板，通过 **DCS-BIOS** 与 DCS World 通信。
基于 PyQt6，从原单体 `ufc_keypad.py` 拆分为清晰的模块包 `ufc/`。

## 功能
- **LOCAL ICP**：完整 UFC 布局，点击/触控输出键位，实时显示座舱数据
- **MORSE LIGHT**：字母+小键盘，输入文本经编队灯输出莫尔斯码
- **LIGHT CONTROL**：着陆/滑行灯、编队灯、航线灯、频闪灯手动控制 + 预设
- **SYSTEM SELECT**：页面切换中枢
- **可选启动动画**：打开面板后显示启动覆盖层，等待第一条 DCS-BIOS 信号；收到信号后显示 ONLINE / READY 并自动切入 LOCAL ICP
  - `UFC BIT（军机自检风格）`：黑底绿字、BIT 自检、BUS SCAN
  - `千禧日式动画风格`：架空千禧日本动画风格终端、蓝黑 HUD、日文状态字
- DCS-BIOS 双向同步：接收 `239.255.50.10:5010/UDP`，发送 `127.0.0.1:7778/UDP`
- Windows 原生触控隔离（WH_MOUSE_LL 钩子 + RegisterTouchWindow）

## DCS-BIOS 通信端口

当前端口说明以源码 `ufc/dcs_bios.py` 为准：

| 方向 | 地址 / 端口 | 用途 |
|------|-------------|------|
| DCS → UFC Keypad | `239.255.50.10:5010/UDP` | 接收 DCS-BIOS Skunkworks 组播导出的座舱状态数据 |
| UFC Keypad → DCS | `127.0.0.1:7778/UDP` | 发送 DCS-BIOS 控制命令 |

## 运行
```bash
pip install -r requirements.txt
python main.py
```

## DCS Export bridge 诊断

弹射座椅保险、ECM REC 和 CV 弹射配平依赖额外的 Export.lua bridge。安装或更新 bridge：

```bash
python install_dcs_export_bridge.py
```

完全重启 DCS、进入 F/A-18C 座舱并退出主 UFC 程序后，运行诊断：

```bash
python probe_hornet_bridge.py
```

诊断程序默认扫描 draw argument `0..800`，逐项测试弹射座椅、ECM 和俯仰配平，并在当前目录生成可直接反馈的文件：

```text
probe_report_YYYYMMDD_HHMMSS.md
probe_report_YYYYMMDD_HHMMSS.json
```

无人值守运行可增加 `--yes`；扫描其他范围可使用 `--scan-from` / `--scan-to`。一次最多扫描 1001 个参数，范围限制为 `0..2000`。

DCS 端日志位于 `Saved Games\DCS*\Logs\UFC_Keypad_CVTrim.log`。若报告显示没有 telemetry，先检查该日志是否存在，并确认没有其他程序占用 UDP 5518。

## 当前冷启动清单

- LAND：26 步。
- CV：27 步，其中第 25 步为自动 CAT TRIM。
- 第 14 步 `CANOPY / OXYGEN`：关闭座舱盖并打开 OBOGS。
- APU START/OFF 使用本机已验证的保持式硬件输入命令 3023，避免普通命令 3001 推上后失效。
- 第 17 步 `FCS / RWR`：执行 FCS RESET，并将 ALR-67 POWER 保持在 ON。
- 第 12 步 `APU OFF / FLAPS HALF`：关闭 APU，并将襟翼开关置于 HALF。
- 第 19 步 `SAI UNLOCK`：程序使用专用 CCW 输入旋转解锁备用姿态仪，不调整小飞机标线，等待用户确认。
- 第 20 步 `RADALT MIN`：通过屏幕触控 −/+ 以 20 ft 为一档选择目标；按 START 后程序给雷达高度仪通电并闭环设置，完成后再次等待确认。
- 第 21 步 `BINGO FUEL`：通过屏幕触控 −/+ 以 100 lb 为一档选择目标；按 START 后闭环设置，完成后再次等待确认。
- 第 23 步 `RADAR / INS`：雷达转 OPR、INS 转 LAND/CV 对应位置，随后停下等待人工确认。
- 第 24 步 `AMPCD PB19`：仅通过 DCS-BIOS 按下并释放一次 PB19，随后等待人工确认；不再同时发送 Export bridge，避免双击。
- LAND 第 25 步、CV 第 26 步 `HMD CAL / IFA`：按 DAY/NIGHT 设置 HMD 亮度并将 INS 转 IFA；等待 10 秒后执行 RDDI OSB 序列，最后等待用户手动校准确认。
- HMD 打开后严格按 `RDDI OSB18 → OSB18 → OSB3 → OSB20` 执行，每次按键完成后等待 3 秒。

## 启动动画设置

在设置面板中可选择启动动画风格。切换后会立即替换当前启动覆盖层，并保存到 `ufc_config.json` 作为下次启动默认值：

```json
{
  "startup_style": "ufc_bit"
}
```

可选值：

| 值 | 显示名称 |
|----|----------|
| `ufc_bit` | UFC BIT（军机自检风格） |
| `anime_millennium_jp` | 千禧日式动画风格 |

## 打包 (PyInstaller, 单文件无控制台)
```bash
pyinstaller UFC_Keypad_v5.spec
# 或直接：
pyinstaller --onefile --windowed --name UFC_Keypad_v5 ^
  --add-data "FA-18C_Hornet_Up_Front_Controller.ttf;." ^
  --add-data "ufc_config.json;." main.py
```
> 注意：打包后 `ufc/` 包会被 PyInstaller 自动收集；字体与配置文件需通过
> `--add-data` 一并打包（或用 `sys._MEIPASS` 查找，代码已兼容）。

## 模块结构 (`ufc/`)
| 模块 | 职责 |
|------|------|
| `constants.py` | 屏幕尺寸、背景色、DCS-BIOS 标识符、布局辅助函数 |
| `crashlog.py`  | 未捕获异常 → `ufc_crash.log` |
| `config.py`    | `ufc_config.json` 读写 |
| `fonts.py`     | Hornet UFC 字体加载 (B612 回退) |
| `morse.py`     | 文本 → 莫尔斯点划序列 |
| `colors.py`    | 亮度 → 颜色计算 (绿色 LED 风格)，持有 `_CURRENT_BRIGHTNESS` 真值 |
| `dcs_bios.py`  | DCS-BIOS UDP 解析器、接收线程、指令发送 |
| `input.py`     | 原生触控钩子 + 键位注入 (SendInput/PostMessage) |
| `widgets.py`   | `UFCCell` / `UFCBlank` 自定义控件 |
| `startup.py`   | 可选启动动画覆盖层与设置面板附加项 |
| `ui.py`        | `UFCKeypadWindow` 主面板 + `SettingsWindow` 设置窗口 |
| `main.py`      | 仓库根目录入口，创建 QApplication 与主窗口 |

## 依赖
- Python 3.10+
- PyQt6
- Windows (原生触控钩子仅 Windows 有效)

## Steps 19–21 touch setup

The former MANUAL SETUP step is split into three user-confirmed steps. SAI uses
the local input-only `SAI_Rotate_EXT` command through the Export bridge's
`SetCommand` path. RADALT and BINGO use large on-screen touch controls instead
of keyboard input. RADALT changes by 20 ft per tap; BINGO changes by 100 lb per
tap. Press START once to apply the displayed value and again after cockpit
verification to continue.

Suggested initial values remain configurable in `ufc_config.json` under
`manual_setup_targets`: LAND defaults to 200 ft / 3000 lb and CV defaults to
200 ft / 4000 lb. RADALT argument 287 is converted through the local cockpit
gauge curves. Missing feedback or pulse-limit failure enters manual takeover.
