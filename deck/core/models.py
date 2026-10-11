"""统一数据模型。所有适配器通过这些模型与 Web UI 交互。"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class Track(BaseModel):
    """声音列表中的一项。index 对应 Soundpad「所有声音」分类下的唯一索引。"""

    index: Optional[int] = None
    name: str
    path: Optional[str] = None
    category: Optional[str] = None


class SoundButton(BaseModel):
    """声音面板按钮：可以按 Soundpad 列表索引播放，也可以触发一组热键。"""

    id: str
    name: str
    kind: str = "index"  # index | hotkey
    index: Optional[int] = None
    hotkey: list[str] = Field(default_factory=list)
    category: Optional[str] = None  # 所属分类（自动生成时继承自声音列表）


class AdapterInfo(BaseModel):
    name: str
    display_name: str
    description: str
    available: bool
    capabilities: list[str]  # 能力集合：play_pause/next/prev/stop/volume/tracks/state/sounds
    actions: list[str] = Field(default_factory=list)  # 当前可用的传输操作


class PlaybackInfo(BaseModel):
    status: str = "stopped"  # playing | paused | stopped
    position_ms: int = 0
    duration_ms: int = 0
    track_name: Optional[str] = None


class DeckState(BaseModel):
    version: str = ""
    adapter: str = ""
    adapter_display: str = ""
    adapter_available: bool = False
    auth_enabled: bool = True
    adapters: list[AdapterInfo] = Field(default_factory=list)
    playback: PlaybackInfo = Field(default_factory=PlaybackInfo)
    volume: Optional[int] = None
    muted: Optional[bool] = None
    sounds: list[SoundButton] = Field(default_factory=list)
    profile: Optional[str] = None
    profiles: list[str] = Field(default_factory=list)
