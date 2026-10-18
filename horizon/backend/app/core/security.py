"""MVP 认证：X-API-Key 单用户。云端换 OIDC Bearer，路由依赖签名不变。"""
from fastapi import Depends, Header

from app.core.config import Settings, get_settings
from app.core.errors import ApiError


async def require_api_key(
    x_api_key: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> str:
    if not x_api_key or x_api_key != settings.api_key:
        raise ApiError("UNAUTHORIZED", "缺少或错误的 X-API-Key", 401)
    # MVP 阶段 actor 固定；接入 OIDC 后返回 sub
    return "local.analyst"
