"""CompanionDeck API 冒烟测试（使用桩适配器，不依赖真实 Soundpad）。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from deck.adapters.base import BaseAdapter, Unsupported
from deck.core.models import Category, PlaybackInfo, SoundButton, Track
from deck.server import ServerApp

AUTH_TOKEN = "test-token-123"


class StubAdapter(BaseAdapter):
    name = "stub"
    display_name = "桩适配器"
    description = "测试用"
    capabilities = {
        "play_pause", "next", "prev", "stop", "volume",
        "tracks", "state", "sounds",
        "categories", "random", "seek",
    }

    def __init__(self, config=None):
        super().__init__(config)
        self.calls = []
        self.volume = 42
        self._selected_category = 1

    def available(self):
        return True

    def play_pause(self):
        self.calls.append("play_pause")

    def next(self):
        self.calls.append("next")

    def set_volume(self, volume):
        self.volume = volume
        self.calls.append(("volume", volume))

    def get_volume(self):
        return self.volume

    def get_muted(self):
        return False

    def get_playback(self):
        return PlaybackInfo(
            status="playing", position_ms=1000, duration_ms=10000,
            track_name="测试曲目", artist="测试艺术家", title="测试曲目",
            play_count=3, index=1,
        )

    def get_tracks(self):
        return [Track(index=1, name="测试声音", path="C:\\sounds\\a.mp3", category="默认")]

    def get_sounds(self):
        return [
            SoundButton(id="1", name="测试声音", kind="category_sound",
                        index=1, category="默认", category_index=1,
                        position_in_category=1)
        ]

    def play_sound(self, sound):
        self.calls.append(("play_sound", sound.id))

    # 分类
    def get_categories(self):
        return [
            Category(index=0, name="All sounds", type=1, hidden=True,
                     sounds=[Track(index=1, name="测试声音")]),
            Category(index=1, name="默认", type=0,
                     sounds=[Track(index=1, name="测试声音", title="测试声音")]),
        ]

    def select_category(self, index):
        self._selected_category = index
        self.calls.append(("select_category", index))

    def next_category(self):
        self.calls.append("next_category")

    def prev_category(self):
        self.calls.append("prev_category")

    def play_from_category(self, category_index, position_in_category):
        self.calls.append(("play_from_category", category_index, position_in_category))

    # 随机
    def play_random(self):
        self.calls.append("play_random")

    def play_random_from_category(self, category_index):
        self.calls.append(("play_random_from_category", category_index))

    # 跳转
    def seek_ms(self, position_ms):
        self.calls.append(("seek_ms", position_ms))

    def jump_ms(self, delta_ms):
        self.calls.append(("jump_ms", delta_ms))

    def play_current_again(self):
        self.calls.append("play_current_again")


class OfflineAdapter(BaseAdapter):
    name = "offline"
    display_name = "离线桩"
    description = "始终离线"
    capabilities = {"play_pause"}

    def available(self):
        return False

    def play_pause(self):
        raise AssertionError("离线适配器不应被调用")


@pytest.fixture()
def cfg():
    return {
        "auth": {"enabled": True, "token": AUTH_TOKEN},
        "active_adapter": "stub",
        "adapters": {"stub": {"enabled": True}, "offline": {"enabled": True}},
    }


@pytest.fixture()
def client(cfg):
    app = ServerApp(cfg, adapters_override=[StubAdapter, OfflineAdapter]).app
    return TestClient(app)


def _auth():
    return {"Authorization": f"Bearer {AUTH_TOKEN}"}


def test_index_served(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "CompanionDeck" in r.text


def test_state_requires_auth(client):
    r = client.get("/api/state")
    assert r.status_code == 401
    r = client.get("/api/state", params={"token": AUTH_TOKEN})
    assert r.status_code == 200


def test_state_shape(client):
    r = client.get("/api/state", headers=_auth())
    assert r.status_code == 200
    body = r.json()
    assert body["adapter"] == "stub"
    assert body["adapter_available"] is True
    assert body["playback"]["status"] == "playing"
    assert body["playback"]["artist"] == "测试艺术家"
    assert body["playback"]["index"] == 1
    assert body["volume"] == 42
    assert len(body["adapters"]) == 2
    names = {a["name"] for a in body["adapters"]}
    assert names == {"stub", "offline"}
    # 分类树
    assert len(body["categories"]) == 2
    assert body["categories"][1]["name"] == "默认"


def test_transport_action(client):
    r = client.post("/api/transport/play_pause", headers=_auth())
    assert r.status_code == 200
    r = client.post("/api/transport/next", headers=_auth())
    assert r.status_code == 200
    r = client.post("/api/transport/nonexistent", headers=_auth())
    assert r.status_code in (400, 404, 405)


def test_offline_adapter_rejected_on_transport(client):
    client.post("/api/adapter", json={"adapter": "offline"}, headers=_auth())
    r = client.post("/api/transport/play_pause", headers=_auth())
    assert r.status_code == 503


def test_volume(client):
    r = client.post("/api/volume", json={"volume": 66}, headers=_auth())
    assert r.status_code == 200
    body = client.get("/api/state", headers=_auth()).json()
    assert body["volume"] == 66


def test_sound_play(client):
    r = client.post("/api/sound/play", json={"id": "1"}, headers=_auth())
    assert r.status_code == 200
    r = client.post("/api/sound/play", json={"id": "missing"}, headers=_auth())
    assert r.status_code == 404


def test_tracks(client):
    r = client.get("/api/tracks", headers=_auth())
    assert r.status_code == 200
    assert r.json()[0]["name"] == "测试声音"


def test_adapter_switch(client):
    r = client.post("/api/adapter", json={"adapter": "offline"}, headers=_auth())
    assert r.status_code == 200
    assert r.json()["adapter"] == "offline"
    r = client.post("/api/adapter", json={"adapter": "nope"}, headers=_auth())
    assert r.status_code == 404


def test_websocket_push(client):
    with client.websocket_connect("/ws?token=" + AUTH_TOKEN) as ws:
        data = ws.receive_json()
        assert data["adapter"] == "stub"
        assert data["playback"]["status"] == "playing"
        assert "version" in data


def test_websocket_rejects_bad_token(client):
    with pytest.raises(Exception):
        with client.websocket_connect("/ws?token=wrong"):
            ws = None  # pragma: no cover
            assert ws is None


# ---------- 新接口 ----------

def test_categories_endpoint(client):
    r = client.get("/api/categories", headers=_auth())
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 2
    assert body[0]["name"] == "All sounds"


def test_category_select(client):
    r = client.post("/api/category/select", json={"index": 1}, headers=_auth())
    assert r.status_code == 200
    body = r.json()
    assert body["adapter"] == "stub"


def test_category_next_prev(client):
    r = client.post("/api/category/next", headers=_auth())
    assert r.status_code == 200
    r = client.post("/api/category/prev", headers=_auth())
    assert r.status_code == 200


def test_play_from_category(client):
    r = client.post(
        "/api/sound/play-from-category",
        json={"category_index": 1, "position_in_category": 1},
        headers=_auth(),
    )
    assert r.status_code == 200


def test_random(client):
    r = client.post("/api/sound/random", headers=_auth())
    assert r.status_code == 200
    r = client.post(
        "/api/sound/random-from-category",
        json={"category_index": 1},
        headers=_auth(),
    )
    assert r.status_code == 200


def test_seek_and_jump(client):
    r = client.post("/api/seek", json={"position_ms": 5000}, headers=_auth())
    assert r.status_code == 200
    r = client.post("/api/jump", json={"delta_ms": -2000}, headers=_auth())
    assert r.status_code == 200
    r = client.post("/api/play-current-again", headers=_auth())
    assert r.status_code == 200


def test_qr_endpoint(client):
    r = client.get("/api/qr", params={"url": "http://example.com:8390"}, headers=_auth())
    # 如果没有安装 qrcode 库，会返回 502；安装了会返回 SVG
    assert r.status_code in (200, 502)


def test_manifest_and_sw(client):
    r = client.get("/manifest.json")
    assert r.status_code == 200
    r = client.get("/sw.js")
    assert r.status_code == 200
