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

import base64
import os
import shutil
import subprocess
import sys
import time
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


def restart_server() -> None:
    """重启 adb 守护进程，清除陈旧的设备枚举（插拔后列表不刷新时使用）。"""
    adb = adb_path()
    if not adb:
        return
    try:
        _run([adb, "kill-server"], timeout=5.0)
    except Exception:  # noqa: BLE001
        pass


def reconnect() -> None:
    """`adb reconnect offline`：尝试恢复 offline 状态的设备。"""
    adb = adb_path()
    if not adb:
        return
    try:
        _run([adb, "reconnect", "offline"], timeout=5.0)
    except Exception:  # noqa: BLE001
        pass


def reverse_with_retry(port: int, attempts: int = 3, delay: float = 1.5) -> tuple[bool, str]:
    """带重试的反向转发：手机刚插上时 adb 枚举有延迟，offline 时自动 reconnect。"""
    msg = "未检测到 USB 设备"
    for i in range(max(1, attempts)):
        ok, msg = reverse(port)
        if ok:
            return ok, msg
        if i < attempts - 1:
            if any(state == "offline" for _, state in devices_status()):
                reconnect()
            time.sleep(delay)
    return False, msg


# adb 的 Windows 后端只枚举注册表中带此接口 GUID 的设备；荣耀/华为等机型
# 被 Windows 自动绑定裸 WinUSB 驱动时缺少该值，表现为「adb devices 看不到手机」。
_ADB_IFACE_GUID = "{F72FE0D4-CBCB-407d-8814-9ED673D0DD6B}"


def repair_recognition() -> tuple[bool, str]:
    """一键修复「手机已插线、已开 USB 调试，但 adb 看不到」。

    给所有 ADB Interface 设备节点的注册表补写 DeviceInterfaceGUIDs 并重启节点
    （等效安装 Google USB 驱动的核心效果）。会弹出 UAC 管理员授权窗口；
    修复对设备节点持久生效，但同一手机换插**另一个 USB 口**会生成新节点，
    需重新修复。仅 Windows 有效。
    """
    if sys.platform != "win32":
        return False, "仅 Windows 需要此修复"
    script = (
        "$devs = Get-PnpDevice -PresentOnly | Where-Object { $_.FriendlyName -like '*ADB Interface*' };"
        "if (-not $devs) { exit 3 };"
        "foreach ($d in $devs) {"
        "  $key = \"HKLM:\\SYSTEM\\CurrentControlSet\\Enum\\$($d.InstanceId)\\Device Parameters\";"
        "  New-Item -Path $key -Force | Out-Null;"
        f"  New-ItemProperty -Path $key -Name DeviceInterfaceGUIDs -PropertyType MultiString -Value @('{_ADB_IFACE_GUID}') -Force | Out-Null;"
        "  pnputil /restart-device \"$($d.InstanceId)\" | Out-Null"
        "};"
        "exit 0"
    )
    enc = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    cmd = (
        "$p = Start-Process powershell -Verb RunAs -Wait -PassThru -WindowStyle Hidden "
        f"-ArgumentList '-NoProfile','-EncodedCommand','{enc}'; exit $p.ExitCode"
    )
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command", cmd],
            capture_output=True, text=True, timeout=180, creationflags=_NO_WINDOW,
        )
    except Exception as e:  # noqa: BLE001
        return False, f"修复流程执行失败：{e}"
    if proc.returncode == 3:
        return False, "未找到 ADB Interface 设备（请确认手机已插线并开启 USB 调试）"
    if proc.returncode != 0:
        return False, "已取消管理员授权，未执行修复"
    time.sleep(2)  # 等待节点重启完成
    restart_server()
    return True, "已修复驱动识别并重启 adb（下次插这个 USB 口免修复）"


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
