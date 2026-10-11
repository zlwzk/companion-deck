"""系统媒体键适配器（通用）。

模拟 Windows 媒体键（播放/暂停、下一首、上一首、停止、音量），
Windows 会把媒体键路由到当前活动的媒体会话——因此无需配置，
就能控制正在播放的 Spotify / 浏览器 / 视频播放器等任意软件。
"""

from __future__ import annotations

from deck.hotkeys import send_keys

from .base import BaseAdapter

_KEYS = {
    "play_pause": ["media_play_pause"],
    "next": ["media_next"],
    "prev": ["media_prev"],
    "stop": ["media_stop"],
    "volume_up": ["volume_up"],
    "volume_down": ["volume_down"],
    "toggle_mute": ["volume_mute"],
}


class MediaKeysAdapter(BaseAdapter):
    name = "mediakeys"
    display_name = "系统媒体键（通用）"
    description = "模拟 Windows 媒体键，控制当前正在播放的媒体会话（Spotify/浏览器/播放器/游戏内媒体）"
    capabilities = {"play_pause", "next", "prev", "stop", "volume"}

    def _press(self, action: str) -> None:
        keys = _KEYS.get(action)
        if keys:
            send_keys(keys)

    def play_pause(self) -> None:
        self._press("play_pause")

    def next(self) -> None:
        self._press("next")

    def prev(self) -> None:
        self._press("prev")

    def stop(self) -> None:
        self._press("stop")

    def volume_up(self) -> None:
        self._press("volume_up")

    def volume_down(self) -> None:
        self._press("volume_down")

    def toggle_mute(self) -> None:
        self._press("toggle_mute")
