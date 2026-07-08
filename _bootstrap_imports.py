# -*- coding: utf-8 -*-
"""启动期包名大小写兼容。

项目源码标准包名是小写 ``ufc``。但 Windows / ZIP 解压 / 手工复制时，目录可能变成
``UFC``。在某些环境中 ``import ufc`` 仍会失败。本模块在任何 ufc.* import 之前运行，
把大写 ``UFC`` 目录显式注册为 Python 包 ``ufc``。
"""
import importlib.util
import os
import sys


def ensure_ufc_package(base_dir=None):
    """确保 ``import ufc`` 可用。

    返回实际使用的包目录路径；失败时返回 None。
    """
    if base_dir is None:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    base_dir = os.path.abspath(base_dir)

    if base_dir not in sys.path:
        sys.path.insert(0, base_dir)

    lower_dir = os.path.join(base_dir, "ufc")
    upper_dir = os.path.join(base_dir, "UFC")

    # 标准结构存在时直接使用。
    if os.path.exists(os.path.join(lower_dir, "__init__.py")):
        return lower_dir

    # 兼容大写目录：把 UFC/__init__.py 作为包 ufc 加载。
    init_file = os.path.join(upper_dir, "__init__.py")
    if os.path.exists(init_file):
        if "ufc" in sys.modules:
            return upper_dir
        spec = importlib.util.spec_from_file_location(
            "ufc",
            init_file,
            submodule_search_locations=[upper_dir],
        )
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        module.__path__ = [upper_dir]
        sys.modules["ufc"] = module
        spec.loader.exec_module(module)
        return upper_dir

    return None
