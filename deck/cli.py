"""命令行入口：启动服务并打印访问信息。"""

from __future__ import annotations

import argparse
import threading
import webbrowser

import uvicorn

from deck import __app_name__, __version__
from deck.config import CONFIG_PATH, load as load_config
from deck.lan import lan_ips
from deck.server import ServerApp


def main() -> None:
    parser = argparse.ArgumentParser(prog="deck", description=f"{__app_name__} 局域网控制器")
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
    print(f"  {__app_name__} v{__version__}  局域网伴侣操控台")
    print("=" * 56)
    print(f"  本机访问   : http://127.0.0.1:{port}")
    for ip in lan_ips():
        print(f"  局域网访问 : http://{ip}:{port}   （手机需与电脑在同一网络）")
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
