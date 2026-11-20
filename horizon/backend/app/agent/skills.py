"""Agent Skill 注册表：把能力（工具集 + 权限）打包成可复用的技能。

- `policy_preprocess`：原文 → 政策字段收尾 + 预处理（读原文/业务图谱/客户暴露，算百分比，公开检索，写预处理）。
- `irrelevant_policy_cleanup`：判定对汇丰完全没有影响的政策，删除政策与原文（确定性门禁 + 删除工具）。

权限模型统一为「除数据外泄外全开」，Skill 只声明自己用到的能力子集。
"""
from __future__ import annotations

from dataclasses import dataclass

from app.agent.permissions import DELETE, PUBLIC_EGRESS, READ, WRITE


@dataclass(frozen=True)
class Skill:
    name: str
    label: str
    description: str
    tools: tuple[str, ...]
    permissions: frozenset[str]


PREPROCESS = Skill(
    name="policy_preprocess",
    label="政策预处理",
    description="读取原文、业务图谱与客户暴露，复核业务线/客群并提交预处理结论；百分比由平台口径计算。",
    tools=(
        "read_policy",
        "read_document",
        "read_business_map",
        "read_customer_exposure",
        "compute_percentages",
        "refresh_policy_fields",
        "search_public_web",
        "save_preprocess",
    ),
    permissions=frozenset({READ, WRITE, PUBLIC_EGRESS}),
)

IRRELEVANT_CLEANUP = Skill(
    name="irrelevant_policy_cleanup",
    label="无关政策清理",
    description="判定政策对汇丰银行是否完全没有影响；确认无影响时删除政策及原文，仅保留审计痕迹。",
    tools=(
        "read_policy",
        "check_hsbc_impact",
        "delete_irrelevant_policy",
    ),
    permissions=frozenset({READ, DELETE}),
)

SKILLS: tuple[Skill, ...] = (PREPROCESS, IRRELEVANT_CLEANUP)

_BY_NAME = {skill.name: skill for skill in SKILLS}


def get_skill(name: str) -> Skill:
    return _BY_NAME[name]


def describe_skills() -> list[dict]:
    return [
        {
            "name": skill.name,
            "label": skill.label,
            "description": skill.description,
            "tools": list(skill.tools),
            "permissions": sorted(skill.permissions),
        }
        for skill in SKILLS
    ]
