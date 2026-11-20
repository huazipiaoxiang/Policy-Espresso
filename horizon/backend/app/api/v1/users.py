"""管理员用户管理：列表 / 新建 / 改角色与密码 / 删除。

账号存于 user 表（username + sha256 密码 + 角色）。仅管理员可读写，
政策使用者与运营专员无法通过该接口查看或修改他人账号。
"""
from __future__ import annotations

import hashlib
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError, not_found
from app.core.security import require_api_key, require_roles
from app.db.models import User
from app.db.session import get_db

router = APIRouter(
    prefix="/admin/users", tags=["users"], dependencies=[Depends(require_api_key)]
)

ROLES = ("admin", "processor", "consumer")
MIN_PASSWORD_LENGTH = 6


def _hash(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _view(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "onboarded": user.onboarded,
        "created_at": _iso(user.created_at),
    }


def _admin_count(db: Session, exclude_id: str | None = None) -> int:
    """剩余管理员数量；exclude_id 用于判断「改掉/删掉这个管理员后是否还有人」。"""
    stmt = select(func.count(User.id)).where(User.role == "admin")
    if exclude_id:
        stmt = stmt.where(User.id != exclude_id)
    return db.scalar(stmt) or 0


class CreateUserBody(BaseModel):
    username: str
    password: str
    role: str = "consumer"


class UpdateUserBody(BaseModel):
    role: str | None = None
    password: str | None = None
    onboarded: bool | None = None


@router.get("")
def list_users(
    q: str | None = None,
    role: str | None = None,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
    _: str = Depends(require_roles("admin")),
) -> dict:
    """用户列表（分页）：支持用户名搜索与角色筛选，并返回各角色数量概览。"""
    page = max(1, page)
    page_size = min(max(1, page_size), 200)
    stmt = select(User)
    count_stmt = select(func.count(User.id))
    if q and q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(User.username.like(like))
        count_stmt = count_stmt.where(User.username.like(like))
    if role:
        stmt = stmt.where(User.role == role)
        count_stmt = count_stmt.where(User.role == role)
    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.order_by(User.created_at.desc(), User.username.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    by_role = {
        name: db.scalar(select(func.count(User.id)).where(User.role == name)) or 0
        for name in ROLES
    }
    return {
        "items": [_view(user) for user in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "summary": {"total": sum(by_role.values()), **by_role},
    }


@router.post("", status_code=201)
def create_user(
    body: CreateUserBody,
    db: Session = Depends(get_db),
    _: str = Depends(require_roles("admin")),
) -> dict:
    username = body.username.strip()
    if not username or len(username) > 64:
        raise ApiError("INVALID_INPUT", "用户名不能为空且不超过 64 个字符", 422)
    if len(body.password) < MIN_PASSWORD_LENGTH:
        raise ApiError("INVALID_INPUT", f"密码至少 {MIN_PASSWORD_LENGTH} 位", 422)
    if body.role not in ROLES:
        raise ApiError("INVALID_ROLE", "无效角色", 422)
    if db.scalar(select(User).where(User.username == username)):
        raise ApiError("USER_EXISTS", "用户名已存在", 409)
    user = User(
        username=username,
        password_hash=_hash(body.password),
        role=body.role,
        # 只有政策使用者需要首次主题引导
        onboarded=body.role != "consumer",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _view(user)


@router.patch("/{user_id}")
def update_user(
    user_id: str,
    body: UpdateUserBody,
    db: Session = Depends(get_db),
    _: str = Depends(require_roles("admin")),
) -> dict:
    """修改角色 / 重置密码 / 标记引导完成。"""
    user = db.get(User, user_id)
    if not user:
        raise not_found("用户", user_id)
    if body.role is not None:
        if body.role not in ROLES:
            raise ApiError("INVALID_ROLE", "无效角色", 422)
        if user.role == "admin" and body.role != "admin" and _admin_count(db, exclude_id=user.id) == 0:
            raise ApiError("INVALID_OPERATION", "至少保留一个管理员账号", 400)
        user.role = body.role
        # 只有政策使用者需要首次主题引导，其他角色视为已引导
        user.onboarded = body.role != "consumer"
    if body.password is not None:
        if len(body.password) < MIN_PASSWORD_LENGTH:
            raise ApiError("INVALID_INPUT", f"密码至少 {MIN_PASSWORD_LENGTH} 位", 422)
        user.password_hash = _hash(body.password)
    if body.onboarded is not None:
        user.onboarded = body.onboarded
    db.commit()
    db.refresh(user)
    return _view(user)


@router.delete("/{user_id}")
def delete_user(
    user_id: str,
    actor: str | None = Query(default=None, description="当前登录用户名，用于阻止删除自己"),
    db: Session = Depends(get_db),
    _: str = Depends(require_roles("admin")),
) -> dict:
    user = db.get(User, user_id)
    if not user:
        raise not_found("用户", user_id)
    if actor and user.username == actor:
        raise ApiError("INVALID_OPERATION", "不能删除当前登录账号", 400)
    if user.role == "admin" and _admin_count(db, exclude_id=user.id) == 0:
        raise ApiError("INVALID_OPERATION", "至少保留一个管理员账号", 400)
    db.delete(user)
    db.commit()
    # 返回 200 + JSON：204 空响应在部分代理链路（Next BFF）会丢失状态码
    return {"deleted": True, "id": user_id}
