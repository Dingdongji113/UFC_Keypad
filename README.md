# UFC Keypad (模块化版)

F/A-18C Hornet **Up Front Controller** 触控面板，通过 **DCS-BIOS** 与 DCS World 通信。
基于 PyQt6，从原单体 `ufc_keypad.py` 拆分为清晰的模块包 `ufc/`。

## 功能
- **LOCAL ICP**：完整 UFC 布局，点击/触控输出键位，实时显示座舱数据
- **MORSE LIGHT**：字母+小键盘，输入文本经编队灯输出莫尔斯码
- **LIGHT CONTROL**：着陆/滑行灯、编队灯、航线灯、频闪灯手动控制 + 预设
- **SYSTEM SELECT**：页面切换中枢
- DCS-BIOS 双向同步（UDP 导入 7778 / 接收 37778），亮度随座舱旋钮联动
- Windows 原生触控隔离（WH_MOUSE_LL 钩子 + RegisterTouchWindow）

## 运行
```bash
pip install -r requirements.txt
python main.py
```

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
| `ui.py`        | `UFCKeypadWindow` 主面板 + `SettingsWindow` 设置窗口 |
| `app.py`       | (见仓库根 `main.py`) 入口 |

## 依赖
- Python 3.10+
- PyQt6
- Windows (原生触控钩子仅 Windows 有效)
