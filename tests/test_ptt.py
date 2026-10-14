"""PTT 自动按键模块与 /api/ptt 接口测试（不触发真实按键，全部 mock）。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from deck import ptt
from deck.adapters.base import BaseAdapter
from deck.core.models import SoundButton
from deck.ptt import PttController, clamp_ms, normalize_key, vk_code
from deck.server import ServerApp

AUTH_TOKEN = "test-token-123"


# ---------- normalize_key / vk_code ----------

@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("v", "V"),
        (" V ", "V"),
        ("5", "5"),
        ("f5", "F5"),
        ("F12", "F12"),
        ("space", "SPACE"),
        ("Enter", "ENTER"),
        ("capslock", "CAPSLOCK"),
        ("", None),
        ("   ", None),
        (";", None),
        ("AA", None),
        ("WIN", None),
        (None, None),
        (123, None),
    ],
)
def test_normalize_key(raw, expected):
    assert normalize_key(raw) == expected


def test_vk_code():
    assert vk_code("V") == ord("V")
    assert vk_code("5") == 0x35
    assert vk_code("SPACE") == 0x20
    assert vk_code("F1") == 0x70
    assert vk_code("F12") == 0x7B


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (150, 150),
        ("200", 200),
        (-5, 0),      # 夹到下限
        (9999, 500),  # 夹到上限
        (None, 150),  # 非法回退默认
        ("abc", 150),
    ],
)
def test_clamp_ms(raw, expected):
    assert clamp_ms(raw, 150, 0, 500) == expected


# ---------- PttController ----------

class Recorder:
    """替换 _down/_up，记录按键事件序列。"""

    def __init__(self, ctl: PttController, monkeypatch):
        self.events = []
        monkeypatch.setattr(ctl, "_down", lambda vk: self.events.append(("down", vk)))
        monkeypatch.setattr(ctl, "_up", lambda vk: self.events.append(("up", vk)))


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(ptt.time, "sleep", lambda s: None)


def _ctl(cfg, monkeypatch):
    ctl = PttController(lambda: cfg)
    rec = Recorder(ctl, monkeypatch)
    return ctl, rec


def test_disabled_does_nothing(monkeypatch):
    ctl, rec = _ctl({"enabled": False, "key": "V", "mode": "hold"}, monkeypatch)
    ctl.before_play()
    ctl.on_playback(True)
    assert rec.events == []


def test_hold_mode_press_and_release(monkeypatch, fake_timer):
    ctl, rec = _ctl({"enabled": True, "key": "V", "mode": "hold"}, monkeypatch)
    vk = ord("V")
    ctl.before_play()
    assert rec.events == [("down", vk)]
    # 已按住时重复触发不会再按
    ctl.before_play()
    assert rec.events == [("down", vk)]
    ctl.on_playback(False)  # 尾巴定时器到期后才松开
    assert rec.events == [("down", vk)]
    fake_timer.instances[-1].fn()
    assert rec.events == [("down", vk), ("up", vk)]
    # 幂等：再次松开无事件
    ctl.release()
    assert rec.events == [("down", vk), ("up", vk)]


def test_tap_mode_press_once(monkeypatch):
    ctl, rec = _ctl({"enabled": True, "key": "B", "mode": "tap"}, monkeypatch)
    vk = ord("B")
    ctl.before_play()
    assert rec.events == [("down", vk), ("up", vk)]
    assert ctl._holding is False


def test_dedup_blocks_immediate_retrigger(monkeypatch):
    ctl, rec = _ctl({"enabled": True, "key": "V", "mode": "tap"}, monkeypatch)
    ctl.before_play()
    ctl.before_play()  # 2 秒去重窗口内
    assert len(rec.events) == 2  # 只有一对 down/up
    ctl._last_trigger -= 3  # 模拟去重窗口已过
    ctl.before_play()
    assert len(rec.events) == 4


def test_on_playback_external_trigger(monkeypatch, fake_timer):
    """Soundpad 侧热键触发的播放，监控层补按。"""
    ctl, rec = _ctl({"enabled": True, "key": "V", "mode": "hold"}, monkeypatch)
    vk = ord("V")
    ctl.on_playback(True)
    assert rec.events == [("down", vk)]
    ctl.on_playback(False)
    fake_timer.instances[-1].fn()  # 尾巴到期才松开
    assert rec.events == [("down", vk), ("up", vk)]


def test_invalid_config_falls_back_to_defaults(monkeypatch):
    ctl, rec = _ctl({"enabled": True, "key": "@@", "mode": "weird"}, monkeypatch)
    ctl.before_play()
    # 键名回退默认 V，模式回退默认 hold
    assert rec.events == [("down", ord("V"))]
    ctl.release()


def test_shutdown_releases(monkeypatch):
    ctl, rec = _ctl({"enabled": True, "key": "V", "mode": "hold"}, monkeypatch)
    ctl.before_play()
    ctl.shutdown()
    assert rec.events == [("down", ord("V")), ("up", ord("V"))]


class FakeTimer:
    """替换 threading.Timer：只记录，不真正延时。"""

    instances: list = []

    def __init__(self, delay, fn):
        self.delay = delay
        self.fn = fn
        self.cancelled = False
        FakeTimer.instances.append(self)

    def start(self):
        pass

    def cancel(self):
        self.cancelled = True


@pytest.fixture()
def fake_timer(monkeypatch):
    FakeTimer.instances = []
    monkeypatch.setattr(ptt.threading, "Timer", FakeTimer)
    return FakeTimer


def test_tail_delays_release(monkeypatch, fake_timer):
    cfg = {"enabled": True, "key": "V", "mode": "hold", "tail_ms": 800}
    ctl, rec = _ctl(cfg, monkeypatch)
    vk = ord("V")
    ctl.before_play()
    ctl.on_playback(False)  # 播放停止：不立即松开，安排尾巴定时器
    assert rec.events == [("down", vk)]
    assert len(fake_timer.instances) == 1
    assert fake_timer.instances[0].delay == pytest.approx(0.8)
    fake_timer.instances[0].fn()  # 尾巴时间到
    assert rec.events == [("down", vk), ("up", vk)]


def test_new_play_cancels_tail(monkeypatch, fake_timer):
    """声音连播：尾巴定时器被取消，语音键全程不松。"""
    cfg = {"enabled": True, "key": "V", "mode": "hold", "tail_ms": 800}
    ctl, rec = _ctl(cfg, monkeypatch)
    vk = ord("V")
    ctl.before_play()
    ctl.on_playback(False)
    ctl.on_playback(True)  # 紧接着新播放（在去重窗口内也要取消尾巴）
    assert fake_timer.instances[0].cancelled is True
    assert rec.events == [("down", vk)]  # 没有松开，也没有重复按
    assert ctl.is_holding() is True


def test_release_cancels_tail(monkeypatch, fake_timer):
    cfg = {"enabled": True, "key": "V", "mode": "hold", "tail_ms": 800}
    ctl, rec = _ctl(cfg, monkeypatch)
    vk = ord("V")
    ctl.before_play()
    ctl.on_playback(False)
    ctl.release()  # 立即松开并取消尾巴
    assert fake_timer.instances[0].cancelled is True
    assert rec.events == [("down", vk), ("up", vk)]


def test_custom_lead_and_tap_used(monkeypatch):
    """可配的提前量/点按时长被正确使用。"""
    sleeps = []
    monkeypatch.setattr(ptt.time, "sleep", lambda s: sleeps.append(s))
    ctl, rec = _ctl(
        {"enabled": True, "key": "V", "mode": "tap", "tap_ms": 250, "lead_ms": 400},
        monkeypatch,
    )
    ctl.before_play()
    assert sleeps == [pytest.approx(0.25)]
    ctl2, _ = _ctl(
        {"enabled": True, "key": "V", "mode": "hold", "tap_ms": 250, "lead_ms": 400},
        monkeypatch,
    )
    ctl2.before_play()
    assert sleeps[-1] == pytest.approx(0.4)


def test_test_press_ignores_enabled(monkeypatch):
    """试按不受 enabled 开关限制，按住时长取 tap_ms 与 300ms 较大值。"""
    sleeps = []
    monkeypatch.setattr(ptt.time, "sleep", lambda s: sleeps.append(s))
    ctl, rec = _ctl({"enabled": False, "key": "G", "mode": "hold", "tap_ms": 60}, monkeypatch)
    key = ctl.test_press()
    assert key == "G"
    assert rec.events == [("down", ord("G")), ("up", ord("G"))]
    assert sleeps == [pytest.approx(0.3)]


# ---------- /api/ptt ----------

class StubAdapter(BaseAdapter):
    name = "stub"
    display_name = "桩适配器"
    description = "测试用"
    capabilities = {"sounds", "state"}

    def available(self):
        return True

    def get_sounds(self):
        return [SoundButton(id="1", name="测试声音", kind="index", index=1)]

    def play_sound(self, sound):
        pass


@pytest.fixture()
def server_app():
    cfg = {
        "auth": {"enabled": True, "token": AUTH_TOKEN},
        "active_adapter": "stub",
        "adapters": {"stub": {"enabled": True}},
    }
    return ServerApp(cfg, adapters_override=[StubAdapter])


@pytest.fixture()
def client(server_app):
    return TestClient(server_app.app)


def _auth():
    return {"Authorization": f"Bearer {AUTH_TOKEN}"}


def test_ptt_get_defaults(client):
    r = client.get("/api/ptt", headers=_auth())
    assert r.status_code == 200
    assert r.json() == {
        "enabled": False, "key": "V", "mode": "hold",
        "lead_ms": 150, "tap_ms": 60, "tail_ms": 500, "holding": False,
    }


def test_ptt_requires_auth(client):
    assert client.get("/api/ptt").status_code == 401


def test_ptt_post_updates_and_normalizes(server_app, client):
    r = client.post(
        "/api/ptt", headers=_auth(),
        json={"enabled": True, "key": "b", "mode": "tap"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is True and body["key"] == "B" and body["mode"] == "tap"
    assert server_app.cfg["ptt"] == {"enabled": True, "key": "B", "mode": "tap"}


def test_ptt_post_timing_params(server_app, client):
    r = client.post(
        "/api/ptt", headers=_auth(),
        json={"lead_ms": 0, "tap_ms": 500, "tail_ms": 1000},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["lead_ms"] == 0 and body["tap_ms"] == 500 and body["tail_ms"] == 1000
    assert server_app.cfg["ptt"]["tail_ms"] == 1000


@pytest.mark.parametrize(
    ("field", "value"),
    [("lead_ms", 501), ("lead_ms", -1), ("tap_ms", 501), ("tail_ms", 299), ("tail_ms", 1001)],
)
def test_ptt_post_timing_out_of_range(client, field, value):
    r = client.post("/api/ptt", headers=_auth(), json={field: value})
    assert r.status_code == 400
    assert "毫秒之间" in r.json()["detail"]


def test_ptt_test_endpoint(server_app, client, monkeypatch):
    calls = []
    monkeypatch.setattr(server_app.ptt, "test_press", lambda: calls.append("x") or "V")
    r = client.post("/api/ptt/test", headers=_auth())
    assert r.status_code == 200
    assert r.json() == {"ok": True, "key": "V"}
    assert calls == ["x"]


def test_state_exposes_ptt(server_app, client):
    r = client.get("/api/state", headers=_auth())
    assert r.status_code == 200
    body = r.json()
    assert body["ptt_enabled"] is False
    assert body["ptt_holding"] is False


def test_ptt_post_partial_update(server_app, client):
    r = client.post("/api/ptt", headers=_auth(), json={"enabled": True})
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is True
    assert body["key"] == "V"
    assert body["mode"] == "hold"


def test_ptt_post_invalid_key(client):
    r = client.post("/api/ptt", headers=_auth(), json={"key": "@@"})
    assert r.status_code == 400
    assert "无法识别的按键" in r.json()["detail"]


def test_ptt_post_invalid_mode(client):
    r = client.post("/api/ptt", headers=_auth(), json={"mode": "weird"})
    assert r.status_code == 400


def test_play_sound_triggers_before_play(server_app, client, monkeypatch):
    calls = []
    monkeypatch.setattr(server_app.ptt, "before_play", lambda: calls.append("before_play"))
    r = client.post("/api/sound/play", headers=_auth(), json={"id": "1"})
    assert r.status_code == 200
    assert calls == ["before_play"]


def test_disable_releases_key(server_app, client, monkeypatch):
    calls = []
    monkeypatch.setattr(server_app.ptt, "release", lambda: calls.append("release"))
    server_app.cfg["ptt"] = {"enabled": True, "key": "V", "mode": "hold"}
    r = client.post("/api/ptt", headers=_auth(), json={"enabled": False})
    assert r.status_code == 200
    assert calls == ["release"]
