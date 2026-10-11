"""配置加载 / 保存。首次运行自动生成 config.json 与访问口令。"""

from __future__ import annotations

import copy
import json
import secrets
import threading
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"

_lock = threading.Lock()

DEFAULTS: dict = {
    "server": {"host": "0.0.0.0", "port": 8390},
    "auth": {
        "enabled": True,
        "token": None,  # None 表示首次运行时自动生成
    },
    "active_adapter": "soundpad",
    "adapters": {
        "soundpad": {
            "enabled": True,
            # 声音面板按钮：id / name / kind(index|hotkey) / index 或 hotkey
            # 留空则自动从 Soundpad 声音列表生成（按列表索引播放）
            "sounds": [],
        },
        "mediakeys": {
            "enabled": True,
        },
        "profile": {
            "enabled": True,
            "active_profile": "Spotify",
            # 为任意软件定义的热键方案
            "profiles": [
                {
                    "name": "Spotify",
                    "description": "桌面版 Spotify 全局快捷键",
                    "hotkeys": {
                        "play_pause": ["ctrl", "alt", "p"],
                        "next": ["ctrl", "alt", "n"],
                        "prev": ["ctrl", "alt", "b"],
                        "stop": ["ctrl", "alt", "s"],
                        "volume_up": ["ctrl", "alt", "up"],
                        "volume_down": ["ctrl", "alt", "down"],
                        "toggle_mute": ["ctrl", "alt", "m"],
                    },
                },
                {
                    "name": "VLC",
                    "description": "VLC 媒体播放器全局快捷键示例（请在 VLC 设置中配置相同组合）",
                    "hotkeys": {
                        "play_pause": ["ctrl", "alt", "p"],
                        "next": ["ctrl", "alt", "right"],
                        "prev": ["ctrl", "alt", "left"],
                        "stop": ["ctrl", "alt", "s"],
                    },
                },
            ],
        },
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    """浅层配置与默认配置合并，保证新版本新增字段自动补齐。"""
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load(path: Path | str = CONFIG_PATH) -> dict:
    with _lock:
        path = Path(path)
        if not path.exists():
            cfg = copy.deepcopy(DEFAULTS)
            if cfg["auth"]["token"] is None:
                cfg["auth"]["token"] = secrets.token_urlsafe(16)
            save(cfg, path)
            return cfg

        raw = json.loads(path.read_text(encoding="utf-8"))
        cfg = _deep_merge(DEFAULTS, raw)
        if not cfg["auth"].get("token"):
            cfg["auth"]["token"] = secrets.token_urlsafe(16)
            save(cfg, path)
        return cfg


def save(cfg: dict, path: Path | str = CONFIG_PATH) -> None:
    Path(path).write_text(
        json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8"
    )
