"""Webhook 通知器：邮件 / 企业微信 / 飞书（POST JSON，超时 10s，失败不阻断分发）。"""
from __future__ import annotations

import httpx

from app.core.logging import get_logger

log = get_logger("notifications.webhook")

_TEMPLATES = {
    "email": lambda a: {"subject": a.title, "body_md": a.body_md},
    "wecom": lambda a: {"msgtype": "markdown", "markdown": {"content": f"**{a.title}**\n{a.body_md[:500]}"}},
    "feishu": lambda a: {"msg_type": "text", "content": {"text": f"{a.title}\n{a.body_md[:500]}"}},
}


class WebhookNotifier:
    def __init__(self, channel: str, url: str):
        self.name = channel
        self.url = url

    def send(self, alert) -> dict:  # noqa: ANN001
        payload = _TEMPLATES.get(self.name, _TEMPLATES["email"])(alert)
        try:
            resp = httpx.post(self.url, json=payload, timeout=10.0)
            ok = 200 <= resp.status_code < 300
            return {"ok": ok, "target": self.url[:60], "status_code": resp.status_code}
        except httpx.HTTPError as e:
            log.warning("notify_failed", channel=self.name, error=str(e))
            return {"ok": False, "target": self.url[:60], "error": str(e)}
