"""系统设置与运行状态（只读快照）。

设计约束（docs/DECISIONS.md）：
- 进程级配置（LLM Provider / 模型分层 / 存储后端 / 通知 webhook / 抓取参数）由 .env 注入，
  运行期不可热改——本接口只做**脱敏快照展示**，不提供写操作，避免引入运行时可变配置表的安全面。
- 密钥类字段（API Key / AK/SK / webhook 完整 URL）一律脱敏，只返回「是否已配置」。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ai.provider import get_provider
from app.core.config import Settings, get_settings
from app.core.security import require_api_key, require_roles
from app.db.session import get_db

router = APIRouter(prefix="/settings", tags=["settings"], dependencies=[Depends(require_api_key), Depends(require_roles("admin"))])


def _mask_webhook(value: str) -> str:
    """webhook 只暴露「已配置/未配置」，不返回完整 URL（避免泄露鉴权 token）。"""
    return "configured" if value else ""


@router.get("")
def get_system_settings(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    provider = get_provider()

    # 运行时依赖状态（与 /healthz 同一口径）
    db_ok = True
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        db_ok = False

    return {
        "runtime": {
            "db": "ok" if db_ok else "fail",
            "llm_provider": provider.name,
            "storage_backend": settings.storage_backend,
            "scheduler": "apscheduler",  # 默认；FC 触发二选一，见 DECISIONS
            "timezone": settings.tz_display,
            "version": "0.1.0",
        },
        "llm": {
            "provider": settings.llm_provider,
            "model_tier": {
                "classify": settings.model_for_task("classify"),
                "extract": settings.model_for_task("extract"),
                "impact": settings.model_for_task("impact"),
                "studio": settings.model_for_task("studio"),
            },
            "dashscope_configured": bool(settings.dashscope_api_key),
            "ollama_base_url": settings.ollama_base_url,
        },
        "storage": {
            "backend": settings.storage_backend,
            # 本地文件系统路径属基础设施细节，脱敏为「是否已配置」，不暴露服务器路径
            "storage_dir_configured": bool(settings.storage_dir),
            "oss_configured": bool(settings.oss_access_key_id and settings.oss_access_key_secret),
            "oss_bucket": settings.oss_bucket or "",
        },
        "crawl": {
            "user_agent": settings.crawl_user_agent,
            "max_rps_per_domain": settings.crawl_max_rps_per_domain,
            "respect_robots": settings.crawl_respect_robots,
            "max_attachments_per_doc": settings.crawl_max_attachments_per_doc,
            "max_items_per_source": settings.crawl_max_items_per_source,
        },
        "notify": {
            "inapp": "configured",  # 站内通知始终在场
            "email": _mask_webhook(settings.notify_email_webhook),
            "wecom": _mask_webhook(settings.notify_wecom_webhook),
            "feishu": _mask_webhook(settings.notify_feishu_webhook),
        },
        "security": {
            "auth": "api_key" if settings.api_key else "none",
            "job_trigger_token_configured": bool(settings.job_trigger_token),
        },
    }
