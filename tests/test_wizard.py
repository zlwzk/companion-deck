"""连接向导与 adb 增强功能测试（全 mock，不依赖真实设备）。"""

from __future__ import annotations

import builtins
from types import SimpleNamespace

import pytest

from deck import adb, wizard


# ---------- 菜单选项解析 ----------

class TestParseChoice:
    def test_usb(self):
        assert wizard.parse_choice("1") == "usb"
        assert wizard.parse_choice(" usb ") == "usb"
        assert wizard.parse_choice("U") == "usb"

    def test_hotspot(self):
        assert wizard.parse_choice("2") == "电脑热点"
        assert wizard.parse_choice("热点") == "电脑热点"

    def test_lan(self):
        assert wizard.parse_choice("3") == "局域网"
        assert wizard.parse_choice("WIFI") == "局域网"

    def test_smart_default(self):
        assert wizard.parse_choice("") is None
        assert wizard.parse_choice("  ") is None

    def test_invalid(self):
        assert wizard.parse_choice("abc") is None
        assert wizard.parse_choice("9") is None


# ---------- adb 设备状态解析 ----------

def _fake_run(stdout: str):
    return SimpleNamespace(stdout=stdout, stderr="", returncode=0)


class TestDevicesStatus:
    def test_all_states(self, monkeypatch):
        monkeypatch.setattr(adb, "adb_path", lambda: "adb")
        monkeypatch.setattr(
            adb, "_run",
            lambda args, timeout=8.0: _fake_run(
                "List of devices attached\nS1\tdevice\nS2\tunauthorized\nS3\toffline\n\n")
        )
        assert adb.devices_status() == [("S1", "device"), ("S2", "unauthorized"), ("S3", "offline")]

    def test_only_authorized_listed(self, monkeypatch):
        monkeypatch.setattr(adb, "adb_path", lambda: "adb")
        monkeypatch.setattr(
            adb, "_run",
            lambda args, timeout=8.0: _fake_run("S1\tdevice\nS2\tunauthorized\n")
        )
        assert adb.devices() == ["S1"]

    def test_no_adb(self, monkeypatch):
        monkeypatch.setattr(adb, "adb_path", lambda: None)
        assert adb.devices_status() == []


# ---------- adb 自动安装 ----------

class TestInstallAdb:
    def test_failure_degrades(self, monkeypatch, tmp_path):
        monkeypatch.setattr(adb, "_install_root", lambda: tmp_path)
        monkeypatch.setattr(adb, "PLATFORM_TOOLS_URL", adb.PLATFORM_TOOLS_URL)

        def boom(*a, **k):
            raise OSError("network down")

        monkeypatch.setattr(adb.urllib.request, "urlopen", boom)
        ok, msg = adb.install_adb()
        assert ok is False
        assert "失败" in msg

    def test_success_extracts(self, monkeypatch, tmp_path):
        import zipfile
        monkeypatch.setattr(adb, "_install_root", lambda: tmp_path)
        # 预先构造一个合法的 platform-tools zip（内含 platform-tools/adb.exe）
        zip_src = tmp_path / "src.zip"
        with zipfile.ZipFile(zip_src, "w") as zf:
            zf.writestr("platform-tools/adb.exe", b"fake adb")
        monkeypatch.setattr(adb, "PLATFORM_TOOLS_URL", zip_src.as_uri())

        chunks = iter([zip_src.read_bytes()])

        class FakeResp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self, n=-1):
                try:
                    return next(chunks)
                except StopIteration:
                    return b""

        monkeypatch.setattr(adb.urllib.request, "urlopen", lambda url, timeout=30: FakeResp())
        ok, msg = adb.install_adb()
        assert ok is True
        assert (tmp_path / "platform-tools" / "adb.exe").is_file()
        assert known_install_ok(tmp_path)

    def test_known_install(self, monkeypatch, tmp_path):
        monkeypatch.setattr(adb, "_install_root", lambda: tmp_path)
        assert adb.known_install() is None
        (tmp_path / "platform-tools").mkdir(parents=True)
        (tmp_path / "platform-tools" / "adb.exe").write_text("x")
        assert adb.known_install() == str(tmp_path / "platform-tools" / "adb.exe")


def known_install_ok(root) -> bool:
    return adb.known_install() is not None


# ---------- USB 分步向导 ----------

class TestUsbWizard:
    def test_non_interactive_no_adb(self, monkeypatch):
        monkeypatch.setattr(adb, "adb_path", lambda: None)
        ok, msg = wizard.run_usb_wizard(8390, interactive=False)
        assert ok is False
        assert "adb" in msg

    def test_non_interactive_no_device(self, monkeypatch):
        monkeypatch.setattr(adb, "adb_path", lambda: "adb")
        monkeypatch.setattr(adb, "devices_status", lambda: [])
        ok, msg = wizard.run_usb_wizard(8390, interactive=False)
        assert ok is False

    def test_success_with_device(self, monkeypatch):
        monkeypatch.setattr(adb, "adb_path", lambda: "adb")
        monkeypatch.setattr(adb, "devices_status", lambda: [("S1", "device")])
        calls = []

        def fake_reverse(port):
            calls.append(port)
            return True, "已桥接"

        monkeypatch.setattr(adb, "reverse", fake_reverse)
        ok, msg = wizard.run_usb_wizard(8390, interactive=True)
        assert ok is True
        assert calls == [8390]

    def test_unauthorized_retry_then_success(self, monkeypatch):
        monkeypatch.setattr(adb, "adb_path", lambda: "adb")
        states = iter([[("S1", "unauthorized")], [("S1", "device")]])
        monkeypatch.setattr(adb, "devices_status", lambda: next(states))
        answers = iter([""])
        monkeypatch.setattr(builtins, "input", lambda prompt="": next(answers))
        monkeypatch.setattr(adb, "reverse", lambda port: (True, "已桥接"))
        ok, _ = wizard.run_usb_wizard(8390, interactive=True)
        assert ok is True

    def test_skip_option(self, monkeypatch):
        monkeypatch.setattr(adb, "adb_path", lambda: "adb")
        monkeypatch.setattr(adb, "devices_status", lambda: [])
        monkeypatch.setattr(builtins, "input", lambda prompt="": "s")
        ok, msg = wizard.run_usb_wizard(8390, interactive=True)
        assert ok is False
        assert "跳过" in msg


    def test_repair_option(self, monkeypatch):
        """输入 r 触发驱动修复，修复成功后重试检测到设备。"""
        monkeypatch.setattr(adb, "adb_path", lambda: "adb")
        states = iter([[], [("S1", "device")]])
        monkeypatch.setattr(adb, "devices_status", lambda: next(states))
        answers = iter(["r"])
        monkeypatch.setattr(builtins, "input", lambda prompt="": next(answers))
        repairs = []
        monkeypatch.setattr(
            adb, "repair_recognition",
            lambda: (repairs.append(1), (True, "已修复"))[1]
        )
        monkeypatch.setattr(adb, "reverse_with_retry", lambda port: (True, "已桥接"))
        ok, _ = wizard.run_usb_wizard(8390, interactive=True)
        assert ok is True
        assert len(repairs) == 1

    def test_offline_auto_reconnect(self, monkeypatch):
        """offline 状态自动触发 reconnect。"""
        monkeypatch.setattr(adb, "adb_path", lambda: "adb")
        states = iter([[("S1", "offline")], [("S1", "device")]])
        monkeypatch.setattr(adb, "devices_status", lambda: next(states))
        calls = []
        monkeypatch.setattr(adb, "reconnect", lambda: calls.append(1))
        answers = iter([""])
        monkeypatch.setattr(builtins, "input", lambda prompt="": next(answers))
        monkeypatch.setattr(adb, "reverse_with_retry", lambda port: (True, "已桥接"))
        ok, _ = wizard.run_usb_wizard(8390, interactive=True)
        assert ok is True
        assert len(calls) == 1


# ---------- adb 重试逻辑 ----------

class TestReverseWithRetry:
    def test_first_attempt_success(self, monkeypatch):
        monkeypatch.setattr(adb, "reverse", lambda port: (True, "ok"))
        ok, msg = adb.reverse_with_retry(8390)
        assert ok is True

    def test_success_on_third(self, monkeypatch):
        results = iter([(False, "no device"), (False, "no device"), (True, "ok")])
        monkeypatch.setattr(adb, "reverse", lambda port: next(results))
        monkeypatch.setattr(adb, "devices_status", lambda: [])
        monkeypatch.setattr(adb.time, "sleep", lambda s: None)
        ok, _ = adb.reverse_with_retry(8390, attempts=3)
        assert ok is True

    def test_all_fail(self, monkeypatch):
        monkeypatch.setattr(adb, "reverse", lambda port: (False, "no device"))
        monkeypatch.setattr(adb, "devices_status", lambda: [])
        monkeypatch.setattr(adb.time, "sleep", lambda s: None)
        ok, msg = adb.reverse_with_retry(8390, attempts=3)
        assert ok is False
        assert "no device" in msg

    def test_offline_triggers_reconnect(self, monkeypatch):
        monkeypatch.setattr(adb, "reverse", lambda port: (False, "offline"))
        monkeypatch.setattr(adb, "devices_status", lambda: [("S1", "offline")])
        monkeypatch.setattr(adb.time, "sleep", lambda s: None)
        calls = []
        monkeypatch.setattr(adb, "reconnect", lambda: calls.append(1))
        adb.reverse_with_retry(8390, attempts=3)
        assert len(calls) == 2  # 前两次失败各触发一次

    def test_repair_non_windows(self, monkeypatch):
        monkeypatch.setattr(adb.sys, "platform", "linux")
        ok, msg = adb.repair_recognition()
        assert ok is False
        assert "Windows" in msg


# ---------- 通道操作提示 ----------

class TestChannelSteps:
    @pytest.mark.parametrize("channel", ["电脑热点", "局域网"])
    def test_non_empty(self, channel):
        steps = wizard.channel_steps(channel)
        assert isinstance(steps, list) and len(steps) >= 2
        assert all(isinstance(s, str) for s in steps)
