"""PTT（Push-To-Talk）自动按键：播放声音时自动按下游戏内的语音激活键。

设计要点：
- 使用 ctypes 调 user32.keybd_event，零新增依赖，可随单文件 exe 打包
- 两种模式：
  - hold（长按）：播放开始时按下，播放停止/暂停时松开
  - tap（点按）：播放开始时短促按一下
- 双层触发：
  1. API 播放路径同步调 before_play()（带提前量，避免语音开头被游戏截断）
  2. 监控线程轮询播放状态兜底（覆盖 Soundpad 侧热键直接触发的播放）
- 2 秒去重：两个触发层短时间内不会重复按键
- 可配参数：
  - lead_ms（0~500）：按键先于播放的提前量，给游戏语音通道建立时间
  - tap_ms（0~500）：tap 模式的按键时长
  - tail_ms（300~1000）：hold 模式声音结束后多按一会儿再松开，盖住收尾截断
"""

from __future__ import annotations

import sys
import threading
import time

# 命名键 → VK 码
_NAMED = {
    "SPACE": 0x20,
    "ENTER": 0x0D,
    "TAB": 0x09,
    "ESC": 0x1B,
    "SHIFT": 0x10,
    "CTRL": 0x11,
    "ALT": 0x12,
    "CAPSLOCK": 0x14,
    "UP": 0x26,
    "DOWN": 0x28,
    "LEFT": 0x25,
    "RIGHT": 0x27,
}
for _i in range(1, 13):  # F1-F12
    _NAMED[f"F{_i}"] = 0x6F + _i

MODES = ("hold", "tap")

DEFAULTS = {
    "enabled": False,
    "key": "V",
    "mode": "hold",
    "lead_ms": 150,
    "tap_ms": 60,
    "tail_ms": 500,
}

# 各参数允许范围（毫秒）
LEAD_RANGE = (0, 500)
TAP_RANGE = (0, 500)
TAIL_RANGE = (300, 1000)

# 监控线程的触发去重窗口（秒）
_DEDUP_SECONDS = 2.0


def normalize_key(raw: object) -> str | None:
    """把用户输入规范化为键名；无法识别返回 None。

    支持：单个 A-Z / 0-9 字符，或 _NAMED 中的命名键（大小写不敏感）。
    """
    if not isinstance(raw, str):
        return None
    key = raw.strip().upper()
    if not key:
        return None
    if len(key) == 1 and ("A" <= key <= "Z" or "0" <= key <= "9"):
        return key
    if key in _NAMED:
        return key
    return None


def vk_code(key: str) -> int:
    """键名 → Windows 虚拟键码。"""
    if len(key) == 1:
        if "A" <= key <= "Z":
            return ord(key)
        if "0" <= key <= "9":
            return 0x30 + (ord(key) - ord("0"))
    return _NAMED[key]


def clamp_ms(raw: object, default: int, lo: int, hi: int) -> int:
    """毫秒参数：转 int 并夹在 [lo, hi]；非法值回退默认。"""
    try:
        value = int(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, value))


class PttController:
    """按配置在播放前后自动按下/松开指定按键。"""

    def __init__(self, cfg_getter) -> None:
        # cfg_getter() -> dict，返回当前 ptt 配置
        self._cfg_getter = cfg_getter
        self._lock = threading.Lock()
        self._holding = False
        self._last_trigger = 0.0
        self._tail_timer: threading.Timer | None = None

    # ---- 底层按键 ----
    @staticmethod
    def _press(vk: int, up: bool) -> None:
        if sys.platform != "win32":
            return
        import ctypes

        ctypes.windll.user32.keybd_event(vk, 0, 0x0002 if up else 0, 0)

    def _down(self, vk: int) -> None:
        self._press(vk, up=False)

    def _up(self, vk: int) -> None:
        self._press(vk, up=True)

    # ---- 配置 ----
    def _cfg(self) -> dict:
        cfg = self._cfg_getter() or {}
        return {
            "enabled": bool(cfg.get("enabled", False)),
            "key": normalize_key(cfg.get("key")) or DEFAULTS["key"],
            "mode": cfg.get("mode") if cfg.get("mode") in MODES else DEFAULTS["mode"],
            "lead_ms": clamp_ms(cfg.get("lead_ms"), DEFAULTS["lead_ms"], *LEAD_RANGE),
            "tap_ms": clamp_ms(cfg.get("tap_ms"), DEFAULTS["tap_ms"], *TAP_RANGE),
            "tail_ms": clamp_ms(cfg.get("tail_ms"), DEFAULTS["tail_ms"], *TAIL_RANGE),
        }

    # ---- 状态 ----
    def is_holding(self) -> bool:
        with self._lock:
            return self._holding

    # ---- 对外接口 ----
    def before_play(self) -> None:
        """播放前调用：tap 短按一下；hold 按下并保持。自带 2 秒去重。"""
        cfg = self._cfg()
        if not cfg["enabled"]:
            return
        now = time.monotonic()
        with self._lock:
            self._cancel_tail_timer_locked()  # 新播放先到：取消尾巴松开，按键保持
            if now - self._last_trigger < _DEDUP_SECONDS:
                return
            self._last_trigger = now
            if self._holding:
                return  # 已按住，无需重复按
            vk = vk_code(cfg["key"])
            if cfg["mode"] == "tap":
                self._down(vk)
                time.sleep(cfg["tap_ms"] / 1000)
                self._up(vk)
            else:
                self._down(vk)
                self._holding = True
                time.sleep(cfg["lead_ms"] / 1000)

    def on_playback(self, playing: bool) -> None:
        """监控层调用：外部触发的播放补按；停止/暂停时按 tail_ms 延迟松开。"""
        cfg = self._cfg()
        if not cfg["enabled"]:
            return
        if playing:
            # before_play 自带去重与"已按住"判断，不会重复按键
            self.before_play()
        else:
            self._schedule_release(cfg["tail_ms"])

    def _schedule_release(self, tail_ms: int) -> None:
        """tail 毫秒后松开；期间若有新播放则取消（按键保持不松）。"""
        with self._lock:
            if not self._holding:
                return
            self._cancel_tail_timer_locked()
            timer = threading.Timer(tail_ms / 1000, self.release)
            timer.daemon = True
            self._tail_timer = timer
            timer.start()

    def _cancel_tail_timer_locked(self) -> None:
        timer = self._tail_timer
        self._tail_timer = None
        if timer is not None:
            timer.cancel()

    def release(self) -> None:
        """立即松开 hold 按键（幂等，并取消未到的 tail 定时器）。"""
        with self._lock:
            self._cancel_tail_timer_locked()
            if not self._holding:
                return
            cfg = self._cfg()
            self._up(vk_code(cfg["key"]))
            self._holding = False

    def test_press(self) -> str:
        """设置页「试按一下」：用当前配置的按键短按一次，返回实际按下的键名。

        不受 enabled 开关限制（显式测试动作）；按住时长取 tap_ms 与 300ms 的较大值，
        保证游戏里肉眼/耳听可辨。
        """
        cfg = self._cfg()
        vk = vk_code(cfg["key"])
        hold_s = max(cfg["tap_ms"], 300) / 1000
        with self._lock:
            self._cancel_tail_timer_locked()
        self._down(vk)
        time.sleep(hold_s)
        self._up(vk)
        return cfg["key"]

    def shutdown(self) -> None:
        """退出前确保按键被松开。"""
        self.release()
