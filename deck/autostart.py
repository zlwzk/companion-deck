r"""开机自启（Windows 注册表 Run 键，零第三方依赖）。

写入 HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run 下，
名为 CompanionDeck，值为启动命令（默认 `pythonw -m deck`，或打包后的 exe 路径）。
"""

from __future__ import annotations

import ctypes
import sys
import winreg
from pathlib import Path
from typing import Optional

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_APP_NAME = "CompanionDeck"


def _startup_command(config_path: Optional[str] = None) -> str:
    """构造开机自启命令行。

    优先使用打包后的 exe（PyInstaller）；开发环境用 pythonw -m deck。
    """
    if getattr(sys, "frozen", False):  # PyInstaller 打包后
        exe = Path(sys.executable)
        cmd = f'"{exe}"'
    else:
        # 开发环境：用当前 Python 解释器
        python = sys.executable
        # 找到项目根目录（含 deck 包）
        here = Path(__file__).resolve().parent.parent
        cmd = f'"{python}" -m deck'
        cmd += f' --cwd "{here}"' if here else ""
    if config_path:
        cmd += f' --config "{config_path}"'
    return cmd


def is_enabled() -> bool:
    """是否已设置开机自启。"""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, _APP_NAME)
            return bool(value)
    except FileNotFoundError:
        return False
    except OSError:
        return False


def enable() -> bool:
    """启用开机自启。"""
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.SetValueEx(key, _APP_NAME, 0, winreg.REG_SZ, _startup_command())
        return True
    except OSError:
        return False


def disable() -> bool:
    """禁用开机自启。"""
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.DeleteValue(key, _APP_NAME)
        return True
    except FileNotFoundError:
        return True  # 本来就没有，视为成功
    except OSError:
        return False


def set_enabled(enabled: bool) -> bool:
    """切换开机自启状态。"""
    return enable() if enabled else disable()
