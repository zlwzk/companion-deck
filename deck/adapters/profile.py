"""自定义热键方案适配器（任意软件）。

不需要写代码：在 config.json 的 profiles 里为任意软件定义一组热键
（组合键名见 deck/hotkeys.py 的 VK_MAP 与字母/数字/F1-F24），
即可用手机控制它——这是「适配未来所有软件」的零代码路径。
"""

from __future__ import annotations

from typing import Optional

from deck.hotkeys import send_keys

from .base import BaseAdapter, Unsupported

_KNOWN_ACTIONS = (
    "play_pause", "next", "prev", "stop",
    "volume_up", "volume_down", "toggle_mute",
)


class ProfileAdapter(BaseAdapter):
    name = "profile"
    display_name = "自定义热键方案（任意软件）"
    description = "在配置里为任意软件定义热键方案，用手机控制它（零代码适配）"
    capabilities = {"play_pause", "next", "prev", "stop", "volume"}

    def __init__(self, config: dict | None = None) -> None:
        super().__init__(config)
        self._profiles: list[dict] = (config or {}).get("profiles") or []
        self._active = (config or {}).get("active_profile")
        if self._active is None and self._profiles:
            self._active = self._profiles[0]["name"]

    # ---------- 生命周期 ----------
    def available(self) -> bool:
        return bool(self._profiles)

    # ---------- 方案管理 ----------
    def _profile(self) -> dict | None:
        for p in self._profiles:
            if p.get("name") == self._active:
                return p
        return None

    def _hotkey(self, action: str) -> list[str] | None:
        profile = self._profile()
        if profile is None:
            return None
        keys = (profile.get("hotkeys") or {}).get(action)
        return keys if keys else None

    def profiles(self) -> list[str]:
        return [p.get("name", "未命名") for p in self._profiles]

    def current_profile(self) -> Optional[str]:
        return self._active

    def switch_profile(self, name: str) -> None:
        names = [p.get("name") for p in self._profiles]
        if name in names:
            self._active = name

    def enabled_actions(self) -> list[str]:
        profile = self._profile()
        if profile is None:
            return []
        defined = set((profile.get("hotkeys") or {}).keys())
        return [a for a in _KNOWN_ACTIONS if a in defined]

    # ---------- 传输控制 ----------
    def _run(self, action: str) -> None:
        keys = self._hotkey(action)
        if not keys:
            raise Unsupported(f"当前方案未定义 {action}")
        send_keys(keys)

    def play_pause(self) -> None:
        self._run("play_pause")

    def next(self) -> None:
        self._run("next")

    def prev(self) -> None:
        self._run("prev")

    def stop(self) -> None:
        self._run("stop")

    def volume_up(self) -> None:
        self._run("volume_up")

    def volume_down(self) -> None:
        self._run("volume_down")

    def toggle_mute(self) -> None:
        self._run("toggle_mute")
