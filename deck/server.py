"""CompanionDeck FastAPI 服务：REST API + WebSocket 实时状态推送 + Web UI。"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from deck import __version__
from deck.adapters import BUILTIN_ADAPTERS
from deck.adapters.base import BaseAdapter, Unsupported
from deck.config import save as save_config
from deck.core.models import AdapterInfo, DeckState, PlaybackInfo, SoundButton
from deck.core.registry import AdapterRegistry
from deck.security import make_auth_dep
from deck.tray import is_supported as tray_supported

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


class CategorySelect(BaseModel):
    index: int


class PlayFromCategory(BaseModel):
    category_index: int
    position_in_category: int


class RandomFromCategory(BaseModel):
    category_index: int


class SeekPayload(BaseModel):
    position_ms: int


class JumpPayload(BaseModel):
    delta_ms: int


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

        if "categories" in active.capabilities:
            try:
                categories = active.get_categories()
                # 限制序列化大小：分类数与每分类声音数都做上限
                state.categories = self._prune_categories(categories)
                cur = active.current_category()
                if cur is not None:
                    state.current_category_index = cur.index
                    state.current_category_name = cur.name
            except Exception:  # noqa: BLE001
                pass

        try:
            state.profile = active.current_profile()
            state.profiles = active.profiles()
        except Exception:  # noqa: BLE001
            pass

        return state

    @staticmethod
    def _prune_categories(categories: list, max_per_cat: int = 200) -> list:
        """裁剪分类树用于 WebSocket 推送：限制每分类声音数，避免包过大。"""
        out = []
        for cat in categories:
            cat = cat.model_copy(update={"sounds": cat.sounds[:max_per_cat]}) if hasattr(cat, "model_copy") else cat
            out.append(cat)
        return out

    # ---------- 路由 ----------
    def _setup_routes(self) -> None:
        app = self.app
        auth = make_auth_dep(self._get_token)

        @app.get("/")
        def index() -> FileResponse:
            return FileResponse(WEB_DIR / "index.html")

        app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")

        @app.get("/manifest.json")
        def manifest() -> FileResponse:
            return FileResponse(WEB_DIR / "manifest.json", media_type="application/manifest+json")

        @app.get("/sw.js")
        def service_worker() -> Response:
            return Response(
                (WEB_DIR / "sw.js").read_text(encoding="utf-8"),
                media_type="text/javascript",
            )

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

        @app.get("/api/categories")
        def api_categories(_=Depends(auth)) -> list[dict]:
            active = self.registry.active
            if active is None or "categories" not in active.capabilities:
                raise HTTPException(status_code=400, detail="当前适配器不支持分类")
            try:
                cats = active.get_categories()
            except Unsupported:
                raise HTTPException(status_code=400, detail="不支持分类")
            except Exception:  # noqa: BLE001
                raise HTTPException(status_code=502, detail="读取分类失败")
            return [c.model_dump() for c in cats]

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

        # ---------- 分类操作 ----------
        @app.post("/api/category/select")
        def api_category_select(payload: CategorySelect, _=Depends(auth)) -> dict:
            active = self.registry.active
            if active is None or "categories" not in active.capabilities:
                raise HTTPException(status_code=400, detail="当前适配器不支持分类")
            try:
                active.select_category(payload.index)
            except Unsupported:
                raise HTTPException(status_code=400, detail="不支持分类切换")
            except Exception:  # noqa: BLE001
                raise HTTPException(status_code=502, detail="切换分类失败")
            return self._state().model_dump()

        @app.post("/api/category/next")
        def api_category_next(_=Depends(auth)) -> dict:
            active = self.registry.active
            if active is None or "categories" not in active.capabilities:
                raise HTTPException(status_code=400, detail="当前适配器不支持分类")
            try:
                active.next_category()
            except Unsupported:
                raise HTTPException(status_code=400, detail="不支持分类切换")
            except Exception:  # noqa: BLE001
                raise HTTPException(status_code=502, detail="切换分类失败")
            return self._state().model_dump()

        @app.post("/api/category/prev")
        def api_category_prev(_=Depends(auth)) -> dict:
            active = self.registry.active
            if active is None or "categories" not in active.capabilities:
                raise HTTPException(status_code=400, detail="当前适配器不支持分类")
            try:
                active.prev_category()
            except Unsupported:
                raise HTTPException(status_code=400, detail="不支持分类切换")
            except Exception:  # noqa: BLE001
                raise HTTPException(status_code=502, detail="切换分类失败")
            return self._state().model_dump()

        @app.post("/api/sound/play-from-category")
        def api_play_from_category(payload: PlayFromCategory, _=Depends(auth)) -> dict:
            active = self.registry.active
            if active is None or "categories" not in active.capabilities:
                raise HTTPException(status_code=400, detail="当前适配器不支持分类")
            try:
                active.play_from_category(payload.category_index, payload.position_in_category)
            except Unsupported:
                raise HTTPException(status_code=400, detail="不支持按分类播放")
            except Exception:  # noqa: BLE001
                raise HTTPException(status_code=502, detail="播放失败")
            return {"ok": True}

        # ---------- 随机播放 ----------
        @app.post("/api/sound/random")
        def api_random(_=Depends(auth)) -> dict:
            active = self.registry.active
            if active is None or "random" not in active.capabilities:
                raise HTTPException(status_code=400, detail="当前适配器不支持随机播放")
            try:
                active.play_random()
            except Unsupported:
                raise HTTPException(status_code=400, detail="不支持随机播放")
            except Exception:  # noqa: BLE001
                raise HTTPException(status_code=502, detail="随机播放失败")
            return {"ok": True}

        @app.post("/api/sound/random-from-category")
        def api_random_from_category(payload: RandomFromCategory, _=Depends(auth)) -> dict:
            active = self.registry.active
            if active is None or "random" not in active.capabilities:
                raise HTTPException(status_code=400, detail="当前适配器不支持随机播放")
            try:
                active.play_random_from_category(payload.category_index)
            except Unsupported:
                raise HTTPException(status_code=400, detail="不支持分类内随机播放")
            except Exception:  # noqa: BLE001
                raise HTTPException(status_code=502, detail="随机播放失败")
            return {"ok": True}

        # ---------- 进度跳转 ----------
        @app.post("/api/seek")
        def api_seek(payload: SeekPayload, _=Depends(auth)) -> dict:
            active = self.registry.active
            if active is None or "seek" not in active.capabilities:
                raise HTTPException(status_code=400, detail="当前适配器不支持进度跳转")
            try:
                active.seek_ms(payload.position_ms)
            except Unsupported:
                raise HTTPException(status_code=400, detail="不支持进度跳转")
            except Exception:  # noqa: BLE001
                raise HTTPException(status_code=502, detail="跳转失败")
            return {"ok": True}

        @app.post("/api/jump")
        def api_jump(payload: JumpPayload, _=Depends(auth)) -> dict:
            active = self.registry.active
            if active is None or "seek" not in active.capabilities:
                raise HTTPException(status_code=400, detail="当前适配器不支持进度跳转")
            try:
                active.jump_ms(payload.delta_ms)
            except Unsupported:
                raise HTTPException(status_code=400, detail="不支持进度跳转")
            except Exception:  # noqa: BLE001
                raise HTTPException(status_code=502, detail="跳转失败")
            return {"ok": True}

        @app.post("/api/play-current-again")
        def api_play_current_again(_=Depends(auth)) -> dict:
            active = self.registry.active
            if active is None or "seek" not in active.capabilities:
                raise HTTPException(status_code=400, detail="当前适配器不支持此操作")
            try:
                active.play_current_again()
            except Unsupported:
                raise HTTPException(status_code=400, detail="不支持重新播放")
            except Exception:  # noqa: BLE001
                raise HTTPException(status_code=502, detail="重新播放失败")
            return {"ok": True}

        @app.get("/api/qr")
        def api_qr(url: str = "", _=Depends(auth)) -> Response:
            """为给定 URL 生成 SVG QR 码（依赖 qrcode 库）。"""
            target = url or self._lan_url()
            if not target:
                raise HTTPException(status_code=400, detail="无可用的局域网地址")
            from deck.qrcode import is_available, to_svg

            if not is_available():
                raise HTTPException(status_code=502, detail="二维码库未安装（pip install qrcode）")
            try:
                svg = to_svg(target)
            except Exception:  # noqa: BLE001
                raise HTTPException(status_code=502, detail="二维码生成失败")
            return Response(svg, media_type="image/svg+xml")

        @app.get("/api/tray-supported")
        def api_tray_supported() -> dict:
            return {"supported": tray_supported()}

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

    def _lan_url(self) -> Optional[str]:
        """返回首选局域网访问 URL（端口取配置）。"""
        try:
            from deck.lan import lan_ips, hotspot_ips

            port = int((self.cfg.get("server") or {}).get("port") or 8390)
            for ip in lan_ips() + hotspot_ips():
                if ip:
                    return f"http://{ip}:{port}"
        except Exception:  # noqa: BLE001
            pass
        return None
