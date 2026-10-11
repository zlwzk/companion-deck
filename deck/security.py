"""访问口令校验（FastAPI 依赖）。"""

from __future__ import annotations

import hmac
from typing import Callable

from fastapi import Header, HTTPException, Query


def make_auth_dep(get_token: Callable[[], str | None]):
    """构造一个 FastAPI 依赖：校验 Bearer Token 或 ?token= 查询参数。"""

    def dependency(
        authorization: str | None = Header(default=None),
        token: str | None = Query(default=None),
    ) -> None:
        expected = get_token()
        if expected is None:
            return  # 未开启鉴权
        provided = token
        if provided is None and authorization:
            scheme, _, value = authorization.partition(" ")
            if scheme.lower() == "bearer":
                provided = value.strip()
        if not provided or not hmac.compare_digest(provided, expected):
            raise HTTPException(status_code=401, detail="unauthorized")

    return dependency
