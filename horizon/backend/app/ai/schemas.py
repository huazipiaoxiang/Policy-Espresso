"""P1–P5 链路输出 JSON Schema（05 文档，严格模式：禁止额外字段）。"""
from __future__ import annotations

_EVIDENCE_ITEM = {
    "type": "object",
    "required": ["quote"],
    "properties": {
        "quote": {"type": "string"},
        "paragraph_index": {"type": "integer"},
    },
}

CLASSIFY_SCHEMA = {
    "type": "object",
    "required": ["is_financial_policy", "policy_type", "jurisdictions", "themes", "confidence"],
    "properties": {
        "is_financial_policy": {"type": "boolean"},
        "policy_type": {
            "type": "string",
            "enum": ["law", "regulation", "guideline", "circular", "consultation",
                     "press_release", "budget", "speech", "news", "report", "other"],
        },
        "jurisdictions": {"type": "array", "items": {"type": "string"}},
        "themes": {"type": "array", "items": {"type": "string"}},
        "reason": {"type": "string"},
        "confidence": {"type": "number"},
    },
}

EXTRACT_SCHEMA = {
    "type": "object",
    "required": ["title", "issuing_bodies", "themes", "summary_zh", "confidence"],
    "properties": {
        "title": {"type": "string"},
        "issuing_bodies": {"type": "array", "items": {"type": "string"}},
        "doc_number": {"type": ["string", "null"]},
        "published_at": {"type": ["string", "null"]},
        "effective_at": {"type": ["string", "null"]},
        "expiry_at": {"type": ["string", "null"]},
        "applicable_entities_text": {"type": ["string", "null"]},
        "applicable_scope": {
            "type": "string",
            "enum": ["all", "domestic_only", "foreign_included", "qualified_only", "unclear"],
        },
        "targets": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name", "category"],
                "properties": {
                    "name": {"type": "string"},
                    "category": {"type": "string",
                                 "enum": ["bank", "insurer", "securities_firm", "fund", "corporate", "individual", "other"]},
                },
            },
        },
        "amounts": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["value", "currency", "unit", "description", "quote"],
                "properties": {
                    "value": {"type": "number"},
                    "currency": {"type": "string"},
                    "unit": {"type": "string"},
                    "description": {"type": "string"},
                    "quote": {"type": "string"},
                },
            },
        },
        "deadlines": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["date", "description", "quote"],
                "properties": {"date": {"type": "string"}, "description": {"type": "string"}, "quote": {"type": "string"}},
            },
        },
        "obligations": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["actor", "action", "condition", "quote"],
                "properties": {"actor": {"type": "string"}, "action": {"type": "string"},
                               "condition": {"type": "string"}, "quote": {"type": "string"}},
            },
        },
        "incentives": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["beneficiary", "benefit", "condition", "quote"],
                "properties": {"beneficiary": {"type": "string"}, "benefit": {"type": "string"},
                               "condition": {"type": "string"}, "quote": {"type": "string"}},
            },
        },
        "themes": {"type": "array", "items": {"type": "string"}},
        "summary_zh": {"type": "string"},
        "evidence": {"type": "array", "items": _EVIDENCE_ITEM},
        "confidence": {"type": "number"},
    },
}

SCOPE_SCHEMA = {
    "type": "object",
    "required": ["results", "foreign_bank_differential"],
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["entity_id", "result", "reason", "evidence"],
                "properties": {
                    "entity_id": {"type": "string", "enum": ["hsbc_hk", "hsbc_cn"]},
                    "result": {"type": "string", "enum": ["covered", "excluded", "not_mentioned", "na"]},
                    "reason": {"type": "string"},
                    "evidence": {"type": "array", "items": _EVIDENCE_ITEM},
                    "confidence": {"type": "number"},
                },
            },
        },
        "foreign_bank_differential": {"type": "boolean"},
        "differential_note": {"type": "string"},
        "group_affiliate_mention": {
            "type": "object",
            "required": ["mentioned", "entities"],
            "properties": {
                "mentioned": {"type": "boolean"},
                "entities": {"type": "array", "items": {"type": "string"}},
                "note": {"type": "string"},
            },
        },
        "ambiguity": {"type": "array", "items": {"type": "string"}},
    },
}

_DIM = {
    "type": "object",
    "required": ["reason"],
    "properties": {
        "score": {"type": ["integer", "null"]},
        "reason": {"type": "string"},
        "evidence_ids": {"type": "array", "items": {"type": "string"}},
    },
}

IMPACT_SCHEMA = {
    "type": "object",
    "required": ["scores", "direction", "transmission_chain", "affected", "confidence"],
    "properties": {
        "scores": {
            "type": "object",
            "required": ["relevance", "exposure", "urgency", "certainty", "actionability", "differential", "compliance"],
            "properties": {d: _DIM for d in
                           ["relevance", "exposure", "urgency", "certainty", "actionability", "differential", "compliance"]},
        },
        "direction": {"type": "string", "enum": ["positive", "negative", "mixed", "neutral"]},
        "transmission_chain": {"type": "array", "items": {"type": "string"}},
        "affected": {
            "type": "object",
            "required": ["business_lines", "segments"],
            "properties": {
                "business_lines": {"type": "array", "items": {"type": "string"}},
                "segments": {"type": "array", "items": {"type": "string"}},
                "exposure_range": {
                    "type": ["object", "null"],
                    "properties": {
                        "low": {"type": "number"},
                        "high": {"type": "number"},
                        "currency": {"type": "string"},
                        "unit": {"type": "string"},
                        "basis": {"type": "string"},
                        "confidence": {"type": "number"},
                    },
                },
            },
        },
        "recommended_actions": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["owner", "action", "deadline"],
                "properties": {"owner": {"type": "string"}, "action": {"type": "string"}, "deadline": {"type": "string"}},
            },
        },
        "case_links": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["case_id", "similarity"],
                "properties": {"case_id": {"type": "string"}, "similarity": {"type": "number"}, "takeaway": {"type": "string"}},
            },
        },
        "unknowns": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "number"},
    },
}


STUDIO_SCHEMA = {
    "type": "object",
    "required": ["title", "disclaimer", "baseline", "proposals", "boundary_check"],
    "properties": {
        "title": {"type": "string"},
        "disclaimer": {"type": "string"},
        "baseline": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["theme", "current_state", "key_instruments"],
                "properties": {
                    "theme": {"type": "string"},
                    "current_state": {"type": "string"},
                    "key_instruments": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "gaps": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["theme", "gap"],
                "properties": {"theme": {"type": "string"}, "gap": {"type": "string"}, "benchmark": {"type": "string"}},
            },
        },
        "proposals": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "theme", "tier", "current_basis", "non_conflict_argument",
                             "draft_clause", "impact", "risks", "kpis"],
                "properties": {
                    "id": {"type": "string"},
                    "theme": {"type": "string"},
                    "tier": {"type": "string", "enum": ["渐进", "突破", "结构性"]},
                    "current_basis": {
                        "type": "array",
                        "minItems": 1,
                        "items": {
                            "type": "object",
                            "required": ["doc", "clause", "quote"],
                            "properties": {"doc": {"type": "string"}, "clause": {"type": "string"},
                                           "quote": {"type": "string"}},
                        },
                    },
                    "non_conflict_argument": {"type": "string"},
                    "draft_clause": {"type": "string"},
                    "impact": {
                        "type": "object",
                        "required": ["on_hk", "on_hsbc", "on_industry"],
                        "properties": {"on_hk": {"type": "string"}, "on_hsbc": {"type": "string"},
                                       "on_industry": {"type": "string"}},
                    },
                    "risks": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["risk", "mitigation", "likelihood"],
                            "properties": {"risk": {"type": "string"}, "mitigation": {"type": "string"},
                                           "likelihood": {"type": "string", "enum": ["low", "mid", "high"]}},
                        },
                    },
                    "kpis": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                    "precedents": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "boundary_check": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["proposal_id", "status"],
                "properties": {
                    "proposal_id": {"type": "string"},
                    "status": {"type": "string", "enum": ["pass", "warn", "fail"]},
                    "issue": {"type": "string"},
                    "suggestion": {"type": "string"},
                },
            },
        },
    },
}
