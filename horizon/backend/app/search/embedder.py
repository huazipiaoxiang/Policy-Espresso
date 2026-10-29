"""嵌入 Provider：DashScope / Ollama / Mock 三选一，缺失或失败时抛 EmbedError。

与 LLMProvider 平行存在（03 §5 的 EmbeddingProvider 约定）：嵌入与生成模型可独立选型，
密钥只走环境变量。所有失败统一收敛为 EmbedError，由调用方降级为纯词法检索。
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

from app.core.config import get_settings

DEFAULT_MODELS = {
    "dashscope": "text-embedding-v3",
    "ollama": "bge-m3",
    "mock": "mock-hash-8d",
}


class EmbedError(RuntimeError):
    """嵌入不可用（未配置 / 网络失败 / 返回结构异常）。调用方降级，不阻断主流程。"""


@dataclass(frozen=True)
class EmbeddingResult:
    vectors: list[list[float]]
    model: str
    latency_ms: int


def resolve_provider_name() -> str:
    """SEARCH_EMBEDDING_PROVIDER 为空时跟随 LLM_PROVIDER，保证默认开箱可用。"""
    settings = get_settings()
    name = (settings.search_embedding_provider or settings.llm_provider or "mock").strip().lower()
    return name if name in DEFAULT_MODELS else "mock"


def _embed_mock(texts: list[str]) -> EmbeddingResult:
    """确定性伪嵌入（与 MockProvider.embed 同实现），仅供离线/CI 保持行为确定。"""
    import hashlib

    started = time.monotonic()
    vectors: list[list[float]] = []
    for text in texts:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        vectors.append([byte / 255.0 for byte in digest[:8]])
    return EmbeddingResult(
        vectors=vectors,
        model=DEFAULT_MODELS["mock"],
        latency_ms=int((time.monotonic() - started) * 1000),
    )


def _embed_http(*, base_url: str, api_key: str, model: str, texts: list[str]) -> EmbeddingResult:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {"model": model, "input": texts}
    started = time.monotonic()
    try:
        resp = httpx.post(f"{base_url.rstrip('/')}/embeddings", headers=headers, json=payload, timeout=30.0)
        resp.raise_for_status()
        raw = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise EmbedError(f"嵌入请求失败：{type(exc).__name__}") from exc
    latency_ms = int((time.monotonic() - started) * 1000)

    rows = raw.get("data") if isinstance(raw, dict) else None
    if not isinstance(rows, list) or not rows:
        raise EmbedError("嵌入返回结构异常：缺少 data")
    vectors: list[list[float]] = []
    for row in rows:
        vector = row.get("embedding") if isinstance(row, dict) else None
        if not isinstance(vector, list) or not vector:
            raise EmbedError("嵌入返回结构异常：缺少 embedding")
        vectors.append([float(value) for value in vector])
    if len(vectors) != len(texts):
        raise EmbedError(f"嵌入条数不匹配：期望 {len(texts)}，得到 {len(vectors)}")
    return EmbeddingResult(vectors=vectors, model=model, latency_ms=latency_ms)


def embed_texts(texts: list[str]) -> EmbeddingResult:
    """批量嵌入。空输入直接返回空结果，不发网络请求。"""
    if not texts:
        return EmbeddingResult(vectors=[], model=DEFAULT_MODELS[resolve_provider_name()], latency_ms=0)

    settings = get_settings()
    name = resolve_provider_name()
    model = settings.search_embedding_model or DEFAULT_MODELS[name]
    clean = [str(text or "")[:4000] for text in texts]

    if name == "mock":
        return _embed_mock(clean)
    if name == "dashscope":
        if not settings.dashscope_api_key:
            raise EmbedError("DASHSCOPE_API_KEY 未配置")
        return _embed_http(base_url=settings.dashscope_base_url, api_key=settings.dashscope_api_key,
                           model=model, texts=clean)
    if name == "ollama":
        # Ollama 的 OpenAI 兼容端点同样暴露 /embeddings
        return _embed_http(base_url=settings.ollama_base_url, api_key="ollama", model=model, texts=clean)
    raise EmbedError(f"未知嵌入 provider：{name}")


def embed_available() -> bool:
    """轻量探活：用于决定是否启用向量通道（不产生真实计费调用之外的开销）。"""
    name = resolve_provider_name()
    if name == "mock":
        return True
    settings = get_settings()
    if name == "dashscope":
        return bool(settings.dashscope_api_key)
    return True
