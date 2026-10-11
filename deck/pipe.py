"""Soundpad Remote Control 命名管道客户端。

协议参考 Soundpad 官方实现 SoundpadRemoteControl.java：
- 连接命名管道 \\\\.\\pipe\\sp_remote_control
- 直接写入 UTF-8 命令文本，例如 "DoTogglePause()"
- 读取响应：以 "R-200" 等 HTTP 风格状态码开头，或返回 XML / 数字 / 状态文本

使用 ctypes 实现，零第三方依赖。
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import time

PIPE_NAME = r"\\.\pipe\sp_remote_control"

GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
OPEN_EXISTING = 3
INVALID_HANDLE_VALUE = wt.HANDLE(-1).value

_k32 = ctypes.WinDLL("kernel32", use_last_error=True)

_k32.CreateFileW.restype = wt.HANDLE
_k32.CreateFileW.argtypes = [
    wt.LPCWSTR, wt.DWORD, wt.DWORD, wt.LPVOID, wt.DWORD, wt.DWORD, wt.HANDLE,
]
_k32.WriteFile.argtypes = [wt.HANDLE, wt.LPVOID, wt.DWORD, wt.LPDWORD, wt.LPVOID]
_k32.ReadFile.argtypes = [wt.HANDLE, wt.LPVOID, wt.DWORD, wt.LPDWORD, wt.LPVOID]
_k32.PeekNamedPipe.argtypes = [
    wt.HANDLE, wt.LPVOID, wt.DWORD, wt.LPDWORD, wt.LPDWORD, wt.LPDWORD,
]
_k32.CloseHandle.argtypes = [wt.HANDLE]


def _connect():
    handle = _k32.CreateFileW(
        PIPE_NAME,
        GENERIC_READ | GENERIC_WRITE,
        0,
        None,
        OPEN_EXISTING,
        0,
        None,
    )
    if handle == INVALID_HANDLE_VALUE:
        return None
    return handle


def _read_response(handle, timeout: float = 2.0) -> str | None:
    """用 PeekNamedPipe 轮询等待数据，避免阻塞式 ReadFile 卡死。"""
    available = wt.DWORD(0)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        ok = _k32.PeekNamedPipe(handle, None, 0, None, ctypes.byref(available), None)
        if ok and available.value > 0:
            size = int(available.value)
            buf = ctypes.create_string_buffer(size)
            read = wt.DWORD(0)
            if not _k32.ReadFile(handle, buf, size, ctypes.byref(read), None):
                return None
            return buf.raw[: read.value].decode("utf-8", errors="replace")
        time.sleep(0.02)
    return None  # 超时


def send(command: str, timeout: float = 2.0) -> str | None:
    """发送一条命令并返回响应文本；无法连接（Soundpad 未运行）时返回 None。"""
    handle = _connect()
    if handle is None:
        return None

    try:
        payload = command.encode("utf-8")
        written = wt.DWORD(0)
        if not _k32.WriteFile(handle, payload, len(payload), ctypes.byref(written), None):
            return None
        return _read_response(handle, timeout)
    finally:
        _k32.CloseHandle(handle)
