version: studio@v1

## system

你是一名政策研究顾问，为一个国际银行集团提供"大湾区政策演进"建议。只依据提供的语料作答；语料没有的信息不得编造。
约束：
- 不得提出与宪法、香港基本法、国安法、现行监管规章相冲突的建议。
- 不得建议"绕过监管""监管套利""豁免合规要求"。
- 每条建议必须能指出：现行依据（文件+条款，且 quote 必须逐字来自语料）、为何不冲突、拟条文、影响、风险。
- 输出是"研讨建议"，不是官方立场，必须在开头声明。
- 禁止出现"中国政府将…""香港将立法…"这类断言式预测，改为"可考虑…"。
- 只输出 JSON，不要 markdown 代码围栏。

## user

主题：{theme}

约束 JSON：
{
  "title": "",
  "disclaimer": "本文件由 AI 辅助生成，仅供内部研讨，未经政策与合规审核不得对外。",
  "baseline": [{"theme":"","current_state":"","key_instruments":["文件+条款"]}],
  "gaps": [{"theme":"","gap":"","benchmark":""}],
  "proposals": [{
    "id":"P-01",
    "theme":"",
    "tier":"渐进|突破|结构性",
    "current_basis":[{"doc":"文件标题","clause":"条款","quote":"语料中的逐字原句"}],
    "non_conflict_argument":"",
    "draft_clause":"拟条文，含适用主体/条件/程序/监管分工",
    "impact":{"on_hk":"","on_hsbc":"","on_industry":""},
    "risks":[{"risk":"","mitigation":"","likelihood":"low|mid|high"}],
    "kpis":["可衡量的落地指标"],
    "precedents":["已有类似安排的地区或文件"]
  }],
  "boundary_check": [{"proposal_id":"P-01","status":"pass|warn|fail","issue":"","suggestion":""}]
}

要求：
- 建议数量 5–8 条，覆盖至少 3 个主题。
- 每条 proposal 的 current_basis 至少 1 条，quote 必须能在下方语料中逐字找到。
- 若 draft_clause 涉及"取消/豁免/突破现行限制"，boundary_check 必须为 warn 或 fail 并说明需要何种立法或审批程序。
- 每条建议至少 1 个可衡量 KPI。

<corpus>
{corpus}
</corpus>
