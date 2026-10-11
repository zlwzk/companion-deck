"""全局热键模拟（SendInput）。

用于「系统媒体键」与「自定义热键方案」两类适配器。
使用 ctypes 直接调用 SendInput，无需管理员权限，不依赖第三方库。
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import time

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002

VK_MAP = {
    "media_play_pause": 0xB3,
    "media_next": 0xB0,
    "media_prev": 0xB1,
    "media_stop": 0xB2,
    "volume_up": 0xAF,
    "volume_down": 0xAE,
    "volume_mute": 0xAD,
    "ctrl": 0x11,
    "control": 0x11,
    "alt": 0x12,
    "shift": 0x10,
    "win": 0x5B,
    "space": 0x20,
    "enter": 0x0D,
    "esc": 0x1B,
    "tab": 0x09,
    "up": 0x26,
    "down": 0x28,
    "left": 0x25,
    "right": 0x27,
    "home": 0x24,
    "end": 0x23,
    "pgup": 0x21,
    "pgdn": 0x22,
}


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wt.WORD),
        ("wScan", wt.WORD),
        ("dwFlags", wt.DWORD),
        ("time", wt.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("padding", ctypes.c_byte * 24)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("i",)
    _fields_ = [("type", wt.DWORD), ("i", _INPUTUNION)]


_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.SendInput.argtypes = [wt.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
_user32.SendInput.restype = wt.UINT


def key_code(name: str) -> int:
    n = name.strip().lower()
    if n in VK_MAP:
        return VK_MAP[n]
    if len(n) == 1 and n.isalnum():
        return ord(n.upper())
    if n.startswith("f") and n[1:].isdigit() and 1 <= int(n[1:]) <= 24:
        return 0x6F + int(n[1:])  # F1 = 0x70
    raise ValueError(f"未知按键: {name!r}")


def _input(vk: int, key_up: bool = False) -> INPUT:
    inp = INPUT()
    inp.type = INPUT_KEYBOARD
    inp.ki.wVk = vk
    if key_up:
        inp.ki.dwFlags = KEYEVENTF_KEYUP
    return inp


def _fire(items: list[INPUT]) -> None:
    if not items:
        return
    arr = (INPUT * len(items))(*items)
    _user32.SendInput(len(items), arr, ctypes.sizeof(INPUT))


def send_keys(keys: list[str], hold: float = 0.03) -> None:
    """依次按下组合键，再按相反顺序抬起。keys 示例：["ctrl","alt","p"]"""
    vks = [key_code(k) for k in keys]
    if not vks:
        return
    _fire([_input(vk) for vk in vks])
    time.sleep(hold)
    _fire([_input(vk, key_up=True) for vk in reversed(vks)])
