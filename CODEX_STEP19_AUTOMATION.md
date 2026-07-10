# Codex 任务：将冷启动第 19 步改为自动执行（已废弃）

> 本文仅保留历史设计。当前实现已删除 `manual_setup_targets` 与
> RADALT/BINGO 目标闭环；直接触控流程以 README.md 和 CODEX_PROGRESS.md
> 为准。

> 仓库：`Dingdongji113/UFC_Keypad`  
> 任务范围：只修改第 19 步 `MANUAL SETUP` 的执行逻辑；不要回退或破坏现有冷启动、CV 自动配平、RADAR/INS 分步确认、HMD/IFA 时序和 OSB 单通道逻辑。  
> 当前要求已经确认：备用姿态仪只需要自动**解锁**，不需要自动水平校准。

---

## 0. 开工前必须从 Git 仓库拉取最新版本

不要使用旧压缩包、旧工作目录或聊天中早期代码片段作为修改基础。

### 已有本地仓库

```bash
git status
git fetch origin
git checkout main
git pull --ff-only origin main
git rev-parse HEAD
```

### 没有本地仓库

```bash
git clone https://github.com/Dingdongji113/UFC_Keypad.git
cd UFC_Keypad
git checkout main
git pull --ff-only origin main
git rev-parse HEAD
```

开工前必须确认：

```text
1. 工作区没有未说明的本地改动。
2. 当前 HEAD 为远程 main 最新提交。
3. 仓库中已经存在以下最新模块：
   - ufc/hmd_osb_timing.py
   - ufc/radar_ins_steps.py
   - ufc/cv_trim_auto.py
   - ufc/direct_command_fixups.py
4. 当前 RDDI OSB 逻辑是 DCS-BIOS 主通道、Export bridge 备用通道，不能同时发送。
5. 当前 RADAR / INS 与 AMPCD PB19 已拆成两个独立人工确认步骤。
```

如仓库结构或步骤数量与本文描述不一致，以最新仓库源码为准，先阅读后再改。

---

## 1. 当前第 19 步

当前权威清单位于：

```text
ufc/cold_ui_fixups.py
```

第 19 步当前定义为人工步骤：

```python
(
    "MANUAL SETUP",
    "user",
    "",
    "Set standby attitude, radar altitude minimum, and bingo fuel; then START.",
)
```

当前要求是将其改为程序自动执行，包含三项：

```text
1. 备用姿态仪：只自动解锁。
2. RADALT MIN：自动设置到配置目标值。
3. BINGO FUEL：自动设置到配置目标值。
```

不要求自动校准备用姿态仪水平基准。

---

## 2. 目标行为

第 19 步仍然可以在 UI 上保留名称：

```text
MANUAL SETUP
```

但执行类型改为专用自动状态机，例如：

```python
(
    "MANUAL SETUP",
    "manual_setup_auto",
    "",
    "Unlock standby attitude indicator, set RADALT minimum, and set BINGO fuel.",
)
```

建议的内部流程：

```text
STANDBY ATTITUDE UNLOCK
↓
确认解锁成功
↓
RADALT MIN AUTO SET
↓
确认达到目标值
↓
BINGO FUEL AUTO SET
↓
确认达到目标值
↓
自动进入下一步
```

执行过程中 UI 应显示当前子阶段，例如：

```text
MANUAL SETUP: STANDBY UNLOCK
MANUAL SETUP: RADALT 120 → 200 FT
MANUAL SETUP: BINGO 2400 → 3000 LB
```

三项全部成功后，自动推进到下一步，不需要额外按 `START`。

任意一项失败时，不允许无条件跳过；应进入人工接管状态。

---

## 3. 推荐模块结构

建议新增独立模块：

```text
ufc/manual_setup_auto.py
```

不要把大量新状态机继续堆入：

```text
ufc/cold_ui_fixups.py
ufc/cv_trim_auto.py
```

建议导出：

```python
install_manual_setup_automation(UFCKeypadWindowClass)
```

安装顺序应位于现有冷启动 patch 之后，并确保不会覆盖较新的 `radar_ins_steps` 和 `hmd_osb_timing` 行为。

建议入口安装顺序最终类似：

```python
patch_cold_start(UFCKeypadWindow)
install_cold_direct_entry(UFCKeypadWindow)
install_split_land_cv_setup(UFCKeypadWindow)
install_cold_ui_fixups(UFCKeypadWindow)
install_cv_trim_automation(UFCKeypadWindow)
install_direct_command_fixups(UFCKeypadWindow)
install_hmd_osb_timing_fix(UFCKeypadWindow)
install_radar_ins_step_split(UFCKeypadWindow)
install_manual_setup_automation(UFCKeypadWindow)
```

实际顺序必须根据最新仓库源码确认，避免 patch 覆盖。

同时更新：

```text
main.py
main_safe.py
UFC_Keypad_v5.spec
_verify.py
README.md
CODEX_PROGRESS.md
```

---

## 4. 备用姿态仪自动化要求

### 4.1 只自动解锁

目标仅为：

```text
将备用姿态仪从锁定状态切换到正常工作/解锁状态。
```

不执行：

```text
- 自动调水平。
- 自动根据飞机当前俯仰/横滚校准基准。
- 自动修正小飞机标线。
```

### 4.2 必须先从最新本机映射确认控制项

不要凭印象硬编码控制 ID。

优先查找：

```text
DCS-BIOS 最新 FA-18C_hornet.lua
用户本机 DCS World\Mods\aircraft\FA-18C\Cockpit\Scripts\clickabledata.lua
用户本机 DCS World\Mods\aircraft\FA-18C\Cockpit\Scripts\devices.lua
```

需要确认：

```text
- DCS-BIOS identifier
- device ID
- command ID
- 解锁对应 value
- 可用于确认状态的 draw argument 或 DCS-BIOS 输出字段
```

### 4.3 必须闭环确认

正确逻辑：

```text
读取当前锁定状态
↓
若已解锁，直接完成该子阶段
↓
通过主通道发解锁命令
↓
等待反馈
↓
确认 draw argument / 输出状态变化
↓
成功后进入 RADALT
```

如果没有可读反馈，至少要：

```text
- 记录命令是否发送；
- 设置短超时；
- 失败后进入人工接管；
- 不要假装成功。
```

---

## 5. RADALT MIN 自动化要求

DCS-BIOS 当前公开 FA-18C 映射中存在：

```text
RADALT_HEIGHT
RADALT_MIN_HEIGHT_PTR
```

已知公开映射：

```text
控制：RADALT_HEIGHT
设备：30
命令：3002
控制 argument：291
反馈：RADALT_MIN_HEIGHT_PTR
反馈 argument：287
```

但必须以最新 DCS-BIOS 和用户本机版本为准。

### 5.1 目标值配置化

不要硬编码在 Python 逻辑中。

建议在 `ufc_config.json` 增加：

```json
{
  "manual_setup_targets": {
    "land": {
      "radalt_min_ft": 200,
      "bingo_fuel_lb": 3000
    },
    "carrier": {
      "radalt_min_ft": 200,
      "bingo_fuel_lb": 4000
    }
  }
}
```

上述数字只作为示例默认值。若仓库或用户已有 SOP 配置，以实际要求为准。

代码应提供合理 fallback，但不要让目标值散落在多个模块里。

### 5.2 采用闭环控制

必须读取当前 RADALT minimum，再决定增减方向。

伪代码：

```python
def set_radalt_min_closed_loop(target_ft, done, fail):
    current = read_radalt_min_ft()

    if current is None:
        fail("NO RADALT FEEDBACK")
        return

    if abs(current - target_ft) <= tolerance_ft:
        done()
        return

    direction = "increase" if current < target_ft else "decrease"
    send_one_radalt_step(direction)
    wait_for_feedback_then_repeat()
```

### 5.3 处理反馈标度

`RADALT_MIN_HEIGHT_PTR` 可能是归一化值，不一定直接是英尺。

Codex 必须先确认：

```text
- 输出是否已经是英尺；
- 若是 0..1 归一化值，建立 argument → feet 映射；
- 若可通过 DCS-BIOS 文本/数值直接读取，优先用已换算字段。
```

禁止在未验证标度时假设 `0.2 = 200 ft`。

### 5.4 安全限制

建议常量：

```python
RADALT_TOLERANCE_FT = 10
RADALT_MAX_PULSES = 150
RADALT_FEEDBACK_TIMEOUT_MS = 1000
```

超过上限进入：

```text
MANUAL SETUP HOLD
RADALT COMMAND NO EFFECT
```

---

## 6. BINGO FUEL 自动化要求

### 6.1 先定位真实控制和反馈字段

Codex 必须从最新 DCS-BIOS FA-18C 模块或本机 cockpit 脚本中定位：

```text
- BINGO 增加命令
- BINGO 减少命令
- 当前 BINGO 数值输出
- 显示字段格式和单位
```

可能位于 IFEI 相关字段中，但不要假设具体 identifier 名称。

需要检索关键词：

```text
BINGO
IFEI
FUEL
UP / DOWN
increment / decrement
```

### 6.2 必须读取当前值后闭环调节

禁止使用固定点击次数。

正确逻辑：

```text
读取当前 BINGO
↓
与 LAND/CV 目标比较
↓
每次只发一个增减脉冲
↓
等待新反馈
↓
再次比较
↓
达到目标后结束
```

建议：

```python
BINGO_TOLERANCE_LB = 0
BINGO_MAX_PULSES = 100
BINGO_FEEDBACK_TIMEOUT_MS = 1000
```

如果 DCS 的 BINGO 调节步进是固定 100 lb，则目标值必须校验为合法步进倍数。

---

## 7. DCS-BIOS 与 Export bridge 的使用原则

严格遵守仓库现有原则：

```text
主通道：DCS-BIOS
备用通道：Export bridge
```

绝对禁止同一动作同时从两个通道发送。

错误做法：

```text
DCS-BIOS press
+ 同时 Export clickable press
```

这可能导致一次操作变成双击或旋钮跳两格。

正确 fallback 逻辑不是只看 UDP `send()` 返回值，因为 UDP 发送成功不代表座舱动作成功。

应当：

```text
DCS-BIOS 发一个动作
↓
等待状态反馈变化
↓
如果在超时内没有变化
↓
才尝试 Export bridge
↓
再次等待反馈
```

如果两个通道均无效果，进入人工接管。

---

## 8. 自动状态机设计建议

建议状态：

```text
idle
standby_read
standby_command
standby_verify
radalt_read
radalt_command
radalt_verify
bingo_read
bingo_command
bingo_verify
complete
failed
```

建议统一上下文：

```python
self._manual_setup_phase
self._manual_setup_pulse_count
self._manual_setup_last_feedback
self._manual_setup_failure_reason
```

建议入口：

```python
def _cold_run_manual_setup_auto(self, advance_if_running):
    ...
```

在 `_cold_run_next_step()` 中处理：

```python
elif kind == "manual_setup_auto":
    self._cold_run_manual_setup_auto(advance_if_running)
```

必须尊重：

```text
- _cold_sequence_token
- _cold_state
- RESET
- 页面切换
- 用户暂停/人工接管
```

任何延迟回调执行前都应重新检查 token 和 state，避免 RESET 后旧回调继续发送命令。

---

## 9. 人工接管行为

任何子阶段失败后，应进入：

```python
self._cold_state = "wait_user"
self._cold_exec_phase = "USER"
```

UI 示例：

```text
MANUAL SETUP PARTIAL
STANDBY UNLOCK: OK
RADALT MIN: 200 FT OK
BINGO: NO FEEDBACK
Set remaining item manually, then press START.
```

按 `START` 后允许进入下一步。

不允许：

```text
- 无限重试；
- 无反馈仍自动推进；
- 静默失败；
- 把失败当成功写入日志。
```

---

## 10. 日志要求

每个子阶段记录：

```text
- 当前读数
- 目标值
- 发送通道
- 发送命令
- 反馈前后变化
- pulse count
- timeout
- fallback 是否触发
- 最终成功或失败原因
```

日志示例：

```text
MANUAL_SETUP standby current=locked primary=dcs_bios
MANUAL_SETUP standby feedback locked->unlocked success
MANUAL_SETUP radalt current=120 target=200 direction=up pulse=8
MANUAL_SETUP radalt reached current=198 target=200
MANUAL_SETUP bingo current=2400 target=3000 direction=up pulse=6
MANUAL_SETUP complete
```

---

## 11. 配置兼容性

新增配置时必须：

```text
- 对旧 ufc_config.json 向后兼容；
- 缺失 manual_setup_targets 时使用默认值；
- 不覆盖用户已有其他设置；
- SettingsWindow 是否需要 UI 配置可后续再做，本次优先支持 JSON 配置。
```

建议配置读取集中在一个函数中：

```python
def manual_setup_targets(profile: str) -> dict:
    ...
```

---

## 12. 验证要求

必须更新 `_verify.py`。

至少覆盖：

```text
1. LAND/CV 步骤数量和顺序更新正确。
2. 第 19 步 kind 为 manual_setup_auto。
3. 备用姿态仪已解锁时不重复发送。
4. RADALT 当前值低于目标时只发 increase。
5. RADALT 当前值高于目标时只发 decrease。
6. BINGO 同样按当前值选择方向。
7. 达到目标后自动进入下一子阶段。
8. 超过最大 pulse 后进入 wait_user。
9. DCS-BIOS 成功且反馈变化时 Export bridge 不发送。
10. DCS-BIOS 无反馈时才尝试 Export bridge。
11. 两个通道绝不同时执行同一动作。
12. RESET 或 token 变化后，旧定时回调不再发送命令。
13. 原有 RADAR/INS 两步确认逻辑仍然有效。
14. 原有 HMD IFA 后等待 10 秒与 OSB 200 ms 单通道逻辑仍然有效。
15. CV 自动配平回归测试仍通过。
```

测试不得真实发送 DCS 命令，应 mock：

```text
DCS-BIOS sender
Export bridge sender
telemetry getter
QTimer.singleShot
```

---

## 13. 实机验收标准

### 备用姿态仪

```text
第 19 步开始后，备用姿态仪锁定机构真实解除。
反馈状态从 locked 变为 unlocked。
程序不执行水平校准。
```

### RADALT MIN

```text
程序读取当前最低告警值。
自动调节到配置目标值。
误差在设定容差内。
无双击、无一次跳两格问题。
```

### BINGO

```text
程序读取当前 BINGO 值。
自动调节到 LAND/CV 对应目标。
达到目标后停止，不继续误触。
```

### 整体

```text
三项全部成功后，第 19 步自动完成并进入下一步。
任意一项失败时进入人工接管，用户手动完成后按 START 可继续。
```

---

## 14. 不允许破坏的现有功能

不要回退以下已完成行为：

```text
- 冷舱/热舱自动检测。
- DAY/NIGHT 与 LAND/CV 设置流程。
- RESET 保留当前步骤。
- COMPLETE 跳转 LOCAL ICP。
- 弹射座椅和 ECM 当前实机修正值。
- CV 自动配平闭环。
- RADAR / INS 与 AMPCD PB19 已拆成两个独立人工确认步骤。
- RADAR/INS 两步之间没有固定 10 秒延时。
- HMD 开启并 INS 转 IFA 后等待 10 秒再执行 RDDI OSB。
- RDDI OSB 按下保持 200 ms。
- RDDI OSB 使用 DCS-BIOS 主通道，Export bridge 只做反馈失败后的备用，不能同时发送。
```

---

## 15. Codex 最终交付内容

完成后请提供：

```text
1. 修改摘要。
2. 实际使用的 DCS-BIOS identifier / device / command / argument。
3. 新增配置项和默认值。
4. 自动状态机说明。
5. fallback 和人工接管说明。
6. _verify.py 完整结果。
7. 实机测试步骤。
8. 所有 commit SHA。
```

不要只给方案，需直接修改最新仓库代码、运行验证并提交 Git。
