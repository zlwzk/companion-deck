"""adb reverse 桥接：手机数据线直连电脑，零网络配置。

原理：Android 设备开启「USB 调试」后，`adb reverse tcp:P tcp:P` 会把手机上的
127.0.0.1:P 反向转发到电脑的 127.0.0.1:P —— 手机浏览器直接打开
http://127.0.0.1:8390，流量走 USB 线，完全绕过 Wi-Fi、热点、NAT 与防火墙，
校园网客户端（如锐捷）也无法感知。

仅依赖 Google platform-tools 中的 adb.exe（用户自备并加入 PATH），
本模块只调用已存在的 adb，不会下载或安装任何东西。
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from typing import Optional

# Windows 下隐藏 adb 子进程的控制台窗口；其他平台无此标志
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0


def adb_path() -> Optional[str]:
    """返回可用的 adb 可执行文件路径；未安装返回 None。"""
    return shutil.which("adb")


def _run(args: list[str], timeout: float = 8.0) -> subprocess.CompletedProcess:
    """执行 adb 子命令并捕获输出。"""
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=timeout,
        creationflags=_NO_WINDOW,
    )


def devices() -> list[str]:
    """列出已连接且状态为 device 的 USB 设备序列号。"""
    adb = adb_path()
    if not adb:
        return []
    try:
        proc = _run([adb, "devices"], timeout=5.0)
    except Exception:  # noqa: BLE001 adb 崩溃/驱动异常按无设备处理
        return []
    serials: list[str] = []
    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if not line or line.startswith("List of devices"):
            continue
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":  # 排除 offline / unauthorized
            serials.append(parts[0])
    return serials


def reverse(port: int) -> tuple[bool, str]:
    """对所有已连接设备执行 `adb reverse tcp:port tcp:port`。

    返回 (是否成功, 提示消息)；失败时消息面向用户可读。
    """
    adb = adb_path()
    if not adb:
        return False, "未找到 adb（需安装 Android platform-tools 并加入 PATH）"

    serials = devices()
    if not serials:
        return False, "未检测到 USB 设备（请插线并开启开发者选项中的「USB 调试」）"

    ok: list[str] = []
    fail: list[str] = []
    for serial in serials:
        try:
            proc = _run([adb, "-s", serial, "reverse", f"tcp:{port}", f"tcp:{port}"])
        except Exception as e:  # noqa: BLE001
            fail.append(f"{serial}: {e}")
            continue
        if proc.returncode == 0:
            ok.append(serial)
        else:
            detail = (proc.stderr or proc.stdout or "unknown").strip()
            fail.append(f"{serial}: {detail}")

    if ok and not fail:
        return True, f"已桥接 {len(ok)} 台设备，手机访问 http://127.0.0.1:{port}"
    if ok and fail:
        return True, f"已桥接 {len(ok)} 台；失败 {len(fail)} 台（{'；'.join(fail)}）"
    return False, f"adb reverse 失败（{'；'.join(fail)}）"
