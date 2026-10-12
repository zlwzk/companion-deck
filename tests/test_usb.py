"""adb 桥接模块单元测试（全部 mock，不依赖真实 adb）。"""

from __future__ import annotations

import subprocess
from types import SimpleNamespace

import pytest

from deck import adb


@pytest.fixture()
def fake_adb(monkeypatch):
    """伪造 adb 可执行文件存在。"""
    monkeypatch.setattr(adb, "adb_path", lambda: "C:/fake/adb.exe")


def _ok(stdout: str = "", stderr: str = "") -> SimpleNamespace:
    return SimpleNamespace(returncode=0, stdout=stdout, stderr=stderr)


def _fail(stderr: str = "boom") -> SimpleNamespace:
    return SimpleNamespace(returncode=1, stdout="", stderr=stderr)


def test_adb_missing(monkeypatch):
    monkeypatch.setattr(adb, "adb_path", lambda: None)
    ok, msg = adb.reverse(8390)
    assert not ok
    assert "platform-tools" in msg


def test_no_device(fake_adb, monkeypatch):
    monkeypatch.setattr(adb, "devices", lambda: [])
    ok, msg = adb.reverse(8390)
    assert not ok
    assert "USB 调试" in msg


def test_reverse_success(fake_adb, monkeypatch):
    monkeypatch.setattr(adb, "devices", lambda: ["SER1"])

    captured = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        return _ok()

    monkeypatch.setattr(adb, "_run", fake_run)
    ok, msg = adb.reverse(8390)
    assert ok
    assert "127.0.0.1:8390" in msg
    # 必须带上 -s 序列号，避免多设备场景错乱
    assert captured["args"][:4] == ["C:/fake/adb.exe", "-s", "SER1", "reverse"]
    assert "tcp:8390" in captured["args"][4]
    assert captured["args"][5] == f"tcp:8390"


def test_reverse_multi_device(fake_adb, monkeypatch):
    monkeypatch.setattr(adb, "devices", lambda: ["A", "B"])

    calls: list[list[str]] = []

    def fake_run(args, **kwargs):
        calls.append(args)
        return _ok()

    monkeypatch.setattr(adb, "_run", fake_run)
    ok, msg = adb.reverse(8390)
    assert ok
    assert len(calls) == 2
    assert "2 台" in msg


def test_reverse_failure(fake_adb, monkeypatch):
    monkeypatch.setattr(adb, "devices", lambda: ["SER1"])
    monkeypatch.setattr(adb, "_run", lambda args, **kw: _fail("error: closed"))
    ok, msg = adb.reverse(8390)
    assert not ok
    assert "error: closed" in msg


def test_devices_parse_states(fake_adb, monkeypatch):
    """只统计 state=device 的行，offline/unauthorized 被排除。"""
    stdout = (
        "List of devices attached\n"
        "SER1\tdevice usb:1-1 product:x model:y\n"
        "SER2\toffline\n"
        "SER3\tunauthorized\n"
        "\n"
    )
    monkeypatch.setattr(adb, "_run", lambda args, **kw: _ok(stdout=stdout))
    assert adb.devices() == ["SER1"]


def test_run_uses_no_window_flag(fake_adb, monkeypatch):
    """确保 _run 调用 subprocess.run 且传入隐藏窗口标志（Windows）。"""
    called = {}

    def fake_sr(args, **kwargs):
        called.update(kwargs)
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(adb.subprocess, "run", fake_sr)
    adb._run(["adb", "devices"])
    assert "creationflags" in called
