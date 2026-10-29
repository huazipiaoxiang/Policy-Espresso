"""测试用可控 Provider：按 prompt 内容返回场景化响应（反向用例 N1/N7）。"""
from __future__ import annotations

import json

from app.ai.provider import LLMResult


class FakeProvider:
    name = "fake"

    def __init__(self, scene: str = "n1"):
        self.scene = scene

    def complete(self, *, system, user, schema=None, temperature=0.1, max_tokens=4096, model=None, task=""):  # noqa: ANN001, ANN201
        if task == "classify":
            parsed = {"is_financial_policy": True, "policy_type": "circular",
                      "jurisdictions": ["GD"], "themes": ["贷款与贴息"],
                      "reason": "银行业支持制造业通知", "confidence": 0.9}
        elif task == "extract":
            if self.scene == "n1":
                parsed = {
                    "title": "关于辖内银行业金融机构支持制造业发展的通知",
                    "issuing_bodies": ["广东省财政厅"], "themes": ["贷款与贴息"],
                    "applicable_scope": "all",
                    "applicable_entities_text": "本通知适用于辖内所有银行业金融机构。",
                    "summary_zh": "鼓励辖内银行业金融机构加大对制造业的信贷投放。",
                    "evidence": [{"field": "applicable_scope", "quote": "本通知适用于辖内所有银行业金融机构。", "paragraph_index": 0}],
                    "confidence": 0.88,
                }
            else:  # n7：恒生点名
                parsed = {
                    "title": "关于恒生银行参与大湾区金融服务的通告",
                    "issuing_bodies": ["广东省地方金融管理局"], "themes": ["市场准入与牌照"],
                    "applicable_scope": "qualified_only",
                    "applicable_entities_text": "本通告适用于恒生银行在广州地区的业务试点安排。",
                    "summary_zh": "恒生银行广州业务试点安排。",
                    "evidence": [{"field": "applicable_scope", "quote": "本通告适用于恒生银行在广州地区的业务试点安排。", "paragraph_index": 0}],
                    "confidence": 0.85,
                }
        elif task == "scope":
            if self.scene == "n1":
                parsed = {
                    "results": [
                        {"entity_id": "hsbc_cn", "relevance": "high",
                         "reason": "适用辖内所有银行业金融机构，外商独资法人银行在内",
                         "evidence": [{"quote": "本通知适用于辖内所有银行业金融机构。", "paragraph_index": 0}],
                         "confidence": 0.85},
                        {"entity_id": "hsbc_hk", "relevance": "na", "reason": "境外机构", "evidence": [], "confidence": 0.9},
                    ],
                    "foreign_bank_differential": False,
                    "group_affiliate_mention": {"mentioned": False, "entities": [], "note": ""},
                }
            else:  # n7
                parsed = {
                    "results": [
                        {"entity_id": "hsbc_cn", "relevance": "not_mentioned",
                         "reason": "原文仅点名恒生银行，未提及汇丰实体",
                         "evidence": [{"quote": "本通告适用于恒生银行在广州地区的业务试点安排。", "paragraph_index": 0}],
                         "confidence": 0.9},
                        {"entity_id": "hsbc_hk", "relevance": "not_mentioned", "reason": "原文未提及", "evidence": [], "confidence": 0.9},
                    ],
                    "foreign_bank_differential": False,
                    "differential_note": "",
                    "group_affiliate_mention": {"mentioned": True, "entities": ["恒生银行"],
                                                "note": "原文点名集团其他成员，仅提示，不参与汇丰实体判定"},
                }
        elif task == "impact":
            dims = ["relevance", "exposure", "urgency", "certainty", "actionability", "differential", "compliance"]
            if self.scene == "n1":
                values = {"relevance": 3, "exposure": 2, "urgency": 2, "certainty": 4,
                          "actionability": 2, "differential": 1, "compliance": 1}
            else:
                values = {d: 2 for d in dims}
            parsed = {
                "scores": {d: {"score": values[d], "reason": "fake", "evidence_ids": []} for d in dims},
                "direction": "neutral",
                "transmission_chain": ["信贷投放鼓励 → 行业竞争格局不变 → 汇丰(中国)存量业务稳定"],
                "affected": {"business_lines": ["CMB"], "segments": ["制造业企业"]},
                "recommended_actions": [{"owner": "CMB", "action": "持续跟踪", "deadline": "2027-01-31"}],
                "case_links": [], "unknowns": ["fake 场景"], "confidence": 0.6,
            }
        elif task == "alert":
            return LLMResult(
                text="【一句话结论】x\n【影响对象】y\n【机制】z\n【建议动作】a\n【证据】b\n【置信度】c",
                parsed=None, usage={"prompt_tokens": 0, "completion_tokens": 0},
                latency_ms=1, model="fake",
            )
        else:
            parsed = {"ok": True}
        return LLMResult(
            text=json.dumps(parsed, ensure_ascii=False), parsed=parsed,
            usage={"prompt_tokens": 0, "completion_tokens": 0},
            latency_ms=1, model="fake",
        )

    def complete_messages(self, *, system, messages, schema=None, temperature=0.1,  # noqa: ANN001, ANN201
                          max_tokens=4096, model=None, task=""):
        """多轮：FakeProvider 不区分轮次，按最后一条 user 内容复用 complete 的场景分支。"""
        last_user = ""
        for message in messages:
            if str(message.get("role") or "") == "user":
                last_user = str(message.get("content") or "")
        return self.complete(
            system=system, user=last_user, schema=schema,
            temperature=temperature, max_tokens=max_tokens, model=model, task=task,
        )

    def embed(self, texts):  # noqa: ANN001, ANN201
        return [[0.0] * 8 for _ in texts]
