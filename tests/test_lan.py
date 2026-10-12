"""地址分类单元测试（不依赖真实网络环境）。"""

from deck.lan import classify


def test_v4_lan_private_ranges():
    assert classify("192.168.1.5") == "lan"
    assert classify("10.0.0.1") == "lan"
    assert classify("172.16.0.1") == "lan"
    assert classify("172.31.255.254") == "lan"


def test_v4_hotspot_range():
    assert classify("192.168.137.1") == "hotspot"
    assert classify("192.168.137.99") == "hotspot"
    assert classify("192.168.136.1") == "lan"  # 相邻网段不算热点


def test_v4_usb_tethering_range():
    assert classify("192.168.42.129") == "usb"  # Android RNDIS 默认 PC 侧地址
    assert classify("172.20.10.2") == "usb"  # iOS 热点/USB（NCM）默认 PC 侧地址
    assert classify("192.168.43.1") == "lan"  # 相邻网段不算 USB


def test_v4_public_and_loopback():
    assert classify("8.8.8.8") == "public"
    assert classify("114.114.114.114") == "public"
    assert classify("127.0.0.1") == "loopback"


def test_v6_classes():
    assert classify("::1") == "loopback"
    assert classify("fe80::1") == "linklocal"
    assert classify("fd00::1") == "ula"
    assert classify("2408:8207:1234::1") == "global6"
    assert classify("2001:4860:4860::8888") == "global6"


def test_v6_tunnel_not_global():
    # Teredo / 6to4 隧道地址不是公网可直连地址
    assert classify("2001:0:14c9:d502:814:3fcb:8b6b:cbda") == "other"
    assert classify("2002::1") == "other"


def test_invalid_input():
    assert classify("not-an-ip") == "other"
    assert classify("") == "other"
