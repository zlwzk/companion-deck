"""启动连接向导：让「手机连上电脑」这件事变成一步步的引导。

三种通道 + 一个修复入口：
- USB 数据线直连：全自动检测（adb → 插线 → 授权 → 反向转发），每步都有提示与重试；
- 电脑热点 / 局域网：给出简短操作提示 + 二维码，扫码或输地址即连；
- 一键修复驱动识别：手机已插线、已开 USB 调试却检测不到时使用，
  修复成功后会自动接着完成 USB 桥接。

菜单只在交互式控制台出现（stdin 为 TTY）；开机自启等无人值守场景
用 --no-wizard 或非 TTY 自动跳过，绝不阻塞服务启动。
"""

from __future__ import annotations

import time
from typing import Optional

from deck import adb

# 菜单重试次数（插线/授权等待）
_MAX_RETRY = 3

# 修复后「重新插拔」自动检测：轮询次数 × 间隔 ≈ 一轮等待总时长（秒）
_REPLUG_POLLS = 20
_REPLUG_INTERVAL = 1.5


# ---------- 菜单 ----------

def parse_choice(choice: str) -> Optional[str]:
    """解析菜单输入：usb / 电脑热点 / 局域网 / None(智能模式)。"""
    c = choice.strip().lower()
    if c in ("1", "usb", "u"):
        return "usb"
    if c in ("2", "hotspot", "热点", "rd"):
        return "电脑热点"
    if c in ("3", "lan", "局域网", "wifi", "wi-fi"):
        return "局域网"
    if c in ("4", "fix", "repair", "修复", "r"):
        return "repair"
    return None


def show_menu() -> Optional[str]:
    """显示连接方式选择菜单，返回选中的通道（None = 智能模式）。"""
    plugged = bool(adb.devices())
    print()
    print("─" * 58)
    print("  请选择手机的连接方式")
    print("─" * 58)
    if plugged:
        print("  当前状态：已检测到手机 ✔ 可直接选 [1] USB 直连")
    else:
        print("  当前状态：未检测到手机（选 [1] 后会一步步引导你插线）")
    print()
    print("  [1] USB 数据线直连    —— 自动检测并桥接，绕过防火墙/校园网（推荐）")
    print("  [2] 电脑热点          —— 手机连电脑的移动热点，扫码连接")
    print("  [3] Wi-Fi / 局域网    —— 手机与电脑连同一网络，扫码连接")
    print("  [4] 一键修复驱动识别  —— 已插线、已开 USB 调试却检测不到时点我")
    print("  [回车] 智能模式       —— 自动检测全部通道并给出最优地址")
    print("─" * 58)
    try:
        choice = input("请输入选项: ").strip()
    except (EOFError, KeyboardInterrupt):
        choice = ""
    return parse_choice(choice)


# ---------- USB 分步向导 ----------

def _print_usb_plug_steps() -> None:
    print("      ① 用数据线把手机连到电脑（需支持数据传输，纯充电线无效）")
    print("      ② 手机：设置 → 关于手机 → 连点 7 次「版本号」开启开发者模式")
    print("      ③ 手机：设置 → 系统 → 开发人员选项 → 打开「USB 调试」")
    print("         （荣耀/华为注意认准「USB 调试」，不要选成「允许通过 HDB 连接设备」）")
    print("      ④ 重新插拔一次数据线，下拉通知栏把 USB 用途选为「传输文件」")


def _ensure_adb(interactive: bool, step: str = "[USB 1/3]") -> tuple[bool, str]:
    """步骤「检查 adb 工具」：未安装时（交互模式）可一键自动下载安装。"""
    print(f"  {step} 检查 adb 工具 ...", end="")
    adb_exe = adb.adb_path()
    if adb_exe:
        print(f" ✔ {adb_exe}")
        return True, ""
    print(" 未安装")
    if not interactive:
        return False, "未找到 adb；手动安装 platform-tools 并加入 PATH 后重试"
    ans = input("           是否自动下载安装 adb（Google 官方，约 8 MB）？[y/N] ").strip().lower()
    if ans not in ("y", "yes"):
        return False, "未安装 adb，USB 直连不可用（可稍后手动安装 platform-tools）"
    print("           正在从 dl.google.com 下载 ...", end="", flush=True)
    ok, msg = adb.install_adb()
    print(" 完成" if ok else f" 失败（{msg}）")
    if not ok:
        print(f"           可手动下载：{adb.PLATFORM_TOOLS_URL}")
        return False, "自动安装 adb 失败，USB 直连不可用"
    adb_exe = adb.adb_path()
    if not adb_exe:
        return False, "adb 安装异常，USB 直连不可用"
    print(f"           ✔ {adb_exe}")
    return True, ""


def _run_repair_step(indent: str = "      ") -> tuple[bool, str]:
    """执行一次驱动识别修复（带 UAC 授权提示与结果打印）。"""
    print(f"{indent}即将弹出「用户账户控制」窗口：请点「是」授权（用于修复 adb 驱动识别）…")
    ok, msg = adb.repair_recognition()
    print(f"{indent}{'✔' if ok else '✘'} {msg}")
    return ok, msg


def _wait_device(interactive: bool) -> str:
    """步骤「检测手机」的等待循环（[USB 2/3]）。

    unauthorized 给出授权指引、offline 自动 reconnect、未检测到给出插线指引，
    并提供「r 一键修复驱动识别」选项。返回 ready / skip / fail。
    """
    for attempt in range(1, _MAX_RETRY + 1):
        print("  [USB 2/3] 检测手机 ...", end="")
        status = adb.devices_status()
        states = [s for _, s in status]
        if "device" in states:
            print(f" ✔ 检测到 {len(status)} 台已授权设备")
            return "ready"
        if "unauthorized" in states:
            print(" 手机待授权")
            print("      → 手机上正在弹「允许 USB 调试吗？」：勾选「一律允许」再点「允许」")
        elif "offline" in states:
            print(" 设备离线，正在自动重连 ...")
            adb.reconnect()
        else:
            print(" 未检测到")
            if attempt == 1:
                _print_usb_plug_steps()
                print("      ⑤ 若确认已插线、已开 USB 调试仍检测不到：输入 r 一键修复驱动识别")
        if not interactive or attempt == _MAX_RETRY:
            return "fail"
        try:
            ans = input(f"           回车重试（剩 {_MAX_RETRY - attempt} 次）/ r 修复驱动识别 / s 跳过: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return "skip"
        if ans == "s":
            return "skip"
        if ans == "r":
            _run_repair_step(indent="           ")
    return "fail"  # pragma: no cover - 循环必然 return


def _wait_replug(interactive: bool, step: str = "[修复 3/3]") -> str:
    """修复后的「重新插拔」自动重试：引导用户拔线重插，随后自动轮询检测手机。

    无需按回车：设备插回（或用户在手机上完成授权）后自动进入下一步；
    一轮超时后交互模式可回车再等一轮。返回 ready / skip / fail。
    """
    # 修复后 Windows 会自动重枚举，先立即看一次（可能已就绪）
    status = adb.devices_status()
    if "device" in [s for _, s in status]:
        print(f"  {step} 检测手机 ... ✔ 检测到 {len(status)} 台已授权设备")
        return "ready"
    while True:  # 一轮 ≈ _REPLUG_POLLS × _REPLUG_INTERVAL 秒自动轮询
        print(f"  {step} 等待重新插拔 ...")
        print("      → 请拔下数据线，稍等 1 秒再插回（尽量插同一个 USB 口）")
        print(f"      → 接下来约 {int(_REPLUG_POLLS * _REPLUG_INTERVAL)} 秒会自动检测，手机弹出授权框请直接允许")
        auth_hinted = False
        for i in range(_REPLUG_POLLS):
            status = adb.devices_status()
            states = [s for _, s in status]
            if "device" in states:
                print(f"  {step} 检测手机 ... ✔ 检测到 {len(status)} 台已授权设备")
                return "ready"
            if "unauthorized" in states:
                if not auth_hinted:
                    print("      → 手机已识别，正在等你在手机上点「允许」（勾选「一律允许」）…")
                    auth_hinted = True
            elif "offline" in states:
                adb.reconnect()
            if i < _REPLUG_POLLS - 1:
                time.sleep(_REPLUG_INTERVAL)
        if not interactive:
            return "fail"
        try:
            ans = input("           仍未检测到：回车再等一轮 / s 跳过: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return "skip"
        if ans == "s":
            return "skip"


def run_usb_wizard(port: int, interactive: bool = True) -> tuple[bool, str]:
    """USB 直连分步向导：检测 adb → 等待插线 → 等待授权 → 建立反向转发。

    interactive=False 时（无人值守）只做单次尝试，失败即降级，不等待输入。
    返回 (是否成功, 提示消息)。
    """
    ok, msg = _ensure_adb(interactive, "[USB 1/3]")
    if not ok:
        return False, msg
    result = _wait_device(interactive)
    if result == "skip":
        return False, "已跳过 USB 直连"
    if result != "ready":
        return False, "手机未就绪（未插线 / 未开 USB 调试 / 未授权；可重启程序后选 [1] 重试，或选 [4] 一键修复驱动识别）"
    print(f"  [USB 3/3] 建立反向转发 (adb reverse tcp:{port}) ...", end="")
    ok, msg = adb.reverse_with_retry(port)
    print(" ✔" if ok else f" ✘（{msg}）")
    return ok, msg


def run_repair_wizard(port: int, interactive: bool = True) -> tuple[bool, str]:
    """一键修复驱动识别向导：检查 adb → 修复驱动识别 → 重新检测手机并自动桥接。

    适用场景：手机已插线、已开 USB 调试，程序却始终检测不到
    （荣耀/华为等机型常被 Windows 绑定了不完整的驱动）。修复成功后
    自动完成 USB 反向转发，效果等同直接选 [1]。返回 (是否成功, 提示消息)。
    """
    ok, msg = _ensure_adb(interactive, "[修复 1/3]")
    if not ok:
        return False, msg
    print("  [修复 2/3] 修复驱动识别 ...")
    print("      原理：为手机补注册 adb 驱动接口（等效安装 Google USB 驱动）")
    ok, msg = _run_repair_step()
    if not ok:
        return False, f"修复未完成：{msg}"
    result = _wait_replug(interactive, step="[修复 3/3]")
    if result != "ready":
        return False, "修复已完成，但手机仍未就绪：请重新插拔数据线（固定同一个 USB 口），再选择 [1] USB 直连重试"
    print(f"  [USB] 建立反向转发 (adb reverse tcp:{port}) ...", end="")
    ok, msg = adb.reverse_with_retry(port)
    print(" ✔" if ok else f" ✘（{msg}）")
    return ok, msg


# ---------- 热点 / 局域网操作提示 ----------

def channel_steps(channel: str) -> list[str]:
    """返回所选通道在手机侧的操作提示（逐行打印）。"""
    if channel == "电脑热点":
        return [
            "① 电脑：设置 → 网络 → 移动热点 → 开启（与电脑共享我的 Internet）",
            "② 手机：设置 → WLAN → 连接电脑发出的热点信号",
            "③ 手机：打开下方「扫码直连」二维码，或输入「电脑热点」地址",
        ]
    return [
        "① 手机：设置 → WLAN → 连接与电脑相同的 Wi-Fi / 网络",
        "② 手机：打开下方「扫码直连」二维码，或输入「局域网」地址",
    ]
