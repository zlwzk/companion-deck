"""局域网 IP 发现，用于打印手机可访问的地址。"""

from __future__ import annotations

import socket


def lan_ips() -> list[str]:
    ips: list[str] = []

    # 通过 UDP 连接外部地址探测本机出口 IP（不真正发包）
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if ip and not ip.startswith("127."):
            ips.append(ip)
    except OSError:
        pass

    # 备用：按主机名解析所有 IPv4 地址
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127.") and ip not in ips:
                ips.append(ip)
    except OSError:
        pass

    return ips or ["127.0.0.1"]
