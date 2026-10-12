"""Soundpad 原生适配器。

通过 Soundpad 官方 Remote Control Interface（命名管道 \\\\.\\pipe\\sp_remote_control）
控制 Soundpad：播放/暂停、上一首/下一首、停止、音量、播放状态、声音列表、按索引播放、
**分类树（含嵌套子分类）、分类切换、分类内随机播放、进度跳转、当前声音元数据**。

协议 v1.1.2，参考官方 SoundpadRemoteControl.java：
- GetSoundlist()        → 仅返回 All sounds 隐藏分类下的扁平声音列表
- GetCategories(t, t)   → 返回完整分类树（XML，含嵌套子分类与各分类下的 Sound）
- DoSelectCategory(i)   → 切换当前激活分类
- DoPlaySoundFromCategory(catIdx, soundPos, renderLine, captureLine)
- DoPlayRandomSound() / DoPlayRandomSoundFromCategory(catIdx, renderLine, captureLine)
- DoSeekMs(pos) / DoJumpMs(delta)
"""

from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

from deck.core.models import Category, PlaybackInfo, SoundButton, Track
from deck.hotkeys import send_keys
from deck.pipe import send

from .base import BaseAdapter, Unsupported

_PLAY_STATUS_MAP = {
    "STOPPED": "stopped",
    "PLAYING": "playing",
    "PAUSED": "paused",
    "SEEKING": "playing",
}

_CACHE_TTL = 5.0  # 列表/分类树缓存秒数，避免高频轮询拖慢 UI


class SoundpadAdapter(BaseAdapter):
    name = "soundpad"
    display_name = "Soundpad（原生接口）"
    description = "通过 Soundpad 官方 Remote Control 命名管道控制：切歌、播放/暂停、音量、声音面板、分类树、随机播放、进度跳转"
    capabilities = {
        "play_pause", "next", "prev", "stop", "volume",
        "tracks", "state", "sounds",
        "categories", "random", "seek",
    }

    def __init__(self, config: dict | None = None) -> None:
        super().__init__(config)
        self._cache_ts = 0.0
        self._cache_tracks: list[Track] = []
        self._cache_sounds: list[SoundButton] = []
        self._cache_categories: list[Category] = []
        # 声音索引 → 元数据映射（来自 GetSoundlist 的 artist/title/playCount 等）
        self._meta_map: dict[int, dict] = {}
        self._current_category_index: Optional[int] = None

    # ---------- 底层命令 ----------
    def _cmd(self, command: str, timeout: float = 2.0) -> str | None:
        return send(command, timeout=timeout)

    def _ok(self, response: str | None) -> bool:
        return isinstance(response, str) and response.startswith("R-200")

    def _bool(self, value: bool) -> str:
        """官方 Java 实现发送小写 true/false。"""
        return "true" if value else "false"

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
        # 尝试从元数据映射里补当前声音信息：Soundpad 没有"当前 index"命令，
        # 只能依据 position 与 GetSoundlist 的 duration 字段做模糊匹配。
        self._enrich_playback(info)
        return info

    def _enrich_playback(self, info: PlaybackInfo) -> None:
        """根据时长与播放次数为 PlaybackInfo 补充当前声音元数据（尽力而为）。"""
        if not self._meta_map:
            return
        # 选播放次数最高且时长最接近的项作为候选
        best: Optional[dict] = None
        best_score: tuple = (-1, 0)
        for idx, meta in self._meta_map.items():
            dur = meta.get("duration_sec")
            play_count = meta.get("play_count") or 0
            # 优先匹配时长（秒级），否则回退到播放次数
            dur_match = 0
            if dur and info.duration_ms > 0 and abs(dur * 1000 - info.duration_ms) < 1500:
                dur_match = 1
            score = (dur_match, play_count)
            if score > best_score:
                best_score = score
                best = meta
        if best:
            info.index = best.get("index")
            info.artist = best.get("artist")
            info.title = best.get("title")
            info.play_count = best.get("play_count")
            # 标题优先于文件名
            name = best.get("title") or best.get("name")
            if name:
                info.track_name = name

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

    # ---------- 声音列表（GetSoundlist 扁平视图，带元数据） ----------
    def _refresh_cache(self) -> None:
        now = time.monotonic()
        if now - self._cache_ts < _CACHE_TTL:
            return
        # 1) 拉扁平列表（用于元数据 + 索引映射 + 兼容旧 UI）
        xml_text = self._cmd("GetSoundlist()")
        tracks = self._parse_soundlist(xml_text or "")
        # 同步元数据映射
        self._meta_map = {t.index: self._track_to_meta(t) for t in tracks if t.index is not None}
        # 2) 拉分类树（带声音，但不含图标）
        cat_xml = self._cmd(f"GetCategories({self._bool(True)}, {self._bool(False)})")
        categories = self._parse_categories(cat_xml or "")
        # 若分类树为空但有扁平列表，则用扁平列表生成一个"All sounds"虚拟分类
        if not categories and tracks:
            all_sounds = Category(index=0, name="所有声音", type=1, sounds=tracks)
            categories = [all_sounds]
        # 3) 构建按钮
        sounds = self._build_sounds(tracks, categories)
        self._cache_tracks, self._cache_sounds, self._cache_categories = tracks, sounds, categories
        self._cache_ts = now

    @staticmethod
    def _track_to_meta(t: Track) -> dict:
        return {
            "index": t.index,
            "name": t.name,
            "title": t.title,
            "artist": t.artist,
            "play_count": t.play_count or 0,
            "duration": t.duration,
            "duration_sec": SoundpadAdapter._parse_duration(t.duration),
        }

    @staticmethod
    def _parse_duration(text: Optional[str]) -> Optional[float]:
        """形如 '00:02' / '01:23' / '01:02:03' 的时长 → 秒。"""
        if not text:
            return None
        parts = text.split(":")
        try:
            nums = [int(p) for p in parts]
        except ValueError:
            return None
        if not nums:
            return None
        total = 0
        for n in nums:
            total = total * 60 + n
        return float(total)

    def get_tracks(self) -> list[Track]:
        self._refresh_cache()
        return self._cache_tracks

    def get_sounds(self) -> list[SoundButton]:
        self._refresh_cache()
        return self._cache_sounds

    def _build_sounds(
        self, tracks: list[Track], categories: list[Category]
    ) -> list[SoundButton]:
        """构建声音面板按钮：优先用户配置，否则按分类生成。"""
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
        # 未配置时：从分类树构建按钮（携带分类信息以便 UI 分组）
        buttons: list[SoundButton] = []
        for cat in categories:
            for pos, t in enumerate(cat.sounds, start=1):
                if t.index is None:
                    continue
                buttons.append(
                    SoundButton(
                        id=f"cat{cat.index}-{t.index}",
                        name=t.title or t.name,
                        kind="category_sound",
                        index=t.index,
                        category=cat.name,
                        category_index=cat.index,
                        position_in_category=pos,
                    )
                )
                if len(buttons) >= 500:
                    return buttons
        # 若分类树为空，回退到扁平列表
        if not buttons:
            for t in tracks[:500]:
                if t.index is None:
                    continue
                buttons.append(
                    SoundButton(
                        id=str(t.index), name=t.name, kind="index", index=t.index,
                        category=t.category,
                    )
                )
        return buttons

    def play_sound(self, sound: SoundButton) -> None:
        if sound.kind == "index" and sound.index is not None:
            self._cmd(f"DoPlaySound({sound.index})")
        elif sound.kind == "category_sound" and sound.category_index is not None and sound.position_in_category is not None:
            # DoPlaySoundFromCategory(categoryIndex, soundIndex, renderLine, captureLine)
            cmd = (
                f"DoPlaySoundFromCategory({sound.category_index}, "
                f"{sound.position_in_category}, {self._bool(True)}, {self._bool(False)})"
            )
            self._cmd(cmd)
        elif sound.kind == "hotkey" and sound.hotkey:
            send_keys(sound.hotkey)
        else:
            raise Unsupported

    # ---------- 分类树（GetCategories） ----------
    def get_categories(self) -> list[Category]:
        self._refresh_cache()
        return self._cache_categories

    def select_category(self, index: int) -> None:
        self._cmd(f"DoSelectCategory({int(index)})")
        self._current_category_index = int(index)

    def next_category(self) -> None:
        self._cmd("DoSelectNextCategory()")
        # 索引已变更但无法直接读取，强制刷新缓存
        self._cache_ts = 0.0

    def prev_category(self) -> None:
        self._cmd("DoSelectPreviousCategory()")
        self._cache_ts = 0.0

    def current_category(self) -> Optional[Category]:
        return None  # RC 协议未提供"查询当前分类"命令，仅维护本地状态

    def play_from_category(self, category_index: int, position_in_category: int) -> None:
        cmd = (
            f"DoPlaySoundFromCategory({int(category_index)}, "
            f"{int(position_in_category)}, {self._bool(True)}, {self._bool(False)})"
        )
        self._cmd(cmd)

    # ---------- 随机播放 ----------
    def play_random(self) -> None:
        self._cmd(f"DoPlayRandomSound({self._bool(True)}, {self._bool(False)})")

    def play_random_from_category(self, category_index: int) -> None:
        self._cmd(
            f"DoPlayRandomSoundFromCategory({int(category_index)}, "
            f"{self._bool(True)}, {self._bool(False)})"
        )

    # ---------- 进度跳转 ----------
    def seek_ms(self, position_ms: int) -> None:
        self._cmd(f"DoSeekMs({max(0, int(position_ms))})")

    def jump_ms(self, delta_ms: int) -> None:
        self._cmd(f"DoJumpMs({int(delta_ms)})")

    def play_current_again(self) -> None:
        self._cmd("DoPlayCurrentSoundAgain()")

    # ---------- XML 解析 ----------
    def _parse_soundlist(self, xml_text: str) -> list[Track]:
        """容错解析 GetSoundlist() 返回的 XML（扁平结构，无分类）。"""
        if not xml_text or xml_text.startswith("R-"):
            return []
        tracks: list[Track] = []
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return self._regex_soundlist(xml_text)
        # GetSoundlist 直接是 <Soundlist><Sound .../>...</Soundlist>
        for el in self._iter_sounds(root):
            tracks.append(self._sound_element_to_track(el, category=None))
        if not tracks:
            return self._regex_soundlist(xml_text)
        return tracks

    def _parse_categories(self, xml_text: str) -> list[Category]:
        """解析 GetCategories 返回的 XML 树（含嵌套 <Category>）。"""
        if not xml_text or xml_text.startswith("R-"):
            return []
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return []
        cats: list[Category] = []
        counter = [1]  # 全局 index 计数（仅用于未带 index 属性的回退情况）
        for el in root:
            if el.tag.lower().endswith("categories") or el.tag.lower() == "categories":
                # <Categories> 顶层容器
                for sub in el:
                    if self._is_category_tag(sub.tag):
                        cats.append(self._parse_category_element(sub, counter))
            elif self._is_category_tag(el.tag):
                cats.append(self._parse_category_element(el, counter))
        return cats

    def _parse_category_element(self, el, counter: list) -> Category:
        attrs = {k.lower(): v for k, v in (el.attrib or {}).items()}
        idx_attr = attrs.get("index")
        try:
            idx = int(idx_attr) if idx_attr is not None else counter[0]
        except ValueError:
            idx = counter[0]
        counter[0] += 1
        name = attrs.get("name") or attrs.get("title") or (el.text or "").strip() or "未命名分类"
        type_attr = attrs.get("type")
        try:
            cat_type = int(type_attr) if type_attr is not None else None
        except ValueError:
            cat_type = None
        hidden = attrs.get("hidden", "").lower() in ("true", "1", "yes")
        sounds: list[Track] = []
        subcats: list[Category] = []
        for child in el:
            tag = child.tag.lower()
            if self._is_category_tag(tag):
                subcats.append(self._parse_category_element(child, counter))
            elif tag == "sound" or (tag.endswith("sound") and "list" not in tag):
                sounds.append(self._sound_element_to_track(child, category=name, category_index=idx))
        # 给分类内声音补 position_in_category
        for pos, t in enumerate(sounds, start=1):
            t.position_in_category = pos
            t.category_index = idx
        return Category(
            index=idx, name=name, type=cat_type, hidden=hidden,
            sounds=sounds, subcategories=subcats,
        )

    def _sound_element_to_track(self, el, category: Optional[str], category_index: Optional[int] = None) -> Track:
        """将一个 <Sound> 元素转为 Track，兼容多种属性命名。"""
        attrs = {k.lower(): v for k, v in (el.attrib or {}).items()}
        name = attrs.get("name") or attrs.get("title")
        path = (
            attrs.get("path") or attrs.get("url")
            or attrs.get("file") or attrs.get("filename")
        )
        if not name and path:
            name = Path(path).stem
        if not name:
            # 兜底：取子节点里的 <name>/<title>
            for sub in el.iter():
                if sub.tag.lower() in ("name", "title"):
                    name = (sub.text or "").strip()
                    break
        if not name:
            name = "声音"
        idx_attr = attrs.get("index")
        try:
            idx = int(idx_attr) if idx_attr is not None else None
        except ValueError:
            idx = None
        # artist/title 在 GetCategories 的 Sound 上同样存在
        artist = attrs.get("artist")
        title = attrs.get("title")
        if not name and title:
            name = title
        duration = attrs.get("duration")
        play_count_attr = attrs.get("playcount") or attrs.get("play_count") or attrs.get("playCount")
        try:
            play_count = int(play_count_attr) if play_count_attr is not None else None
        except ValueError:
            play_count = None
        added_on = attrs.get("addedon") or attrs.get("added_on") or attrs.get("addedOn")
        last_played_on = attrs.get("lastplayedon") or attrs.get("last_played_on") or attrs.get("lastPlayedOn")
        tag = attrs.get("tag")
        # 显式传入的 category 覆盖 attrs（来自父级 <Category>）
        cat = category or attrs.get("category") or attrs.get("cat")
        return Track(
            index=idx, name=name or "声音", path=path or None,
            category=cat, artist=artist, title=title or name,
            duration=duration, play_count=play_count,
            added_on=added_on, last_played_on=last_played_on, tag=tag,
            category_index=category_index,
        )

    @staticmethod
    def _is_category_tag(tag: str) -> bool:
        t = (tag or "").lower()
        return t == "category" or t.endswith("category") and not t.endswith("soundlist")

    @staticmethod
    def _iter_sounds(root):
        """遍历 XML 树中所有 <Sound> 元素。"""
        for el in root.iter():
            tag = el.tag.lower()
            if tag == "sound" or (tag.endswith("sound") and "list" not in tag):
                yield el

    def _regex_soundlist(self, xml_text: str) -> list[Track]:
        entries = re.split(r"<(?:Sound|Entry)\b", xml_text, flags=re.IGNORECASE)[1:]
        tracks: list[Track] = []
        for i, chunk in enumerate(entries, start=1):
            name_m = re.search(r'name\s*=\s*"([^"]*)"', chunk, re.IGNORECASE)
            path_m = re.search(r'(?:path|url)\s*=\s*"([^"]*)"', chunk, re.IGNORECASE)
            artist_m = re.search(r'artist\s*=\s*"([^"]*)"', chunk, re.IGNORECASE)
            title_m = re.search(r'title\s*=\s*"([^"]*)"', chunk, re.IGNORECASE)
            dur_m = re.search(r'duration\s*=\s*"([^"]*)"', chunk, re.IGNORECASE)
            pc_m = re.search(r'playcount\s*=\s*"(\d+)"', chunk, re.IGNORECASE)
            name = (name_m.group(1) if name_m else "") or (title_m.group(1) if title_m else "")
            path = path_m.group(1) if path_m else ""
            if not name and path:
                name = Path(path).stem
            if name or path:
                tracks.append(
                    Track(
                        index=i, name=name or f"声音 {i}", path=path or None,
                        artist=artist_m.group(1) if artist_m else None,
                        title=title_m.group(1) if title_m else None,
                        duration=dur_m.group(1) if dur_m else None,
                        play_count=int(pc_m.group(1)) if pc_m else None,
                    )
                )
        return tracks
