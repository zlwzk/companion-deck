"""Soundpad 原生适配器。

通过 Soundpad 官方 Remote Control Interface（命名管道 \\\\.\\pipe\\sp_remote_control）
控制 Soundpad：播放/暂停、上一首/下一首、停止、音量、播放状态、声音列表、按索引播放。
协议与命令参考官方 SoundpadRemoteControl.java。
"""

from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

from deck.core.models import PlaybackInfo, SoundButton, Track
from deck.hotkeys import send_keys
from deck.pipe import send

from .base import BaseAdapter, Unsupported

_PLAY_STATUS_MAP = {
    "STOPPED": "stopped",
    "PLAYING": "playing",
    "PAUSED": "paused",
    "SEEKING": "playing",
}

_CACHE_TTL = 5.0  # 声音列表缓存秒数，避免高频轮询拖慢 UI


class SoundpadAdapter(BaseAdapter):
    name = "soundpad"
    display_name = "Soundpad（原生接口）"
    description = "通过 Soundpad 官方 Remote Control 命名管道控制：切歌、播放/暂停、音量、声音面板"
    capabilities = {"play_pause", "next", "prev", "stop", "volume", "tracks", "state", "sounds"}

    def __init__(self, config: dict | None = None) -> None:
        super().__init__(config)
        self._cache_ts = 0.0
        self._cache_tracks: list[Track] = []
        self._cache_sounds: list[SoundButton] = []

    # ---------- 底层命令 ----------
    def _cmd(self, command: str, timeout: float = 2.0) -> str | None:
        return send(command, timeout=timeout)

    def _ok(self, response: str | None) -> bool:
        return isinstance(response, str) and response.startswith("R-200")

    # ---------- 生命周期 ----------
    def available(self) -> bool:
        return self._ok(self._cmd("IsAlive()"))

    # ---------- 传输控制 ----------
    def play_pause(self) -> None:
        self._cmd("DoTogglePause()")

    def next(self) -> None:
        self._cmd("DoPlayNextSound()")

    def prev(self) -> None:
        self._cmd("DoPlayPreviousSound()")

    def stop(self) -> None:
        self._cmd("DoStopSound()")

    def volume_up(self) -> None:
        volume = self.get_volume()
        if volume is not None:
            self.set_volume(min(100, volume + 5))

    def volume_down(self) -> None:
        volume = self.get_volume()
        if volume is not None:
            self.set_volume(max(0, volume - 5))

    def set_volume(self, volume: int) -> None:
        self._cmd(f"SetVolume({max(0, min(100, int(volume)))})")

    def toggle_mute(self) -> None:
        self._cmd("DoToggleMute()")

    # ---------- 状态与信息 ----------
    def get_playback(self) -> PlaybackInfo:
        status = self._cmd("GetPlayStatus()")
        info = PlaybackInfo(status=_PLAY_STATUS_MAP.get((status or "").strip(), "stopped"))
        position = self._cmd("GetPlaybackPositionInMs()")
        duration = self._cmd("GetPlaybackDurationInMs()")
        if position and position.isdigit():
            info.position_ms = int(position)
        if duration and duration.isdigit():
            info.duration_ms = int(duration)
        return info

    def get_volume(self) -> Optional[int]:
        response = self._cmd("GetVolume()")
        if response and response.isdigit():
            return int(response)
        return None

    def get_muted(self) -> Optional[bool]:
        response = self._cmd("IsMuted()")
        if response and response in ("0", "1"):
            return response == "1"
        return None

    # ---------- 声音列表 ----------
    def _refresh_cache(self) -> None:
        now = time.monotonic()
        if now - self._cache_ts < _CACHE_TTL:
            return
        xml_text = self._cmd("GetSoundlist()")
        tracks = self._parse_soundlist(xml_text or "")
        sounds = self._build_sounds(tracks)
        self._cache_tracks, self._cache_sounds = tracks, sounds
        self._cache_ts = now

    def get_tracks(self) -> list[Track]:
        self._refresh_cache()
        return self._cache_tracks

    def get_sounds(self) -> list[SoundButton]:
        self._refresh_cache()
        return self._cache_sounds

    def _build_sounds(self, tracks: list[Track]) -> list[SoundButton]:
        configured = self.config.get("sounds") or []
        if configured:
            buttons = []
            for i, item in enumerate(configured):
                kind = item.get("kind", "index")
                buttons.append(
                    SoundButton(
                        id=f"cfg-{i}",
                        name=item.get("name", f"按钮 {i + 1}"),
                        kind=kind,
                        index=item.get("index") if kind == "index" else None,
                        hotkey=item.get("hotkey") or [],
                    )
                )
            return buttons
        # 未配置时：从声音列表自动生成按钮（按索引播放）
        return [
            SoundButton(id=str(t.index), name=t.name, kind="index", index=t.index)
            for t in tracks[:500]
        ]

    def play_sound(self, sound: SoundButton) -> None:
        if sound.kind == "index" and sound.index is not None:
            self._cmd(f"DoPlaySound({sound.index})")
        elif sound.kind == "hotkey" and sound.hotkey:
            send_keys(sound.hotkey)
        else:
            raise Unsupported

    def _parse_soundlist(self, xml_text: str) -> list[Track]:
        """容错解析 GetSoundlist() 返回的 XML，兼容不同字段命名。"""
        if not xml_text or xml_text.startswith("R-"):
            return []
        tracks: list[Track] = []
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return self._regex_soundlist(xml_text)

        index = 1
        for el in root.iter():
            tag = el.tag.lower()
            if tag == "sound" or (tag.endswith("sound") and "list" not in tag):
                attrs = {k.lower(): v for k, v in (el.attrib or {}).items()}
                name = attrs.get("name") or attrs.get("title") or (el.text or "").strip()
                path = (
                    attrs.get("path")
                    or attrs.get("file")
                    or attrs.get("filename")
                    or attrs.get("url")
                )
                if not name:
                    for sub in el.iter():
                        if sub.tag.lower() in ("name", "title"):
                            name = (sub.text or "").strip()
                            break
                if not name and path:
                    name = Path(path).stem
                tracks.append(Track(index=index, name=name or f"声音 {index}", path=path or None))
                index += 1

        if not tracks:
            return self._regex_soundlist(xml_text)
        return tracks

    def _regex_soundlist(self, xml_text: str) -> list[Track]:
        entries = re.split(r"<(?:Sound|Entry)\b", xml_text, flags=re.IGNORECASE)[1:]
        tracks: list[Track] = []
        for i, chunk in enumerate(entries, start=1):
            name_m = re.search(r'name\s*=\s*"([^"]*)"', chunk, re.IGNORECASE)
            path_m = re.search(r'path\s*=\s*"([^"]*)"', chunk, re.IGNORECASE)
            name = name_m.group(1) if name_m else ""
            path = path_m.group(1) if path_m else ""
            if not name and path:
                name = Path(path).stem
            if name or path:
                tracks.append(Track(index=i, name=name or f"声音 {i}", path=path or None))
        return tracks
