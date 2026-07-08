# -*- coding: utf-8 -*-
"""UFC Keypad - F/A-18C UFC 触控面板 (DCS-BIOS).

模块化包结构：
    ufc.constants  - 常量 / DCS-BIOS 标识符 / 布局辅助
    ufc.crashlog   - 崩溃日志
    ufc.config     - 配置存取
    ufc.fonts      - Hornet UFC 字体加载
    ufc.morse      - 莫尔斯电码引擎
    ufc.colors     - 亮度颜色计算
    ufc.dcs_bios   - DCS-BIOS 解析 / 接收 / 发送
    ufc.input      - 原生触控钩子 + 键位注入
    ufc.widgets    - UFCCell / UFCBlank 控件
    ufc.startup    - UFC 上电 / BIT 启动覆盖层
    ufc.ui         - UFCKeypadWindow / SettingsWindow
    main.py        - 程序入口
"""

__version__ = "5.0"
