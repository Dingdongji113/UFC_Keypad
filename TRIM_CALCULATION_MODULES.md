# 独立弹射配平计算模块

当前新增两个纯计算模块，暂不由 `main.py`、冷启动状态机或 DCS Export bridge 调用。

## `ufc/weight_trim.py`

根据飞机总重返回基础纵向弹射配平目标：

| 重量 | 目标 |
|---|---:|
| `<= 44,000 lb` | `16° nose-up` |
| `44,000 < W < 49,000 lb` | `17° nose-up` |
| `>= 49,000 lb` | `19° nose-up` |

主要接口：

```python
from ufc.weight_trim import carrier_launch_weight_trim

decision = carrier_launch_weight_trim(45000)
print(decision.target_deg_nose_up)  # 17.0
```

## `ufc/asymmetric_launch_trim.py`

根据各挂点总重量计算净不对称外挂力矩，并按当前资料中的曲线给出横向差动平尾建议。

当前官方力臂表：

| 挂点 | 力臂 |
|---:|---:|
| 1 / 9 | `-19.5 / +19.5 ft` |
| 2 / 8 | `-11.2 / +11.2 ft` |
| 3 / 7 | `-7.3 / +7.3 ft` |
| 4 / 6 | `-3.7 / +3.7 ft` |

中心线挂点 5 不计入横向力矩。

主要接口：

```python
from ufc.asymmetric_launch_trim import carrier_launch_asymmetric_trim

decision = carrier_launch_asymmetric_trim(
    launch_weight_lbs=40000,
    station_weights_lbs={8: 1000},
)
```

模块会返回：

- 带符号和绝对不对称力矩；
- 重载侧与轻载侧；
- 图表差动平尾目标；
- `unloaded wing down` 概念方向；
- 是否允许自动处理；
- 保守拒绝原因。

## 保守边界

当前实现不会擅自填补资料空白：

- `< 11,000 ft-lb`：图表未定义自动目标；
- `> 22,000 ft-lb`：超出图表；
- `<= 36,000 lb` 且力矩 `> 6,000 ft-lb`：拒绝自动处理；
- `36,000–37,000 lb`：资料过渡区，暂不自动处理；
- DCS 中 LEFT/RIGHT trim 命令方向尚未映射；
- 未加入 GBU-24 等特殊修正规则。

## 验证

运行：

```bash
python verify_trim_models.py
```

成功时输出：

```text
ALL TRIM MODEL CHECKS PASSED
```
