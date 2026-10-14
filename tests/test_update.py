"""版本检查模块测试（全 mock，不访问网络）。"""

from __future__ import annotations

import io
import json

from deck import __version__, update


def _reset_cache():
    update._cache.update(at=0.0, latest=None, url=None, checked=False)


def _fake_resp(payload: dict):
    return io.BytesIO(json.dumps(payload).encode("utf-8"))


class FakeRespCM:
    def __init__(self, payload):
        self._buf = _fake_resp(payload)

    def __enter__(self):
        return self._buf

    def __exit__(self, *a):
        return False


class TestParseVer:
    def test_normal(self):
        assert update._parse_ver("v0.4.0") == (0, 4, 0)
        assert update._parse_ver("1.2.3") == (1, 2, 3)

    def test_fallback(self):
        assert update._parse_ver("") == (0,)
        assert update._parse_ver(None) == (0,)


class TestCheckLatest:
    def test_success_newer(self, monkeypatch):
        _reset_cache()
        monkeypatch.setattr(update, "__version__", "0.3.0")
        monkeypatch.setattr(
            update.urllib.request, "urlopen",
            lambda req, timeout=4.0: FakeRespCM({"tag_name": "v9.9.9", "html_url": "https://x"})
        )
        r = update.check_latest()
        assert r["checked"] is True
        assert r["latest"] == "9.9.9"
        assert r["update_available"] is True
        assert r["url"] == "https://x"

    def test_success_same_version(self, monkeypatch):
        _reset_cache()
        monkeypatch.setattr(update, "__version__", __version__)
        monkeypatch.setattr(
            update.urllib.request, "urlopen",
            lambda req, timeout=4.0: FakeRespCM({"tag_name": f"v{__version__}"})
        )
        r = update.check_latest()
        assert r["checked"] is True
        assert r["update_available"] is False

    def test_network_failure_degrades(self, monkeypatch):
        _reset_cache()

        def boom(req, timeout=4.0):
            raise OSError("offline")

        monkeypatch.setattr(update.urllib.request, "urlopen", boom)
        r = update.check_latest()
        assert r["checked"] is False
        assert r["latest"] is None
        assert r["update_available"] is False
        assert r["current"] == __version__

    def test_cache_reuse(self, monkeypatch):
        _reset_cache()
        calls = []

        def fake_urlopen(req, timeout=4.0):
            calls.append(1)
            return FakeRespCM({"tag_name": "v0.0.1"})

        monkeypatch.setattr(update.urllib.request, "urlopen", fake_urlopen)
        update.check_latest()
        update.check_latest()  # 第二次命中缓存，不再请求
        assert len(calls) == 1

    def test_force_bypasses_cache(self, monkeypatch):
        _reset_cache()
        calls = []

        def fake_urlopen(req, timeout=4.0):
            calls.append(1)
            return FakeRespCM({"tag_name": "v0.0.1"})

        monkeypatch.setattr(update.urllib.request, "urlopen", fake_urlopen)
        update.check_latest()
        update.check_latest(force=True)
        assert len(calls) == 2
