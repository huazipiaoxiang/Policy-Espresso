"""SourceAdapter 注册表（06 §5.1）。适配器持有 source 配置，与业务代码解耦。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from app.db.models import Source


@dataclass
class ItemRef:
    """discover 只做"发现新条目"。"""
    url: str
    title: str
    published_at_guess: datetime | None = None
    external_id: str = ""


@dataclass
class RawDoc:
    """fetch 只做"取回原始内容"，不做解析。"""
    url: str
    html: bytes
    headers: dict
    published_at_guess: datetime | None = None


class SourceAdapter(Protocol):
    def discover(self, since: datetime | None) -> list[ItemRef]: ...
    def fetch(self, ref: ItemRef) -> RawDoc: ...


_REGISTRY: dict[str, type] = {}


def register(name: str):  # noqa: ANN201
    def deco(cls):  # noqa: ANN001, ANN202
        _REGISTRY[name] = cls
        return cls

    return deco


def get_adapter(source: "Source") -> SourceAdapter:
    from app.ingest.adapters import listing, manual, pdf, rss, sitemap  # noqa: F401 确保注册

    if source.adapter not in _REGISTRY:
        raise KeyError(f"适配器未注册: {source.adapter}")
    return _REGISTRY[source.adapter](source)
