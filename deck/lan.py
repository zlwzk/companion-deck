"""网络地址发现：本机局域网地址、Tailscale 虚拟网地址（用于互联网远程）。"""

from __future__ import annotations

import ipaddress
import json
import socket
import subprocess
from typing import Optional

_TAILSCALE_NET = ipaddress.IPv4Network("100.64.0.0/10")
_ZEROTIER_NET = ipaddress.IPv4Network("25.0.0.0/8")  # ZeroTier 默认管理网段


def classify_ip(ip: str) -> str:
    """返回地址类型：tailscale / zerotier / lan / loopback / other。"""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return "other"
    if addr.is_loopback:
        return "loopback"
    if addr.version == 4 and addr in _TAILSCALE_NET:
        return "tailscale"
    if addr.version == 4 and addr in _ZEROTIER_NET:
        return "zerotier"
    if addr.is_private:  # 10.x / 172.16-31.x / 192.168.x
        return "lan"
    return "other"


def _enum_ips() -> list[str]:
    ips: list[str] = []

    # UDP 出口探测（不真正发包），拿到最可能被路由的地址
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if ip:
            ips.append(ip)
    except OSError:
        pass

    # 按主机名枚举所有网卡 IPv4
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip not in ips:
                ips.append(ip)
    except OSError:
        pass

    return ips


def lan_ips() -> list[str]:
    """局域网（私网）IPv4 地址列表，供手机在同一 Wi-Fi 下访问。"""
    return [ip for ip in _enum_ips() if classify_ip(ip) == "lan"]


def tailscale_ips() -> list[str]:
    """Tailscale 虚拟网（100.64.0.0/10）IPv4 地址列表，供互联网远程访问。"""
    return [ip for ip in _enum_ips() if classify_ip(ip) == "tailscale"]


def zerotier_ips() -> list[str]:
    """ZeroTier 虚拟网（25.0.0.0/8）IPv4 地址列表，供互联网远程访问。"""
    return [ip for ip in _enum_ips() if classify_ip(ip) == "zerotier"]


def _find_tailscale_cli() -> Optional[str]:
    candidates = [
        "tailscale",
        r"C:\Program Files\Tailscale\tailscale.exe",
        r"C:\Program Files (x86)\Tailscale\tailscale.exe",
    ]
    for exe in candidates:
        try:
            subprocess.run([exe, "version"], capture_output=True, timeout=3)
            return exe
        except Exception:  # noqa: BLE001
            continue
    return None


def tailscale_hostname() -> Optional[str]:
    """尝试读取 Tailscale MagicDNS 名称（如 machine.tailnet.ts.net），失败返回 None。"""
    exe = _find_tailscale_cli()
    if exe is None:
        return None
    try:
        result = subprocess.run(
            [exe, "status", "--json"], capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout)
        dns_name = (data.get("Self") or {}).get("DNSName") or ""
        return dns_name.rstrip(".") or None
    except Exception:  # noqa: BLE001
        return None
