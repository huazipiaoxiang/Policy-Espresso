"""站内通知（必有）：落库即达，前端 /alerts 与顶栏徽章消费。"""
from __future__ import annotations


class InAppNotifier:
    name = "inapp"

    def send(self, alert) -> dict:  # noqa: ANN001
        return {"ok": True, "target": "station", "alert_id": alert.id, "note": "站内通知已生成"}
