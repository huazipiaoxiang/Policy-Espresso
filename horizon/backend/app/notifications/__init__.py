"""Notifier 抽象（03 §3.4）：站内必做；邮件/企微/飞书走 webhook，未配置时降级为站内。"""
from __future__ import annotations

from app.core.config import get_settings
from app.notifications.inapp import InAppNotifier


def get_notifiers() -> list:
    """按配置返回可用通知器。InApp 始终在场；webhook 未配置则跳过（降级站内）。"""
    settings = get_settings()
    notifiers = [InAppNotifier()]
    if settings.notify_email_webhook:
        from app.notifications.webhook import WebhookNotifier

        notifiers.append(WebhookNotifier("email", settings.notify_email_webhook))
    if settings.notify_wecom_webhook:
        from app.notifications.webhook import WebhookNotifier

        notifiers.append(WebhookNotifier("wecom", settings.notify_wecom_webhook))
    if settings.notify_feishu_webhook:
        from app.notifications.webhook import WebhookNotifier

        notifiers.append(WebhookNotifier("feishu", settings.notify_feishu_webhook))
    return notifiers
