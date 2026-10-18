"""P4 影响分析（max 档）。"""
from __future__ import annotations

import json

from app.ai.chains.base import BaseChain
from app.ai.schemas import IMPACT_SCHEMA


class ImpactChain(BaseChain):
    task = "impact"

    def run(  # noqa: ANN201
        self,
        *,
        content_text: str,
        policy_card: dict,
        scope_judgement: dict,
        similar_cases: list[dict],
        business_map_slice: dict,
        exposure_context: dict,
    ):
        return super().run(
            variables={
                "policy_card": json.dumps(policy_card, ensure_ascii=False, indent=1),
                "scope_judgement": json.dumps(scope_judgement, ensure_ascii=False, indent=1),
                "similar_cases": json.dumps(similar_cases, ensure_ascii=False, indent=1),
                "business_map_slice": json.dumps(business_map_slice, ensure_ascii=False, indent=1),
                "exposure_context": json.dumps(exposure_context, ensure_ascii=False, indent=1),
            },
            content_text=content_text,
            schema=IMPACT_SCHEMA,
            temperature=0.1,
        )
