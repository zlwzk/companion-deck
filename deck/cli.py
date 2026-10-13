"""命令行入口：启动服务并打印访问信息（多通道直连）。"""

from __future__ import annotations

import argparse
import os
import socket
import sys
import threading
import webbrowser
from typing import Optional

import uvicorn

from deck import __app_name__, __version__
from deck.autostart import disable as disable_autostart
from deck.autostart import enable as enable_autostart
from deck.autostart import is_enabled as autostart_enabled
from deck.config import CONFIG_PATH, load as load_config
from deck.lan import detect_public_ipv4, urls_by_channel
from deck.server import ServerApp
from deck.tray import is_supported as tray_supported


def _port_in_use(port: int) -> bool:
    try:
        with socket.socket() as s:
            s.bind(("127.0.0.1", port))
            return False
    except OSError:
        return True


def _make_listen_socket(ipv4_host: str, port: int) -> tuple[socket.socket, str]:
    """优先创建 IPv6 双栈监听 socket；失败回退 IPv4。"""
    try:
        s = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        s.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)  # 双栈
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("::", port))
        return s, "dual-stack"
    except OSError:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((ipv4_host, port))
        return s, "ipv4"


def _print_qr_ascii(url: str) -> None:
    """在终端打印 ASCII 二维码（仅当 qrcode 库可用时）。"""
    try:
        import qrcode  # type: ignore
        from io import StringIO
        qr = qrcode.QRCode(border=1, error_correction=qrcode.constants.ERROR_CORRECT_L)
        qr.add_data(url)
        qr.make(fit=True)
        buf = StringIO()
        qr.print_ascii(buf, invert=True)
        print(buf.getvalue())
    except Exception:  # noqa: BLE001
        print("  （未安装 qrcode 库，跳过终端 ASCII 二维码）")


def main() -> None:
    parser = argparse.ArgumentParser(prog="deck", description=f"{__app_name__} 伴侣操控台")
    parser.add_argument("--port", type=int, default=None, help="监听端口（默认取配置）")
    parser.add_argument("--host", type=str, default=None, help="IPv4 回退监听地址（默认 0.0.0.0）")
    parser.add_argument("--no-browser", action="store_true", help="启动后不打开浏览器")
    parser.add_argument("--no-tray", action="store_true", help="不创建系统托盘图标")
    parser.add_argument("--usb", action="store_true",
                        help="USB 直连：进入分步向导（自动检测 adb/插线/授权并桥接），手机访问 http://127.0.0.1:端口")
    parser.add_argument("--no-wizard", action="store_true",
                        help="跳过启动连接向导（开机自启/无人值守场景），自动检测全部通道")
    parser.add_argument("--autostart", choices=["on", "off", "status"], default=None,
                        help="管理开机自启：on=启用 / off=禁用 / status=查询")
    parser.add_argument("--cwd", type=str, default=None, help="开机自启时的工作目录（仅与 autostart on 配合使用）")
    args = parser.parse_args()

    # ---------- 开机自启子命令 ----------
    if args.autostart:
        from deck import autostart
        if args.autostart == "status":
            print(f"[{__app_name__}] 开机自启：{'已启用' if autostart.is_enabled() else '未启用'}")
        elif args.autostart == "on":
            ok = autostart.enable()
            print(f"[{__app_name__}] 启用开机自启：{'成功' if ok else '失败'}")
        else:
            ok = autostart.disable()
            print(f"[{__app_name__}] 禁用开机自启：{'成功' if ok else '失败'}")
        if args.autostart != "status":
            return
        if args.autostart == "status" and not autostart.is_enabled():
            return

    cfg = load_config()
    if args.port:
        cfg["server"]["port"] = args.port
    if args.host:
        cfg["server"]["host"] = args.host

    host = cfg["server"]["host"]
    port = int(cfg["server"]["port"])

    if _port_in_use(port):
        print(f"[{__app_name__}] 端口 {port} 已被占用：可能是上一个实例仍在运行（请先关闭旧窗口），或其他程序占用。")
        print(f"[{__app_name__}] 可临时换端口启动：python -m deck --port 8391")
        raise SystemExit(1)

    server_app = ServerApp(cfg, config_path=CONFIG_PATH)
    app = server_app.app

    token = server_app._get_token()
    active = server_app.registry.active
    soundpad_online = "未知"
    if active is not None:
        try:
            soundpad_online = "在线" if active.available() else "未运行/不可用"
        except Exception:  # noqa: BLE001
            soundpad_online = "未知"

    channels = urls_by_channel(port)

    def _add_usb_channel() -> None:
        channels.append(
            {"channel": "USB 直连", "url": f"http://127.0.0.1:{port}",
             "hint": "手机浏览器直接打开（流量走数据线）"}
        )

    # ---------- 连接方式选择 / USB 直连 ----------
    usb_ok = False
    usb_msg = ""
    focus: Optional[str] = None  # 向导特别突出的通道（决定二维码指向）
    interactive = sys.stdin.isatty()

    def _try_auto_bridge() -> None:
        """智能模式：检测到已授权手机则自动桥接。"""
        nonlocal usb_ok, usb_msg, focus
        import deck.adb as _adb
        if _adb.adb_path() and _adb.devices():
            usb_ok, usb_msg = _adb.reverse(port)
            if usb_ok:
                _add_usb_channel()
                focus = "USB 直连"

    if args.usb:
        from deck.wizard import run_usb_wizard
        usb_ok, usb_msg = run_usb_wizard(port, interactive=interactive)
        if usb_ok:
            _add_usb_channel()
            focus = "USB 直连"
    elif args.no_wizard or not interactive:
        _try_auto_bridge()
    else:
        from deck.wizard import show_menu
        choice = show_menu()
        if choice == "usb":
            usb_ok, usb_msg = run_usb_wizard(port, interactive=True)
            if usb_ok:
                _add_usb_channel()
                focus = "USB 直连"
        elif choice is None:
            _try_auto_bridge()
        else:
            focus = choice  # 电脑热点 / 局域网

    # 二维码首选地址：向导所选通道 > 直连链路（热点/USB） > 局域网
    qr_channel = None
    if focus:
        qr_channel = next((c for c in channels if c["channel"] == focus), None)
    if qr_channel is None:
        direct = next((c for c in channels if c["channel"] in ("电脑热点", "USB 直连")), None)
        qr_channel = direct or next((c for c in channels if c["channel"] == "局域网"), None)
    lan_url = qr_channel["url"] if qr_channel else None
    qr_url = f"{lan_url}?token={token}" if lan_url and token else (lan_url or f"http://127.0.0.1:{port}")

    print("=" * 60)
    print(f"  {__app_name__} v{__version__}  伴侣操控台（局域网直连）")
    print("=" * 60)
    print(f"  本机访问   : http://127.0.0.1:{port}")
    for ch in channels:
        marker = "★" if qr_channel and ch["url"] == qr_channel["url"] else " "
        print(f"  {marker} {ch['channel']} : {ch['url']}   （{ch['hint']}）")
    if token:
        print(f"  访问口令   : {token}")
        print(f"  扫码直连   : {qr_url}  （手机相机扫码即可，免输入地址与口令）")
    else:
        print("  访问口令   : 已关闭（auth.enabled = false）")
    print(f"  当前适配器 : {active.display_name if active else '无'}（{soundpad_online}）")
    if args.usb:
        state = "✔ " + usb_msg if usb_ok else "✘ " + usb_msg
        print(f"  USB 直连   : {state}")
    autostart_state = "已启用" if autostart_enabled() else "未启用"
    tray_state = "已启用" if (tray_supported() and not args.no_tray) else "未启用"
    print(f"  系统托盘   : {tray_state}")
    print(f"  开机自启   : {autostart_state}（用 --autostart on/off 切换）")
    print("=" * 60)

    if not channels:
        print("[提示] 未检测到局域网/热点地址，本机访问仍可用；")
        print("        如需手机控制，请检查网络连接（详见 docs/SETUP.md）。")
    else:
        if focus in ("电脑热点", "局域网"):
            from deck.wizard import channel_steps
            print(f"「{focus}」连接步骤：")
            for step in channel_steps(focus):
                print(f"  {step}")
            print()
        print("连接方式速查（完整步骤见 docs/SETUP.md）：")
        print("  ① 同一 Wi-Fi     → 手机打开「局域网」地址，或扫上方的「扫码直连」二维码")
        print("  ② 打游戏时       → 手机连电脑「移动热点」→ 打开「电脑热点」地址")
        print("  ③ 数据线直连     → 启动时加 --usb 参数（需 adb），手机浏览器打开 http://127.0.0.1:" + str(port))
        if any(ch["channel"] == "IPv6 直连" for ch in channels):
            print("  ④ 人在外面       → 可选「IPv6 直连」地址（需在路由器放行；详见 SETUP.md）")
        # 终端打印二维码（如果安装了 qrcode）
        if lan_url:
            print()
            _print_qr_ascii(qr_url)
            print("  ↑ 用手机相机扫描即可连接（已包含口令）")

    # ---------- 系统托盘 ----------
    if tray_supported() and not args.no_tray:
        try:
            from deck.tray import TrayIcon

            icon_path = None
            assets = os.path.join(os.path.dirname(__file__), "..", "assets")
            if os.path.isdir(assets):
                for name in ("icon.ico", "icon.png"):
                    p = os.path.join(assets, name)
                    if os.path.exists(p):
                        icon_path = p
                        break
            tray = TrayIcon(
                title=f"{__app_name__} v{__version__}",
                url=f"http://127.0.0.1:{port}",
                icon_path=icon_path,
                on_quit=lambda: os._exit(0),
            )
            tray.start()
        except Exception:  # noqa: BLE001 托盘失败不影响主流程
            pass

    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()

    listen_sock, _ = _make_listen_socket(host, port)
    config = uvicorn.Config(app, log_level="warning")
    server = uvicorn.Server(config)
    server.run(sockets=[listen_sock])


if __name__ == "__main__":
    main()
