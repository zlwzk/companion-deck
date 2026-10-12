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
    # 新增字段：Soundpad RC v1.1.x 在 GetCategories 返回的 Sound 元素里携带
    artist: Optional[str] = None
    title: Optional[str] = None
    duration: Optional[str] = None  # 形如 "00:02"
    play_count: Optional[int] = None
    added_on: Optional[str] = None
    last_played_on: Optional[str] = None
    tag: Optional[str] = None
    # 所属分类索引（用于按分类播放）
    category_index: Optional[int] = None
    # 分类内位置（用于 DoPlaySoundFromCategory 的 soundIndex 参数）
    position_in_category: Optional[int] = None


class Category(BaseModel):
    """Soundpad 分类节点（可嵌套，含子分类与声音）。"""

    index: int
    name: str
    type: Optional[int] = None  # 1 = 系统分类（All sounds），0 = 用户分类
    hidden: bool = False
    sounds: list[Track] = Field(default_factory=list)
    subcategories: list["Category"] = Field(default_factory=list)


Category.model_rebuild()


class SoundButton(BaseModel):
    """声音面板按钮：可以按 Soundpad 列表索引播放，也可以触发一组热键。"""

    id: str
    name: str
    kind: str = "index"  # index | hotkey | category_sound | random
    index: Optional[int] = None
    hotkey: list[str] = Field(default_factory=list)
    category: Optional[str] = None  # 所属分类（自动生成时继承自声音列表）
    category_index: Optional[int] = None  # 所属分类索引
    position_in_category: Optional[int] = None  # 分类内位置


class AdapterInfo(BaseModel):
    name: str
    display_name: str
    description: str
    available: bool
    capabilities: list[str]  # 能力集合：play_pause/next/prev/stop/volume/tracks/state/sounds/categories/seek/random
    actions: list[str] = Field(default_factory=list)  # 当前可用的传输操作


class PlaybackInfo(BaseModel):
    status: str = "stopped"  # playing | paused | stopped
    position_ms: int = 0
    duration_ms: int = 0
    track_name: Optional[str] = None
    # 新增字段：当前播放声音的元数据（来自 GetSoundlist 解析结果映射）
    artist: Optional[str] = None
    title: Optional[str] = None
    play_count: Optional[int] = None
    index: Optional[int] = None


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
    # 新增：分类树（仅支持 categories 能力的适配器填充）
    categories: list[Category] = Field(default_factory=list)
    # 新增：当前选中分类索引
    current_category_index: Optional[int] = None
    # 新增：当前选中分类名
    current_category_name: Optional[str] = None
