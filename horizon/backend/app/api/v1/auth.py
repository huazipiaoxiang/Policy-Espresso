"""注册与登录（MVP：用户名 + 密码 + 角色）。生产应以 OIDC 替换。"""
from __future__ import annotations

import hashlib

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db.models import User
from app.db.session import get_db

router = APIRouter(prefix="/auth", tags=["auth"])

VALID_ROLES = ("admin", "consumer", "processor")


def _hash(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


class RegisterBody(BaseModel):
    username: str
    password: str
    role: str = "consumer"


class LoginBody(BaseModel):
    username: str
    password: str


class ChangePasswordBody(BaseModel):
    username: str
    old_password: str
    new_password: str


@router.post("/register", status_code=201)
def register(body: RegisterBody, db: Session = Depends(get_db)):
    username = body.username.strip()
    if not username or not body.password:
        raise ApiError("INVALID_INPUT", "用户名与密码不能为空", 422)
    if body.role not in VALID_ROLES:
        raise ApiError("INVALID_ROLE", "无效角色", 422)
    existing = db.scalar(select(User).where(User.username == username))
    if existing:
        raise ApiError("USER_EXISTS", "用户名已存在", 409)
    user = User(username=username, password_hash=_hash(body.password), role=body.role)
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"id": user.id, "username": user.username, "role": user.role, "onboarded": user.onboarded}


@router.post("/login")
def login(body: LoginBody, db: Session = Depends(get_db)):
    username = body.username.strip()
    user = db.scalar(select(User).where(User.username == username))
    if not user or user.password_hash != _hash(body.password):
        raise ApiError("BAD_CREDENTIALS", "用户名或密码错误", 401)
    return {"id": user.id, "username": user.username, "role": user.role, "onboarded": user.onboarded}


@router.post("/change-password")
def change_password(body: ChangePasswordBody, db: Session = Depends(get_db)):
    """用户自助改密：验旧密码，设置新密码。MVP 以用户名定位（登录态由前端 sessionStorage 维护）。"""
    username = body.username.strip()
    if len(body.new_password) < 6:
        raise ApiError("INVALID_INPUT", "新密码至少 6 位", 422)
    user = db.scalar(select(User).where(User.username == username))
    if not user or user.password_hash != _hash(body.old_password):
        raise ApiError("BAD_CREDENTIALS", "旧密码错误", 401)
    user.password_hash = _hash(body.new_password)
    db.commit()
    return {"username": user.username, "role": user.role}


@router.post("/onboard")
def onboard(body: LoginBody, db: Session = Depends(get_db)):
    """政策使用者完成首次主题引导后标记 onboarded。MVP 以用户名定位（登录后调用）。"""
    username = body.username.strip()
    user = db.scalar(select(User).where(User.username == username))
    if not user:
        raise ApiError("NOT_FOUND", "用户不存在", 404)
    user.onboarded = True
    db.commit()
    return {"onboarded": True}
