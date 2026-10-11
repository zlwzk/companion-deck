"""CompanionDeck API 冒烟测试（使用桩适配器，不依赖真实 Soundpad）。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from deck.adapters.base import BaseAdapter
from deck.core.models import PlaybackInfo, SoundButton, Track
from deck.server import ServerApp

AUTH_TOKEN = "test-token-123"


class StubAdapter(BaseAdapter):
    name = "stub"
    display_name = "桩适配器"
    description = "测试用"
    capabilities = {"play_pause", "next", "prev", "stop", "volume", "tracks", "state", "sounds"}

    def __init__(self, config=None):
        super().__init__(config)
        self.calls = []
        self.volume = 42

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
        return PlaybackInfo(status="playing", position_ms=1000, duration_ms=10000)

    def get_tracks(self):
        return [Track(index=1, name="测试声音", path="C:\\sounds\\a.mp3")]

    def get_sounds(self):
        return [SoundButton(id="1", name="测试声音", kind="index", index=1)]

    def play_sound(self, sound):
        self.calls.append(("play_sound", sound.id))


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
    assert body["volume"] == 42
    assert len(body["adapters"]) == 2
    names = {a["name"] for a in body["adapters"]}
    assert names == {"stub", "offline"}


def test_transport_action(client):
    r = client.post("/api/transport/play_pause", headers=_auth())
    assert r.status_code == 200
    r = client.post("/api/transport/next", headers=_auth())
    assert r.status_code == 200
    r = client.post("/api/transport/nonexistent", headers=_auth())
    assert r.status_code in (400, 404, 405)


def test_offline_adapter_rejected_on_transport(client):
    client.post("/api/adapter", json={"adapter": "offline"}, headers=_auth())
    # 目标软件离线时，传输操作应返回 503 而非假装成功
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
