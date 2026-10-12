"""网络地址发现（零第三方依赖）：枚举本机局域网 / 热点 / 公网 IPv4 / IPv6 全局地址。

所有地址均来自本机网卡与系统网络能力，不依赖任何组网软件、隧道服务或第三方账号。
"""

from __future__ import annotations

import ipaddress
import re
import socket
import urllib.request
from typing import Optional

_HOTSPOT_NET = ipaddress.IPv4Network("192.168.137.0/24")  # Windows 移动热点默认网段
_TEREDO_NET = ipaddress.IPv6Network("2001:0000::/32")  # Teredo 隧道，非公网可直连
_SIXTOFOUR_NET = ipaddress.IPv6Network("2002::/16")  # 6to4 隧道，非公网可直连
_PUBLIC_IP_PROBES = [
    "https://ip.sb",
    "https://api.ipify.org",
    "https://myip.ipip.net",
]


def classify(ip: str) -> str:
    """返回地址类型：loopback / lan / hotspot / public / linklocal / ula / global6 / other。"""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return "other"
    if addr.is_loopback:
        return "loopback"
    if addr.version == 4:
        if addr in _HOTSPOT_NET:
            return "hotspot"
        if addr.is_private:  # 10.x / 172.16-31.x / 192.168.x
            return "lan"
        return "public"
    # IPv6
    if addr.is_link_local:  # fe80::/10
        return "linklocal"
    if addr in _TEREDO_NET or addr in _SIXTOFOUR_NET:
        return "other"  # Teredo / 6to4 隧道地址无法用于公网直连
    if addr.is_private:  # fc00::/7 ULA
        return "ula"
    return "global6"


def _enum_addrs() -> list[str]:
    addrs: list[str] = []

    # UDP 出口探测（不真正发包），拿到最可能被路由的主 IPv4
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if ip:
            addrs.append(ip)
    except OSError:
        pass

    # 按主机名枚举所有网卡 IPv4 + IPv6
    for family in (socket.AF_INET, socket.AF_INET6):
        try:
            for info in socket.getaddrinfo(socket.gethostname(), None, family):
                ip = info[4][0]
                if "%" in ip:  # 去掉 IPv6 scope id
                    ip = ip.split("%", 1)[0]
                if ip not in addrs:
                    addrs.append(ip)
        except OSError:
            pass

    return addrs


def lan_ips() -> list[str]:
    """局域网私网 IPv4（手机连同一 Wi-Fi 即可访问）。"""
    return [ip for ip in _enum_addrs() if classify(ip) == "lan"]


def hotspot_ips() -> list[str]:
    """Windows 移动热点网段 IPv4（手机连电脑热点即可访问）。"""
    return [ip for ip in _enum_addrs() if classify(ip) == "hotspot"]


def public_ips() -> list[str]:
    """本机直连的公网 IPv4（一般不会出现，除非网卡直接配置了公网地址）。"""
    return [ip for ip in _enum_addrs() if classify(ip) == "public"]


def global6_ips() -> list[str]:
    """全局 IPv6 地址（运营商下发，手机流量网络可直接访问，需路由器放行入站）。"""
    return [ip for ip in _enum_addrs() if classify(ip) == "global6"]


def detect_public_ipv4() -> Optional[str]:
    """探测出口公网 IPv4（访问公共查询服务，仅只读探测、不下载任何软件）。

    注意：探测结果是本网络出口的公网 IP；只有当宽带具备公网 IPv4 且
    路由器已把 TCP 8390 转发到本机时，手机才能用该地址访问。
    """
    for url in _PUBLIC_IP_PROBES:
        try:
            with urllib.request.urlopen(url, timeout=4) as resp:
                text = resp.read().decode("utf-8", "ignore").strip()
            m = re.search(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", text)
            if m:
                return m.group(0)
        except Exception:  # noqa: BLE001
            continue
    return None


def urls_by_channel(port: int) -> list[dict]:
    """按使用通道聚合访问地址，供启动横幅展示。"""
    channels: list[dict] = []
    for ip in lan_ips():
        channels.append(
            {"channel": "局域网", "url": f"http://{ip}:{port}", "hint": "手机连同一 Wi-Fi"}
        )
    for ip in hotspot_ips():
        channels.append(
            {"channel": "电脑热点", "url": f"http://{ip}:{port}", "hint": "手机连电脑移动热点"}
        )
    for ip in global6_ips():
        channels.append(
            {"channel": "IPv6 直连", "url": f"http://[{ip}]:{port}", "hint": "需路由器放行 IPv6 入站"}
        )
    return channels
