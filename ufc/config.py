# -*- coding: utf-8 -*-
"""配置保存 / 加载 (ufc_config.json)"""
import os
import json
import sys

# 配置文件位于项目根目录 (包的上一级)
if getattr(sys, 'frozen', False):
    _CONF_DIR = os.path.dirname(sys.executable)
else:
    _CONF_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(_CONF_DIR, "ufc_config.json")
CRASH_LOG_FILE = os.path.join(_CONF_DIR, "ufc_crash.log")

def save_config(config_dict):
    """保存通用配置到 ufc_config.json"""
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config_dict, f, ensure_ascii=False, indent=2)
        print(f"[配置] 已保存: {CONFIG_FILE}")
    except Exception as e:
        print(f"[配置] 保存失败: {e}")

def load_config():
    """加载通用配置"""
    if not os.path.exists(CONFIG_FILE):
        return {}
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"[配置] 加载失败: {e}")
        return {}
