"""适配器基类。

每个目标软件（Soundpad / 媒体会话 / 任意软件的热键方案）实现一个适配器，
声明自己的能力集合，Web UI 会根据能力自动渲染对应控件。
新增适配器只需继承 BaseAdapter 并实现所需方法。
"""

from __future__ import annotations

from typing import Optional

from deck.core.models import PlaybackInfo, SoundButton, Track


class Unsupported(Exception):
    """当前适配器不支持该操作。"""


class BaseAdapter:
    name: str = "base"
    display_name: str = "Base"
    description: str = ""
    # 能力集合，取值：play_pause / next / prev / stop / volume / tracks / state / sounds
    capabilities: set[str] = set()

    def __init__(self, config: dict | None = None) -> None:
        self.config = config or {}

    # ---------- 生命周期 ----------
    def available(self) -> bool:
        """目标软件/通道当前是否可用。"""
        return True

    def activate(self) -> None:
        pass

    def deactivate(self) -> None:
        pass

    # ---------- 传输控制 ----------
    def play_pause(self) -> None:
        raise Unsupported

    def next(self) -> None:
        raise Unsupported

    def prev(self) -> None:
        raise Unsupported

    def stop(self) -> None:
        raise Unsupported

    def volume_up(self) -> None:
        raise Unsupported

    def volume_down(self) -> None:
        raise Unsupported

    def set_volume(self, volume: int) -> None:
        raise Unsupported

    def toggle_mute(self) -> None:
        raise Unsupported

    # ---------- 状态与信息 ----------
    def get_playback(self) -> PlaybackInfo:
        return PlaybackInfo()

    def get_volume(self) -> Optional[int]:
        return None

    def get_muted(self) -> Optional[bool]:
        return None

    def get_tracks(self) -> list[Track]:
        return []

    def get_sounds(self) -> list[SoundButton]:
        return []

    # ---------- 扩展能力 ----------
    def play_sound(self, sound: SoundButton) -> None:
        raise Unsupported

    def switch_profile(self, name: str) -> None:
        raise Unsupported

    def profiles(self) -> list[str]:
        return []

    def current_profile(self) -> Optional[str]:
        return None

    # ---------- UI 辅助 ----------
    _ACTION_KEYS = (
        "play_pause", "next", "prev", "stop",
        "volume_up", "volume_down", "toggle_mute",
    )

    def enabled_actions(self) -> list[str]:
        """当前可用的传输操作列表（按声明顺序）。

        "volume" 为总括能力，自动展开为 volume_up / volume_down / toggle_mute。
        """
        actions = [a for a in self._ACTION_KEYS if a in self.capabilities]
        if "volume" in self.capabilities:
            for a in ("volume_up", "volume_down", "toggle_mute"):
                if a not in actions:
                    actions.append(a)
        return actions
