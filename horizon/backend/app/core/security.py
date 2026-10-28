"""演示环境认证与角色权限。生产环境应以 OIDC 身份替换演示角色请求头。"""
from collections.abc import Callable

from fastapi import Depends, Header

from app.core.config import Settings, get_settings
from app.core.errors import ApiError

DEMO_ROLES = {"admin", "analyst", "approver", "publisher", "consumer"}


async def get_demo_role(x_demo_role: str | None = Header(default=None)) -> str:
    if x_demo_role is None:
        return "analyst"
    if x_demo_role not in DEMO_ROLES:
        raise ApiError("UNAUTHORIZED", "无效的演示角色", 401)
    return x_demo_role


async def require_api_key(
    x_api_key: str | None = Header(default=None),
    x_demo_role: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> str:
    if not x_api_key or x_api_key != settings.api_key:
        raise ApiError("UNAUTHORIZED", "缺少或错误的 X-API-Key", 401)
    role = await get_demo_role(x_demo_role)
    return f"demo.{role}"


def require_roles(*allowed: str) -> Callable:
    async def check_role(role: str = Depends(get_demo_role)) -> str:
        if role not in allowed:
            raise ApiError("FORBIDDEN", "当前角色没有执行此操作的权限", 403)
        return role

    return check_role
