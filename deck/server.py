"""CompanionDeck FastAPI 服务：REST API + WebSocket 实时状态推送 + Web UI。"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from deck import __version__
from deck.adapters import BUILTIN_ADAPTERS
from deck.adapters.base import BaseAdapter, Unsupported
from deck.config import save as save_config
from deck.core.models import AdapterInfo, DeckState, PlaybackInfo, SoundButton
from deck.core.registry import AdapterRegistry
from deck.security import make_auth_dep

logger = logging.getLogger("companiondeck")

WEB_DIR = Path(__file__).resolve().parent / "web"


class AdapterSwitch(BaseModel):
    adapter: str


class VolumeSet(BaseModel):
    volume: int


class ProfileSwitch(BaseModel):
    profile: str


class SoundPlay(BaseModel):
    id: str


class ServerApp:
    def __init__(
        self,
        cfg: dict,
        adapters_override: list[type[BaseAdapter]] | None = None,
        config_path: Path | str | None = None,
    ) -> None:
        """config_path 为 None 时不做配置持久化（用于测试）。"""
        self.cfg = cfg
        self.config_path = config_path
        self.registry = AdapterRegistry()

        classes = adapters_override if adapters_override is not None else BUILTIN_ADAPTERS
        for cls in classes:
            adapter_cfg = (cfg.get("adapters") or {}).get(cls.name, {})
            if adapter_cfg.get("enabled", True):
                try:
                    self.registry.register(cls(adapter_cfg))
                except Exception:  # noqa: BLE001 适配器初始化失败不应拖垮整个服务
                    logger.exception("适配器 %s 初始化失败", cls.name)

        self._activate_initial()

        self.app = FastAPI(title="CompanionDeck", version=__version__)
        self._setup_routes()

    # ---------- 初始化 ----------
    def _activate_initial(self) -> None:
        preferred = self.cfg.get("active_adapter") or "soundpad"
        if preferred in self.registry._adapters:
            self.registry.activate(preferred)
        elif self.registry._adapters:
            first = next(iter(self.registry._adapters))
            self.registry.activate(first)

    def _get_token(self) -> Optional[str]:
        auth = self.cfg.get("auth") or {}
        if auth.get("enabled"):
            return auth.get("token")
        return None

    def _persist(self) -> None:
        if self.config_path is not None:
            save_config(self.cfg, self.config_path)

    # ---------- 状态聚合 ----------
    def _state(self) -> DeckState:
        state = DeckState(
            version=__version__,
            auth_enabled=bool(self._get_token()),
        )
        for adapter in self.registry.all():
            try:
                available = adapter.available()
            except Exception:  # noqa: BLE001
                available = False
            state.adapters.append(
                AdapterInfo(
                    name=adapter.name,
                    display_name=adapter.display_name,
                    description=adapter.description,
                    available=available,
                    capabilities=sorted(adapter.capabilities),
                    actions=adapter.enabled_actions(),
                )
            )

        active = self.registry.active
        if active is None:
            return state
        state.adapter = active.name
        state.adapter_display = active.display_name
        try:
            state.adapter_available = active.available()
        except Exception:  # noqa: BLE001
            state.adapter_available = False

        try:
            state.playback = active.get_playback()
        except Exception:  # noqa: BLE001
            state.playback = PlaybackInfo()

        if "volume" in active.capabilities:
            try:
                state.volume = active.get_volume()
                state.muted = active.get_muted()
            except Exception:  # noqa: BLE001
                pass

        if "sounds" in active.capabilities:
            try:
                sounds = active.get_sounds()
                if len(sounds) <= 500:
                    state.sounds = sounds
            except Exception:  # noqa: BLE001
                pass

        try:
            state.profile = active.current_profile()
            state.profiles = active.profiles()
        except Exception:  # noqa: BLE001
            pass

        return state

    # ---------- 路由 ----------
    def _setup_routes(self) -> None:
        app = self.app
        auth = make_auth_dep(self._get_token)

        @app.get("/")
        def index() -> FileResponse:
            return FileResponse(WEB_DIR / "index.html")

        app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")

        @app.get("/api/state")
        def api_state(_=Depends(auth)) -> dict:
            return self._state().model_dump()

        @app.get("/api/tracks")
        def api_tracks(_=Depends(auth)) -> list[dict]:
            active = self.registry.active
            if active is None:
                return []
            try:
                tracks = active.get_tracks()
            except Unsupported:
                raise HTTPException(status_code=400, detail="该适配器不支持声音列表")
            except Exception:  # noqa: BLE001
                raise HTTPException(status_code=502, detail="读取声音列表失败")
            return [t.model_dump() for t in tracks]

        @app.post("/api/adapter")
        def api_adapter(payload: AdapterSwitch, _=Depends(auth)) -> dict:
            try:
                self.registry.activate(payload.adapter)
            except KeyError:
                raise HTTPException(status_code=404, detail="适配器不存在")
            self.cfg["active_adapter"] = payload.adapter
            self._persist()
            return self._state().model_dump()

        @app.post("/api/transport/{action}")
        def api_transport(action: str, _=Depends(auth)) -> dict:
            active = self.registry.active
            if active is None:
                raise HTTPException(status_code=503, detail="没有可用适配器")
            try:
                if not active.available():
                    raise HTTPException(status_code=503, detail="目标软件未运行（离线）")
            except HTTPException:
                raise
            except Exception:  # noqa: BLE001
                raise HTTPException(status_code=503, detail="目标软件不可用")
            fn = getattr(active, action, None)
            if fn is None or action not in active.enabled_actions():
                raise HTTPException(status_code=400, detail=f"操作 {action} 不可用")
            try:
                fn()
            except Unsupported:
                raise HTTPException(status_code=400, detail=f"操作 {action} 不受支持")
            except Exception:  # noqa: BLE001
                logger.exception("执行 %s 失败", action)
                raise HTTPException(status_code=502, detail="执行失败（目标软件可能未运行）")
            return {"ok": True}

        @app.post("/api/volume")
        def api_volume(payload: VolumeSet, _=Depends(auth)) -> dict:
            active = self.registry.active
            if active is None or "volume" not in active.capabilities:
                raise HTTPException(status_code=400, detail="当前适配器不支持音量")
            try:
                active.set_volume(payload.volume)
            except Unsupported:
                raise HTTPException(status_code=400, detail="不支持音量调节")
            except Exception:  # noqa: BLE001
                raise HTTPException(status_code=502, detail="音量调节失败")
            return {"ok": True}

        @app.post("/api/profile")
        def api_profile(payload: ProfileSwitch, _=Depends(auth)) -> dict:
            active = self.registry.active
            if active is None:
                raise HTTPException(status_code=503, detail="没有可用适配器")
            try:
                active.switch_profile(payload.profile)
            except Unsupported:
                raise HTTPException(status_code=400, detail="当前适配器不支持热键方案")
            if payload.profile in active.profiles():
                self.cfg.setdefault("adapters", {}).setdefault("profile", {})[
                    "active_profile"
                ] = payload.profile
                self._persist()
            return self._state().model_dump()

        @app.post("/api/sound/play")
        def api_sound_play(payload: SoundPlay, _=Depends(auth)) -> dict:
            active = self.registry.active
            if active is None:
                raise HTTPException(status_code=503, detail="没有可用适配器")
            try:
                sounds = active.get_sounds()
            except Exception:  # noqa: BLE001
                sounds = []
            sound = next((s for s in sounds if s.id == payload.id), None)
            if sound is None:
                raise HTTPException(status_code=404, detail="声音不存在")
            try:
                active.play_sound(sound)
            except Unsupported:
                raise HTTPException(status_code=400, detail="该声音无法播放")
            except Exception:  # noqa: BLE001
                raise HTTPException(status_code=502, detail="播放失败")
            return {"ok": True}

        @app.websocket("/ws")
        async def ws_endpoint(websocket: WebSocket) -> None:
            expected = self._get_token()
            if expected is not None:
                import hmac

                provided = websocket.query_params.get("token")
                if not provided or not hmac.compare_digest(provided, expected):
                    await websocket.close(code=4401)
                    return
            await websocket.accept()
            loop = asyncio.get_running_loop()
            try:
                while True:
                    await asyncio.sleep(1.5)
                    state = await loop.run_in_executor(None, self._state)
                    await websocket.send_json(state.model_dump())
            except WebSocketDisconnect:
                pass
            except Exception:  # noqa: BLE001
                logger.debug("WebSocket 连接结束", exc_info=True)
