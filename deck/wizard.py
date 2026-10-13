"""启动连接向导：让「手机连上电脑」这件事变成一步步的引导。

三种通道，两种对待：
- USB 数据线直连：全自动检测（adb → 插线 → 授权 → 反向转发），每步都有提示与重试；
- 电脑热点 / 局域网：给出简短操作提示 + 二维码，扫码或输地址即连。

菜单只在交互式控制台出现（stdin 为 TTY）；开机自启等无人值守场景
用 --no-wizard 或非 TTY 自动跳过，绝不阻塞服务启动。
"""

from __future__ import annotations

from typing import Optional

from deck import adb

# 菜单重试次数（插线/授权等待）
_MAX_RETRY = 3


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
    return None


def show_menu() -> Optional[str]:
    """显示连接方式选择菜单，返回选中的通道（None = 智能模式）。"""
    plugged = bool(adb.devices())
    plug_hint = "（已检测到手机 ✔）" if plugged else ""
    print()
    print("请选择手机的连接方式：")
    print(f"  [1] USB 数据线直连 {plug_hint}  —— 自动检测并桥接，绕过防火墙/校园网（推荐）")
    print("  [2] 电脑热点          —— 手机连电脑的移动热点，扫码连接")
    print("  [3] Wi-Fi / 局域网    —— 手机与电脑连同一网络，扫码连接")
    print("  [回车] 智能模式       —— 自动检测全部通道并给出最优地址")
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


def run_usb_wizard(port: int, interactive: bool = True) -> tuple[bool, str]:
    """USB 直连分步向导：检测 adb → 等待插线 → 等待授权 → 建立反向转发。

    interactive=False 时（无人值守）只做单次尝试，失败即降级，不等待输入。
    返回 (是否成功, 提示消息)。
    """
    # ---- 步骤 1/3：adb 可用性 ----
    print(f"  [USB 1/3] 检查 adb 工具 ...", end="")
    adb_exe = adb.adb_path()
    if not adb_exe:
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
    else:
        print(f" ✔ {adb_exe}")

    # ---- 步骤 2/3：等待手机插线与授权 ----
    for attempt in range(1, _MAX_RETRY + 1):
        print(f"  [USB 2/3] 检测手机 ...", end="")
        status = adb.devices_status()
        states = [s for _, s in status]
        if "device" in states:
            print(f" ✔ 检测到 {len(status)} 台已授权设备")
            break
        if "unauthorized" in states:
            print(" 手机待授权")
            print("      → 手机上正在弹「允许 USB 调试吗？」：勾选「一律允许」再点「允许」")
        elif "offline" in states:
            print(" 设备离线")
            print("      → 手机屏幕解锁后重新插拔一次数据线")
        else:
            print(" 未检测到")
            if attempt == 1:
                _print_usb_plug_steps()
        if not interactive or attempt == _MAX_RETRY:
            return False, "手机未就绪（未插线 / 未开 USB 调试 / 未授权）"
        try:
            ans = input(f"           处理好后按回车重试（{_MAX_RETRY - attempt} 次机会），输入 s 跳过 USB 直连: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return False, "已跳过 USB 直连"
        if ans == "s":
            return False, "已跳过 USB 直连"
    else:  # pragma: no cover - for 循环必然 break 或 return
        return False, "手机未就绪"

    # ---- 步骤 3/3：建立反向转发 ----
    print(f"  [USB 3/3] 建立反向转发 (adb reverse tcp:{port}) ...", end="")
    ok, msg = adb.reverse(port)
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
