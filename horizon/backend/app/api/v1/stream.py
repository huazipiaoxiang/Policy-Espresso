"""SSE 事件流（04 §4.2 /stream/events）：新政策、任务完成、审核提醒。

零依赖实现（text/event-stream 手写格式）；MVP 推送统计增量，间隔 5s。
"""
import asyncio
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import require_api_key
from app.db.models import Policy, ReviewTask
from app.db.session import get_db

router = APIRouter(tags=["stream"], dependencies=[Depends(require_api_key)])


async def _event_generator(db: Session):
    last: tuple[int, int] | None = None
    while True:
        policy_count = db.scalar(select(func.count(Policy.id))) or 0
        pending = db.scalar(select(func.count(ReviewTask.id)).where(ReviewTask.status == "pending")) or 0
        current = (policy_count, pending)
        if current != last:
            last = current
            payload = json.dumps(
                {"policy_total": policy_count, "pending_review": pending,
                 "at": datetime.now(timezone.utc).isoformat()},
                ensure_ascii=False,
            )
            yield f"event: stats\ndata: {payload}\n\n"
        await asyncio.sleep(5)


@router.get("/stream/events")
async def stream_events(db: Session = Depends(get_db)):
    return StreamingResponse(_event_generator(db), media_type="text/event-stream")
