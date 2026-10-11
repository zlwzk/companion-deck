"""地址分类单元测试（不依赖真实网络环境）。"""

from deck.lan import classify_ip


def test_classify_tailscale_range():
    assert classify_ip("100.64.0.1") == "tailscale"
    assert classify_ip("100.101.102.103") == "tailscale"
    assert classify_ip("100.127.255.254") == "tailscale"


def test_classify_zerotier_range():
    assert classify_ip("25.0.0.1") == "zerotier"
    assert classify_ip("25.25.25.25") == "zerotier"
    assert classify_ip("25.255.255.254") == "zerotier"


def test_classify_lan_private_ranges():
    assert classify_ip("192.168.1.5") == "lan"
    assert classify_ip("10.0.0.1") == "lan"
    assert classify_ip("172.16.0.1") == "lan"
    assert classify_ip("172.31.255.254") == "lan"


def test_classify_loopback_and_public():
    assert classify_ip("127.0.0.1") == "loopback"
    assert classify_ip("8.8.8.8") == "other"
    assert classify_ip("not-an-ip") == "other"
