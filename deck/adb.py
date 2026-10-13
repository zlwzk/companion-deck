"""adb reverse 桥接：手机数据线直连电脑，零网络配置。

原理：Android 设备开启「USB 调试」后，`adb reverse tcp:P tcp:P` 会把手机上的
127.0.0.1:P 反向转发到电脑的 127.0.0.1:P —— 手机浏览器直接打开
http://127.0.0.1:8390，流量走 USB 线，完全绕过 Wi-Fi、热点、NAT 与防火墙，
校园网客户端（如锐捷）也无法感知。

adb 本体来自 Google platform-tools：
- 优先使用系统 PATH 中已安装的 adb；
- 其次使用本程序引导安装的位置（%LOCALAPPDATA%\\CompanionDeck\\platform-tools）；
- 都没有时，连接向导可在征得用户同意后自动下载安装（约 8 MB，Google 官方源）。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path
from typing import Optional

# Windows 下隐藏 adb 子进程的控制台窗口；其他平台无此标志
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0

# Google 官方 platform-tools 最新版下载地址（Windows）
PLATFORM_TOOLS_URL = "https://dl.google.com/android/repository/platform-tools-latest-windows.zip"


def _install_root() -> Path:
    """向导安装位置根目录：%LOCALAPPDATA%\\CompanionDeck。"""
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "CompanionDeck"


def known_install() -> Optional[str]:
    """返回向导此前安装的 adb 路径；不存在返回 None。"""
    candidate = _install_root() / "platform-tools" / "adb.exe"
    return str(candidate) if candidate.is_file() else None


def adb_path() -> Optional[str]:
    """返回可用的 adb 可执行文件路径；未安装返回 None。"""
    return shutil.which("adb") or known_install()


def _run(args: list[str], timeout: float = 8.0) -> subprocess.CompletedProcess:
    """执行 adb 子命令并捕获输出。"""
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=timeout,
        creationflags=_NO_WINDOW,
    )


def install_adb() -> tuple[bool, str]:
    """从 Google 官方源下载并解压 platform-tools 到本程序目录。

    仅使用标准库（urllib + zipfile），解压到用户目录，不改系统 PATH、
    不写注册表。返回 (是否成功, 提示消息)。
    """
    root = _install_root()
    dest = root / "platform-tools"
    zip_path = root / "platform-tools.zip"
    try:
        root.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(PLATFORM_TOOLS_URL, timeout=30) as resp, open(zip_path, "wb") as f:
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                f.write(chunk)
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(root)  # 压缩包内含 platform-tools/ 目录
        adb = dest / "adb.exe"
        if not adb.is_file():
            return False, "下载的压缩包结构异常（未找到 adb.exe）"
    except Exception as e:  # noqa: BLE001 网络/磁盘失败一律降级
        return False, f"自动安装 adb 失败：{e}"
    finally:
        try:
            zip_path.unlink(missing_ok=True)
        except OSError:
            pass
    return True, f"adb 已安装到 {dest}"


def devices_status() -> list[tuple[str, str]]:
    """列出全部 USB 设备的 (序列号, 状态)，状态含 device / unauthorized / offline。"""
    adb = adb_path()
    if not adb:
        return []
    try:
        proc = _run([adb, "devices"], timeout=5.0)
    except Exception:  # noqa: BLE001 adb 崩溃/驱动异常按无设备处理
        return []
    out: list[tuple[str, str]] = []
    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if not line or line.startswith("List of devices"):
            continue
        parts = line.split()
        if len(parts) >= 2 and parts[0] != "*":
            out.append((parts[0], parts[1]))
    return out


def devices() -> list[str]:
    """列出已连接且状态为 device 的 USB 设备序列号。"""
    return [serial for serial, state in devices_status() if state == "device"]


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
