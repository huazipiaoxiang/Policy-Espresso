"""统一错误格式：{"error": {"code", "message", "detail"}}（04 §4.1）。"""
import logging
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

log = logging.getLogger("app.errors")


class ApiError(Exception):
    def __init__(self, code: str, message: str, status: int = 400, detail: dict[str, Any] | None = None):
        self.code = code
        self.message = message
        self.status = status
        self.detail = detail or {}
        super().__init__(message)


def error_body(code: str, message: str, detail: dict[str, Any] | None = None) -> dict:
    return {"error": {"code": code, "message": message, "detail": detail or {}}}


async def api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(status_code=exc.status, content=error_body(exc.code, exc.message, exc.detail))


async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    """未捕获异常兜底：返回统一 JSON 而非纯文本 500，前端才能解析出具体错误。"""
    log.error("unhandled_error: %s: %s", type(exc).__name__, exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content=error_body("INTERNAL_ERROR", f"服务器内部错误：{type(exc).__name__}: {exc}"),
    )


# 常用错误
def not_found(what: str, object_id: str) -> ApiError:
    return ApiError("NOT_FOUND", f"{what} 不存在", 404, {"id": object_id})


def not_approved(policy_id: str, current_status: str) -> ApiError:
    return ApiError(
        "NOT_APPROVED",
        "内容未通过人工审核，禁止分发",
        409,
        {"policy_id": policy_id, "current_status": current_status},
    )
