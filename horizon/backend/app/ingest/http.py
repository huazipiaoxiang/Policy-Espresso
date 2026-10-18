"""抓取礼让层（06 §5.3）：

- 单域名 ≤1 req/s（默认）+ 200–600ms 抖动；夜间（02–06 HKT）放宽到 2 req/s
- 遵守 robots.txt；带可识别 UA
- 429/503 指数退避重试；连续失败由调用方记入 source.health 并熔断
"""
from __future__ import annotations

import random
import threading
import time
import urllib.robotparser
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger("ingest.http")

_HKT = timezone(timedelta(hours=8))

_domain_locks: dict[str, threading.Lock] = {}
_domain_last_hit: dict[str, float] = {}
_robots_cache: dict[str, urllib.robotparser.RobotFileParser | None] = {}


class RobotsDisallowedError(PermissionError):
    pass


class FetchError(RuntimeError):
    """retryable=True 表示网络/限流类错误，可重试；False 为 fatal。"""

    def __init__(self, message: str, *, retryable: bool = True, status: int | None = None):
        super().__init__(message)
        self.retryable = retryable
        self.status = status


@dataclass
class FetchResponse:
    url: str
    status: int
    headers: dict
    content: bytes
    latency_ms: int


def _domain_of(url: str) -> str:
    return urlparse(url).netloc.lower()


def _max_rps() -> float:
    settings = get_settings()
    hour_hkt = datetime.now(_HKT).hour
    if 2 <= hour_hkt < 6:
        return settings.crawl_max_rps_per_domain * 2
    return settings.crawl_max_rps_per_domain


def _throttle(domain: str) -> None:
    lock = _domain_locks.setdefault(domain, threading.Lock())
    with lock:
        last = _domain_last_hit.get(domain, 0.0)
        interval = 1.0 / _max_rps() + random.uniform(0.2, 0.6)
        wait = last + interval - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _domain_last_hit[domain] = time.monotonic()


def _robots_allows(url: str) -> bool:
    if not get_settings().crawl_respect_robots:
        return True
    parsed = urlparse(url)
    root = f"{parsed.scheme}://{parsed.netloc}"
    if root not in _robots_cache:
        rp = urllib.robotparser.RobotFileParser(f"{root}/robots.txt")
        try:
            # 用可识别 UA 抓取 robots.txt：部分站点对 urllib 默认 UA 返回 403，
            # robotparser 会将 403 解释为"全站禁止"，造成误杀
            resp = httpx.get(
                f"{root}/robots.txt", headers={"User-Agent": get_settings().crawl_user_agent}, timeout=10.0
            )
            if resp.status_code in (401, 403):
                rp.disallow_all = True
            elif resp.status_code >= 400:
                rp.allow_all = True  # robots 不存在/不可达时默认允许
            else:
                rp.parse(resp.text.splitlines())
            _robots_cache[root] = rp
        except Exception:
            _robots_cache[root] = None  # robots 不可达时默认允许
    rp = _robots_cache[root]
    if rp is None:
        return True
    return rp.can_fetch(get_settings().crawl_user_agent, url)


def fetch(url: str, *, timeout: float = 30.0, max_retries: int = 3) -> FetchResponse:
    """礼让抓取一个 URL。

    失败模式：robots 禁止 → RobotsDisallowedError；429/503/网络错误重试 max_retries 次后抛 FetchError(retryable=True)；
    其他 4xx 立即抛 FetchError(retryable=False)。
    """
    settings = get_settings()
    if not _robots_allows(url):
        raise RobotsDisallowedError(f"robots.txt 禁止抓取: {url}")

    headers = {"User-Agent": settings.crawl_user_agent, "Accept-Language": "zh-HK,zh;q=0.9,en;q=0.8"}
    backoff = [30.0, 120.0, 600.0]
    last_err: Exception | None = None
    for attempt in range(max_retries):
        _throttle(_domain_of(url))
        started = time.monotonic()
        try:
            resp = httpx.get(url, headers=headers, timeout=timeout, follow_redirects=True)
        except httpx.HTTPError as e:
            last_err = e
            log.warning("fetch_network_error", url=url, attempt=attempt, error=str(e))
            if attempt < max_retries - 1:
                time.sleep(min(backoff[attempt], 5.0))  # 交互运行缩短退避；调度场景由外层重试
            continue
        latency = int((time.monotonic() - started) * 1000)
        if resp.status_code in (429, 503):
            last_err = FetchError(f"HTTP {resp.status_code}", retryable=True, status=resp.status_code)
            log.warning("fetch_rate_limited", url=url, status=resp.status_code, attempt=attempt)
            if attempt < max_retries - 1:
                time.sleep(min(backoff[attempt], 5.0))
            continue
        if 400 <= resp.status_code < 500:
            raise FetchError(f"HTTP {resp.status_code} {url}", retryable=False, status=resp.status_code)
        if resp.status_code >= 500:
            last_err = FetchError(f"HTTP {resp.status_code}", retryable=True, status=resp.status_code)
            continue
        return FetchResponse(
            url=str(resp.url), status=resp.status_code,
            headers={k.lower(): v for k, v in resp.headers.items()},
            content=resp.content, latency_ms=latency,
        )
    raise FetchError(f"重试 {max_retries} 次仍失败: {url}: {last_err}", retryable=True)
