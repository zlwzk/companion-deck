"""命令行入口：启动服务并打印访问信息。"""

from __future__ import annotations

import argparse
import socket
import threading
import webbrowser

import uvicorn

from deck import __app_name__, __version__
from deck.config import CONFIG_PATH, load as load_config
from deck.lan import lan_ips, tailscale_hostname, tailscale_ips, zerotier_ips
from deck.server import ServerApp


def _port_in_use(port: int) -> bool:
    try:
        with socket.socket() as s:
            s.bind(("127.0.0.1", port))
            return False
    except OSError:
        return True


def main() -> None:
    parser = argparse.ArgumentParser(prog="deck", description=f"{__app_name__} 伴侣操控台")
    parser.add_argument("--port", type=int, default=None, help="监听端口（默认取配置）")
    parser.add_argument("--host", type=str, default=None, help="监听地址（默认 0.0.0.0）")
    parser.add_argument("--no-browser", action="store_true", help="启动后不打开浏览器")
    args = parser.parse_args()

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

    print("=" * 56)
    print(f"  {__app_name__} v{__version__}  伴侣操控台（局域网 / 互联网）")
    print("=" * 56)
    print(f"  本机访问   : http://127.0.0.1:{port}")
    for ip in lan_ips():
        print(f"  局域网访问 : http://{ip}:{port}   （手机需与电脑在同一网络）")
    ts_ips = tailscale_ips()
    zt_ips = zerotier_ips()
    if ts_ips or zt_ips:
        for ip in ts_ips:
            print(f"  互联网远程 : http://{ip}:{port}   （Tailscale，全球可访问）")
        for ip in zt_ips:
            print(f"  互联网远程 : http://{ip}:{port}   （ZeroTier，全球可访问）")
        hostname = tailscale_hostname()
        if hostname:
            print(f"  远程域名   : http://{hostname}:{port}   （Tailscale MagicDNS）")
    else:
        print("  互联网远程 : 未检测到 ZeroTier / Tailscale —— 如需外网控制，安装 ZeroTier 后重启（详见 docs/SETUP.md）")
    if token:
        print(f"  访问口令   : {token}")
        print("  手机打开页面后输入上方口令即可连接")
    else:
        print("  访问口令   : 已关闭（auth.enabled = false）")
    print(f"  当前适配器 : {active.display_name if active else '无'}（{soundpad_online}）")
    print("=" * 56)

    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()

    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
