# UFC_Keypad 当前未解决问题交接文档

> 目的：把当前 F/A-18C 冷启动管理器的故障、现有代码结构、已尝试方案、验证方法和后续修复方向一次性交给 Codex 处理。  
> 仓库：`Dingdongji113/UFC_Keypad`  
> 项目类型：PyQt6 触摸 UFC 面板 + DCS-BIOS + 可选 DCS Export.lua bridge。  
> 当前重点：冷启动流程中部分座舱控制和 CV 自动配平仍然无效。

---

## 1. 当前未解决故障

### 1.1 弹射座椅保险解除无效

冷启动第 1 步现在是：

```text
EJECT SAFE OFF
```

预期：

```text
弹射座椅 SAFE/ARMED handle 应从 SAFE 变为 ARMED / 解除保险状态。
```

实际：

```text
程序执行后座舱内弹射保险没有变化。
```

当前已尝试：

```text
DCS-BIOS:
  EJECTION_SEAT_ARMED 1

Export.lua direct clickable fallback:
  GetDevice(7):performClickableAction(3006, 1.0)
```

DCS-BIOS 源码确认项：

```lua
FA_18C_hornet:defineToggleSwitch(
  "EJECTION_SEAT_ARMED",
  7,
  3006,
  511,
  "Ejection Seat",
  "Ejection Seat SAFE/ARMED Handle, SAFE/ARMED"
)
```

也就是说公开 DCS-BIOS 模块里确实存在：

```text
ID: EJECTION_SEAT_ARMED
Device: 7
Command: 3006
Draw argument: 511
```

问题不是页面步骤缺失，而是当前发送方式在用户实机 DCS 环境中没有驱动座舱。

---

### 1.2 ECM 转 REC 无效

冷启动步骤：

```text
ECM REC
```

预期：

```text
ECM_MODE_SW 转到 REC。
```

实际：

```text
程序执行后 ECM 旋钮没有转到 REC。
```

当前已尝试：

```text
DCS-BIOS:
  ECM_MODE_SW 1

Export.lua direct clickable fallback:
  GetDevice(66):performClickableAction(3001, 0.1)
```

DCS-BIOS 源码确认项：

```lua
FA_18C_hornet:defineTumb(
  "ECM_MODE_SW",
  66,
  3001,
  248,
  0.1,
  { 0, 0.4 },
  nil,
  false,
  "Dispenser/EMC Panel",
  "ECM Mode Switch",
  { positions = { "XMIT", "REC", "BIT", "STBY", "OFF" } }
)
```

公开映射推导：

```text
0.0 = XMIT
0.1 = REC
0.2 = BIT
0.3 = STBY
0.4 = OFF
```

但用户实机反馈：仍无效。

---

### 1.3 CV 模式自动弹射配平无效

CV 模式最后新增步骤：

```text
CAT TRIM
```

预期：程序自动读取当前重量和当前升降舵/平尾配平角，根据表自动调到目标：

```text
<= 44000 lb      -> 16 deg nose up
45000–48000 lb   -> 17 deg nose up
>= 49000 lb      -> 19 deg nose up
```

当前实现目标函数：

```python
def cv_trim_target_deg(weight_lbs: float) -> float:
    if weight_lbs <= 44000:
        return 16.0
    if weight_lbs < 49000:
        return 17.0
    return 19.0
```

实际：

```text
CV 自动配平无效。
```

当前结构：

```text
DCS Export.lua -> UDP 5518 -> Python telemetry receiver
Python -> UDP 5519 -> DCS Export.lua command handler
```

当前 Lua 尝试读取：

```text
gross_weight_lbs / Weight / GrossWeight / Mass
stab_trim_deg / stabilator_trim_deg / elevator_trim_deg / pitch_trim_deg
candidate draw args: 15,16,17,18,345,346,500,501,502,503
```

当前 Python 若读不到 fresh telemetry，会停在：

```text
CAT TRIM DATA?
```

如果能读到但 trim pulse 不改变任何候选参数，则自动配平仍无法闭环。

---

## 2. 当前相关文件

### Python 主入口

```text
main.py
main_safe.py
```

目前入口安装顺序大致为：

```python
install_ifei_rpm_fallback()
install_realtime_rpm_callbacks()
patch_settings_window_apply_screen(SettingsWindow)
patch_cold_start(UFCKeypadWindow)
install_cold_direct_entry(UFCKeypadWindow)
install_split_land_cv_setup(UFCKeypadWindow)
install_cold_ui_fixups(UFCKeypadWindow)
install_cv_trim_automation(UFCKeypadWindow)
install_direct_command_fixups(UFCKeypadWindow)
```

### 冷启动核心和 UI patch

```text
ufc/cold_start.py
ufc/cold_direct_entry.py
ufc/cold_setup_split.py
ufc/cold_ui_fixups.py
```

### 当前故障相关新增模块

```text
ufc/cv_trim_auto.py
ufc/direct_command_fixups.py
```

### DCS Export bridge

```text
dcs_export/UFC_Keypad_CVTrim.lua
```

需要手动复制到：

```text
C:\Users\Administrator\Saved Games\DCS.openbeta\Scripts\UFC_Keypad_CVTrim.lua
```

并在：

```text
C:\Users\Administrator\Saved Games\DCS.openbeta\Scripts\Export.lua
```

末尾添加：

```lua
dofile(lfs.writedir() .. [[Scripts\UFC_Keypad_CVTrim.lua]])
```

### Probe / 诊断脚本

```text
probe_hornet_bridge.py
install_dcs_export_bridge.py
_verify.py
```

其中 `probe_hornet_bridge.py` 是当前最重要的下一步诊断入口。

---

## 3. 当前冷启动流程概览

### LAND 模式

当前 LAND 约 22 步：

```text
01 EJECT SAFE OFF
02 BATTERY ON
03 APU START
04 APU WAIT
05 APU READY?
06 RIGHT CRANK
07 RIGHT IDLE
08 RIGHT STABLE?
09 LEFT CRANK
10 LEFT IDLE
11 LEFT STABLE?
12 APU OFF
13 BRIGHTNESS
14 CANOPY CLOSE
15 BLEED AIR
16 TRIM RESET
17 FCS / RWR
18 ECM REC
19 MANUAL SETUP
20 LOCAL ICP
21 INS
22 COMPLETE
```

### CV 模式

CV 比 LAND 多一个 `CAT TRIM`：

```text
...
21 INS
22 CAT TRIM
23 COMPLETE
```

`CAT TRIM` 当前已从用户手动确认改为自动步骤，kind 为：

```text
cat_trim_auto
```

---

## 4. 已经修过且不应回退的功能

以下功能之前已修过，除非确认新实现更稳定，否则不要回退：

### 4.1 冷启动自动进入逻辑

需求：

```text
软件启动后显示 US NAVY / WAITING FOR DCS-BIOS。
收到任意 DCS-BIOS 信号后隐藏等待层。
随后根据左右发动机 RPM 判断。
任意一发 >= 60% -> 非冷启动，播放 UFC 动画并进入 LOCAL ICP。
双发都已知且都 < 60% -> 直接进入 COLD START SETUP / COLD START 页面。
```

当前依赖字段：

```text
IFEI_RPM_L
IFEI_RPM_R
left_engine_rpm
right_engine_rpm
```

### 4.2 IFEI RPM fallback

硬编码地址：

```python
IFEI_RPM_L: 0x749E, len=3
IFEI_RPM_R: 0x74A2, len=3
```

解析要支持：

```text
"120F"
"420 "
"  0"
```

不能直接 `float(raw)`，需要正则提取数字。

### 4.3 DAY/NIGHT + LAND/CV setup

进入冷启动页面后先选：

```text
DAY / NIGHT
LAND / CV
```

需要两次 `START` 确认后进入 checklist。

### 4.4 RESET 行为

冷启动 checklist 页面右下角 `RESET`：

```text
连续点击两次 -> 回到 DAY/NIGHT + LAND/CV setup 页面
步数不清零
重新 START x2 后回到原 checklist step
```

### 4.5 COMPLETE 行为

所有步骤执行完后：

```text
START 按钮文字应变为 COMPLETE
点击 COMPLETE -> 跳转 LOCAL ICP
不能继续 START 导致步数溢出
```

---

## 5. 目前关键诊断点

当前不要继续靠猜测 `0/1/0.1/1.0` 修。应该先跑 probe，拿真实 telemetry。

### 5.1 必须先确认 DCS bridge 真实加载

DCS 侧日志应该生成：

```text
C:\Users\Administrator\Saved Games\DCS.openbeta\Logs\UFC_Keypad_CVTrim.log
```

如果没有这个日志，说明 Export.lua bridge 没加载。

### 5.2 运行 probe

条件：

```text
1. DCS 已完全重启
2. 已进入 F/A-18C 座舱
3. 主 UFC 程序不要运行，避免抢 UDP 5518
4. 在仓库根目录运行
```

命令：

```bat
python probe_hornet_bridge.py
```

probe 会测试：

```text
ping
EJECTION_SEAT_ARMED device=7 command=3006 values=[1.0,0.0,1.0,-1.0,1.0]
ECM_MODE_SW device=66 command=3001 values=[0.0,0.1,0.2,0.3,0.4,-0.1,0.1]
trim up/down pulse
```

它会打印 before/after：

```text
seat_armed_arg_511
ecm_mode_arg_248
rwr_power_light_arg_276
rwr_enable_light_arg_267
gross_weight_lbs
stab_trim_deg
trim_arg_15/16/17/18/345/346/500/501/502/503
last_command
```

### 5.3 判断方法

如果 probe 初始显示：

```text
NO TELEMETRY RECEIVED
```

可能原因：

```text
DCS 没加载 Lua
Export.lua 没执行到 dofile
主 UFC 程序或其他程序已经占用 UDP 5518
防火墙/本机 UDP 异常
```

如果 telemetry 有，但 `last_command` 不更新：

```text
Python -> UDP 5519 -> Lua 命令通道没通
```

如果 `last_command` 更新为 clickable，但 draw argument 不变：

```text
device / command / value 不匹配
或 performClickableAction 在 Export 环境下对该 cockpit device 无效
```

如果 ECM 的 `ecm_mode_arg_248` 在某个 value 下变化：

```text
把 direct_command_fixups.py 里的 ECM value 改成对应值
```

如果 `seat_armed_arg_511` 在某个 value 下变化：

```text
把 direct_command_fixups.py 里的 ejection value 改成对应值
```

如果 trim pulse 后所有 `trim_arg_*` 和 `stab_trim_deg` 都不变：

```text
当前 trim command 常量无效，或候选 draw argument 不对。
需要在 Lua 中扩展 command 常量 / draw argument probe。
```

---

## 6. 可能的根因方向

### 6.1 `GetDevice(...):performClickableAction(...)` 的 value 语义可能和 DCS-BIOS define 不同

DCS-BIOS 的 `defineToggleSwitch` / `defineTumb` 对外暴露的是 DCS-BIOS 控制语义，未必等于直接 clickable 的 absolute value。

例如：

```text
DCS-BIOS set_state 1
不一定等于
performClickableAction(command, 1.0)
```

`defineTumb(... fixed_step=0.1, range={0,0.4})` 推导出 `0.1 = REC`，但实机仍无效，说明不能继续盲信推导。

### 6.2 用户本机 DCS 版本可能与公开 DCS-BIOS 映射不一致

建议 Codex 让用户上传或读取本机文件：

```text
DCS World\Mods\aircraft\FA-18C\Cockpit\Scripts\clickabledata.lua
DCS World\Mods\aircraft\FA-18C\Cockpit\Scripts\devices.lua
DCS World\Mods\aircraft\FA-18C\Input\FA-18C\keyboard\default.lua
```

从本机 `clickabledata.lua` 中解析：

```text
弹射座椅 SAFE/ARMED
ECM Mode Switch
Pitch trim command
Stabilator trim draw argument / indicator
```

### 6.3 CV 配平重量/配平角可能不能从 LoGetSelfData / LoGetMechInfo 直接取

如果 `gross_weight_lbs` 是 nil：

```text
需要尝试其它 Export API 或从 fuel + empty weight + stores 估算。
```

如果 `stab_trim_deg` 是 nil 或不随 trim 变化：

```text
需要定位真实的 FCS/STAB trim 参数来源。
```

可能需要：

```text
LoGetMechInfo()
LoGetAircraftDrawArgumentValue(arg)
list_cockpit_params()
get_cockpit_param_handle(name):get()
parse_indication(...)
```

但这些函数在不同 DCS 环境中可用性不同，需要日志化探测。

---

## 7. 建议 Codex 下一步任务

### 任务 A：增强 `probe_hornet_bridge.py`

目标：生成可直接贴回的完整 Markdown/JSON 诊断报告。

建议输出：

```text
probe_report_YYYYMMDD_HHMMSS.md
probe_report_YYYYMMDD_HHMMSS.json
```

报告内容：

```text
是否收到 telemetry
DCS bridge last_command 是否更新
每次 clickable 前后所有关键 arg 差异
trim up/down 后哪些 arg 变化
gross_weight_lbs / stab_trim_deg 是否有效
```

### 任务 B：增强 Lua bridge 的 introspection

当前 Lua 只回传固定 draw args。建议扩展：

```lua
-- 伪代码
for arg = 0, 600 do
  local v = LoGetAircraftDrawArgumentValue(arg)
  if v and abs(v) > threshold then log/telemetry
end
```

或者支持 probe 命令：

```json
{"type":"scan_args","from":0,"to":800}
```

再由 Python 比较命令前后的变化。

### 任务 C：增加本机 FA-18C cockpit 脚本解析器

让用户提供本机 DCS 路径后，自动解析：

```text
clickabledata.lua
devices.lua
command_defs.lua / default.lua
```

目标：不要再依赖公开 DCS-BIOS 仓库猜测。

### 任务 D：把故障项改成闭环执行

弹射保险和 ECM 不应再是“发了就算成功”，而应：

```text
读取当前 arg
发送候选命令
等待 0.3-0.8s
再次读取 arg
确认 arg 到目标值
失败则尝试下一个 method
全部失败则进入 HOLD，显示具体失败原因
```

例如：

```python
methods = [
  DCSBIOS("ECM_MODE_SW", 1),
  CLICKABLE(66, 3001, 0.1),
  CLICKABLE(66, 3001, 0.0),
  CLICKABLE(66, 3001, 0.2),
  CLICKABLE(66, 3001, -0.1),
]
```

但最终 methods 应由 probe 确认，不应硬编码猜值。

### 任务 E：CV 自动配平应分三段验证

```text
1. 读取重量成功？
2. 读取当前 trim 成功？
3. trim pulse 能让 current trim 改变？
```

只有三项均成功才执行自动 trim。否则停在：

```text
CAT TRIM DATA?
```

并显示缺哪一项：

```text
NO WEIGHT
NO TRIM SENSOR
TRIM COMMAND NO EFFECT
```

---

## 8. 验收标准

### 8.1 弹射座椅保险

```text
冷启动第 1 步执行后，座舱内 SAFE/ARMED handle 真实变化。
Probe 中 seat_armed_arg_511 必须发生对应变化。
```

### 8.2 ECM REC

```text
ECM REC 步骤执行后，ECM 旋钮真实转到 REC。
Probe 中 ecm_mode_arg_248 必须进入 REC 对应值。
```

### 8.3 CV CAT TRIM

```text
CV 模式下 CAT TRIM 步骤能读取重量。
能读取当前 trim 角。
trim pulse 后当前 trim 角发生变化。
最终 trim 到目标值 ±0.25° 后自动进入 COMPLETE。
```

### 8.4 不能破坏已有逻辑

```text
冷舱双发 0 RPM -> 自动进入冷启动 setup。
热舱任意一发 >=60 -> 播放 UFC 动画进入 LOCAL ICP。
DAY/NIGHT + LAND/CV 双确认仍然有效。
RESET 双击回 setup 且保留步骤。
COMPLETE 点击跳 LOCAL ICP。
_verify.py 必须通过。
```

---

## 9. 运行命令

常规验证：

```bat
python _verify.py
python main.py
```

DCS bridge 诊断：

```bat
python probe_hornet_bridge.py
```

手动安装 bridge：

```text
复制：
  dcs_export\UFC_Keypad_CVTrim.lua
到：
  C:\Users\Administrator\Saved Games\DCS.openbeta\Scripts\UFC_Keypad_CVTrim.lua

Export.lua 添加：
  dofile(lfs.writedir() .. [[Scripts\UFC_Keypad_CVTrim.lua]])
```

DCS 侧日志：

```text
C:\Users\Administrator\Saved Games\DCS.openbeta\Logs\UFC_Keypad_CVTrim.log
```

Python 侧日志：

```text
UFC_Keypad 项目目录\cv_trim_debug.log
```

---

## 10. 当前建议优先级

```text
P0: 跑 probe_hornet_bridge.py，拿真实 before/after 数据。
P1: 根据 probe 数据修 direct_command_fixups.py 的 ejection / ECM method。
P2: 根据 trim probe 数据修 cv_trim_auto.py 的 trim sensor / trim command。
P3: 把弹射保险、ECM、CAT TRIM 全部改为闭环确认，不再“发了就算”。
P4: 如果 probe 仍无法观察真实变化，改为解析用户本机 clickabledata.lua / devices.lua。
```

---

## 11. 最近相关提交摘要

```text
ad488af7c5190f17f4c456f21343de6323cc6825
  debug: report Hornet bridge probe arguments

13c5a91991e281a198ed85d6bc8bf28b692f2fc3
  debug: add Hornet bridge probe script

117c3259a3eb4b28863312bf57ba0f45109ed6d9
  fix: add direct bridge fallback for failed cockpit controls

efed650fef39eaf285b76af31af5b7cf9640e7af
  fix: add direct cockpit command bridge and CV trim diagnostics

f27402c67730f9e916b5fdd1c7c60e3dff7d02b9
  fix: support direct cockpit commands in export bridge

6935ed2c901cedae3b3ca2c71a6ac44bc7be8d2b
  feat: add CV catapult trim telemetry automation
```
