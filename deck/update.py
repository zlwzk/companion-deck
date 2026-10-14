"""版本检查：对比当前版本与 GitHub 最新 Release。

成功结果缓存 6 小时，失败结果缓存 10 分钟；网络失败静默降级
（checked=False），绝不阻塞服务启动或 API 响应超过超时上限。
"""

from __future__ import annotations

import json
import re
import time
import urllib.request

from deck import __version__

RELEASES_API = "https://api.github.com/repos/zlwzk/companion-deck/releases/latest"
RELEASES_PAGE = "https://github.com/zlwzk/companion-deck/releases/latest"
_TTL_OK = 6 * 3600
_TTL_FAIL = 600
_cache: dict = {"at": 0.0, "latest": None, "url": None, "checked": False}


def _parse_ver(v: str) -> tuple[int, ...]:
    """'v0.4.0' -> (0, 4, 0)；无法解析时返回 (0,) 保证可比较。"""
    nums = re.findall(r"\d+", v or "")
    return tuple(int(n) for n in nums[:3]) if nums else (0,)


def _result() -> dict:
    latest = _cache["latest"]
    return {
        "current": __version__,
        "latest": latest,
        "update_available": bool(latest) and _parse_ver(latest) > _parse_ver(__version__),
        "url": _cache["url"] or RELEASES_PAGE,
        "checked": _cache["checked"],
    }


def check_latest(timeout: float = 4.0, force: bool = False) -> dict:
    """返回 {current, latest, update_available, url, checked}。

    checked=False 表示本次未能连上 GitHub（离线/被墙），latest 为 None。
    """
    now = time.time()
    if not force and _cache["at"]:
        ttl = _TTL_OK if _cache["checked"] else _TTL_FAIL
        if now - _cache["at"] < ttl:
            return _result()

    latest = None
    url = RELEASES_PAGE
    checked = False
    try:
        req = urllib.request.Request(
            RELEASES_API,
            headers={"User-Agent": "companion-deck", "Accept": "application/vnd.github+json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", "ignore"))
        tag = str(data.get("tag_name") or "").lstrip("vV")
        if tag:
            latest = tag
            url = data.get("html_url") or RELEASES_PAGE
            checked = True
    except Exception:  # noqa: BLE001 离线/被墙一律降级
        pass

    _cache.update(at=now, latest=latest, url=url, checked=checked)
    return _result()
