"""链路基类：prompt 加载 → 渲染 → 调用 → Schema 校验 → 证据校验 → 重试 → llm_call_log。

失败模式（05 §0.3 四道闸）：
- JSON/Schema 失败：重试 1 次，再失败抛 ChainValidationError（调用方落 dead_letter）；
- 证据定位失败：该条证据丢弃（不阻断），结论引用了被丢证据的字段置 null；
- 注入防护：抓取内容经 guard.wrap_untrusted 包裹。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.ai import guard
from app.ai.evidence import locate_quote
from app.ai.provider import LLMProvider, get_provider, input_hash
from app.core.logging import get_logger

log = get_logger("ai.chain")

PROMPT_DIR = Path(__file__).resolve().parents[1] / "prompts"


class ChainValidationError(ValueError):
    pass


@dataclass
class ChainResult:
    task: str
    prompt_version: str
    parsed: dict
    text: str = ""  # markdown/文本输出（schema=None 时使用）
    evidence: list[dict] = field(default_factory=list)  # [{field, quote, span_start, span_end}]
    rejected_evidence: list[dict] = field(default_factory=list)
    model: str = ""
    latency_ms: int = 0
    usage: dict = field(default_factory=dict)  # prompt/completion tokens
    input_hash: str = ""


def load_prompt(name: str) -> tuple[str, str, str]:
    """读取 p*.md，返回 (version, system, user_template)。"""
    path = PROMPT_DIR / f"{name}.md"
    text = path.read_text(encoding="utf-8")
    version = ""
    system, user = "", ""
    section = None
    for line in text.splitlines():
        if line.startswith("version:"):
            version = line.split(":", 1)[1].strip()
        elif line.startswith("## system"):
            section = "system"
        elif line.startswith("## user"):
            section = "user"
        elif section == "system":
            system += line + "\n"
        elif section == "user":
            user += line + "\n"
    return version, system.strip(), user.strip()


class BaseChain:
    """五链路共用骨架。子类提供 task 名与 schema。"""

    task = "base"

    def __init__(self, provider: LLMProvider | None = None):
        self.provider = provider or get_provider()

    def run(
        self,
        *,
        variables: dict[str, Any],
        content_text: str,
        schema: dict | None,
        temperature: float = 0.1,
    ) -> ChainResult:
        version, system, user_template = load_prompt(self._prompt_name())
        user = user_template
        for key, value in variables.items():
            user = user.replace("{" + key + "}", str(value))

        last_err: Exception | None = None
        for attempt in range(2):  # Schema 失败重试 1 次
            started = time.monotonic()
            try:
                result = self.provider.complete(
                    system=system, user=user, schema=schema,
                    temperature=temperature, task=self.task,
                )
            except Exception as e:  # 网络/Provider 错误：不重试 prompt，直接上抛
                self._log_call(version, "", "error", started, 0, 0, str(e))
                raise
            latency_ms = int((time.monotonic() - started) * 1000)

            # 文本输出链路（schema=None，如预警草稿）：不做 JSON 校验
            if schema is None:
                usage = result.usage or {}
                self._log_call(version, result.model, "ok", started,
                               usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0), None)
                return ChainResult(
                    task=self.task, prompt_version=version, parsed={},
                    text=result.text, model=result.model, latency_ms=latency_ms,
                    usage=usage, input_hash=input_hash(system, user),
                )

            parsed = result.parsed
            if parsed is None:
                last_err = ChainValidationError(f"{self.task}: 输出无法解析为 JSON")
                self._log_call(version, result.model, "bad_json", started, 0, 0, str(last_err))
                continue
            try:
                guard.validate_schema(parsed, schema)
            except guard.SchemaValidationError as e:
                last_err = ChainValidationError(f"{self.task}: Schema 校验失败: {e}")
                self._log_call(version, result.model, "schema_fail", started, 0, 0, str(e))
                continue
            usage = result.usage or {}
            self._log_call(version, result.model, "ok", started,
                           usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0), None)
            evidence, rejected = self._verify_evidence(parsed, content_text)
            return ChainResult(
                task=self.task, prompt_version=version, parsed=parsed,
                evidence=evidence, rejected_evidence=rejected,
                model=result.model, latency_ms=latency_ms,
                usage=usage, input_hash=input_hash(system, user),
            )
        raise last_err or ChainValidationError(f"{self.task}: 未知失败")

    def _prompt_name(self) -> str:
        return {"classify": "p1_classify", "extract": "p2_extract", "scope": "p3_scope",
                "impact": "p4_impact", "alert": "p5_alert", "studio": "p6_studio"}[self.task]

    def _verify_evidence(self, parsed: dict, content_text: str) -> tuple[list[dict], list[dict]]:
        """通用：提取 parsed 中所有含 quote 的条目，定位 span；失败入 rejected。

        子类可覆盖以按字段名归集。定位失败 → 该条证据作废（不阻断）。
        """
        evidence, rejected = [], []
        self._walk(parsed, content_text, "", evidence, rejected)
        return evidence, rejected

    def _walk(self, node, content_text: str, field: str, evidence: list, rejected: list) -> None:  # noqa: ANN001
        if isinstance(node, dict):
            quote = node.get("quote")
            if isinstance(quote, str) and quote:
                span = locate_quote(content_text, quote)
                item = {"field": field, "quote": quote}
                if span:
                    item.update({"span_start": span[0], "span_end": span[1]})
                    evidence.append(item)
                else:
                    rejected.append(item)
            for key, value in node.items():
                self._walk(value, content_text, key, evidence, rejected)
        elif isinstance(node, list):
            for value in node:
                self._walk(value, content_text, field, evidence, rejected)

    def _log_call(self, prompt_version: str, model: str, status: str, started: float,
                  tokens_in: int, tokens_out: int, error: str | None) -> None:
        """llm_call_log（01 §七）。持久化在 analyze_job 统一事务内提交，此处落结构化日志。"""
        log.info(
            "llm_call",
            task=self.task, prompt_version=prompt_version, model=model, status=status,
            tokens_in=tokens_in, tokens_out=tokens_out,
            latency_ms=int((time.monotonic() - started) * 1000), error=error,
        )
