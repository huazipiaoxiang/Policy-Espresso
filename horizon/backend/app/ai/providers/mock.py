"""MockProvider：离线确定性输出，供测试与无网环境（03 §5）。

优先从 tests/fixtures/mock_responses/<task>.json 读取按 input_hash 索引的应答；
无匹配时返回内置保底应答，保证 CI 可跑、结果确定。
"""
from __future__ import annotations

import json
from pathlib import Path

from app.ai.provider import LLMResult, input_hash

_FIXTURE_DIR = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "mock_responses"

_FALLBACKS: dict[str, object] = {
    "classify": {"is_financial_policy": True, "policy_type": "press_release", "jurisdictions": ["HK"],
                 "themes": [], "reason": "mock：默认按金融新闻稿处理", "confidence": 0.9},
    "extract": {"title": "", "issuing_bodies": [], "themes": [], "summary_zh": "",
                "confidence": 0.5, "applicable_scope": "unclear"},
    "scope": {"results": [], "foreign_bank_differential": False,
              "group_affiliate_mention": {"mentioned": False, "entities": [], "note": ""}},
    "impact": {
        "scores": {d: {"score": None, "reason": "mock：无依据", "evidence_ids": []} for d in
                   ["relevance", "exposure", "urgency", "certainty", "actionability", "differential", "compliance"]},
        "direction": "neutral", "transmission_chain": [], "confidence": 0.0,
        "affected": {"business_lines": [], "segments": []},
    },
    "case": {"similar_cases": [], "note": "mock：无先例声明"},
    "studio": {"proposals": [], "boundary_check": {"status": "warn", "notes": ["mock 输出，仅供开发"]}},
    # 文本输出链路：满足 alert 六段结构校验，避免 mock 模式下分析因校验失败而中断
    "alert": "【一句话结论】mock：暂无法生成有效预警，需接入真实 AI 分析\n"
             "【影响对象】待定\n【机制】待定\n【建议动作】待人工复核\n【证据】无\n【置信度】低",
    # Chat Agent：mock 不参与规划（无法从 prompt 反推用户问题），返回空结构让调用方走规则回退。
    "chat_plan": {"standalone_question": "", "intent": "lookup", "queries": [], "needs_web": False},
    "chat_answer": {"reply": "", "answer_mode": "general", "citation_ids": [], "followups": []},
}


class MockProvider:
    name = "mock"

    def __init__(self, fixture_dir: Path | None = None):
        self.fixture_dir = fixture_dir or _FIXTURE_DIR

    def complete(
        self,
        *,
        system: str,
        user: str,
        schema: dict | None = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        model: str | None = None,
        task: str = "extract",
    ) -> LLMResult:
        digest = input_hash(system, user)
        parsed = self._lookup(task, digest)
        if parsed is None:
            parsed = _FALLBACKS.get(task, {"ok": True})
        if isinstance(parsed, str):
            # 文本输出链路（如 alert）：fixture 值即正文
            return LLMResult(
                text=parsed, parsed=None,
                usage={"prompt_tokens": 0, "completion_tokens": 0},
                latency_ms=1, model="mock-deterministic",
                raw={"mock": True, "input_hash": digest},
            )
        return LLMResult(
            text=json.dumps(parsed, ensure_ascii=False),
            parsed=parsed,
            usage={"prompt_tokens": 0, "completion_tokens": 0},
            latency_ms=1,
            model="mock-deterministic",
            raw={"mock": True, "input_hash": digest},
        )

    def complete_messages(
        self,
        *,
        system: str,
        messages: list[dict],
        schema: dict | None = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        model: str | None = None,
        task: str = "",
    ) -> LLMResult:
        """多轮：展平为单条 user 文本后复用查表逻辑，保证 mock 行为确定且与轮次无关。"""
        flattened = "\n\n".join(
            f"[{str(message.get('role') or 'user')}] {str(message.get('content') or '')}"
            for message in messages
        )
        return self.complete(
            system=system, user=flattened, schema=schema,
            temperature=temperature, max_tokens=max_tokens, model=model, task=task,
        )

    def _lookup(self, task: str, digest: str) -> dict | str | None:
        path = self.fixture_dir / f"{task}.json"
        if not path.exists():
            return None
        try:
            table = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        return table.get(digest) or table.get("__default__")

    def embed(self, texts: list[str]) -> list[list[float]]:
        # 确定性伪嵌入：按文本 hash 生成 8 维单位向量占位（Phase 2 换真嵌入）
        import hashlib

        out = []
        for t in texts:
            h = hashlib.sha256(t.encode()).digest()
            vec = [b / 255.0 for b in h[:8]]
            out.append(vec)
        return out
