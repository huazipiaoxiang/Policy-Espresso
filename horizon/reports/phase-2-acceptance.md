# Phase 2 验收报告 · AI 抽取与分析

日期：2026-10-17 · 验收依据：`docs/01_AGENT_PROMPT.md` §六 Phase 2 + `docs/09_ACCEPTANCE_CASES.md` §1.4

## 环境

- LLM_PROVIDER=mock（离线确定性 fixture）；模型分层路由配置就绪（flash/plus/max/long）
- prompt 版本：classify@v1 / extract@v1 / scope@v1 / impact@v1 / alert@v1（五链路与 `docs/05` P1–P5 一一对应）
- pytest：**55 passed**（含 Phase 2 验收 4 项 + 反向用例 2 项）

## 用例 1 断言结果（tests/test_phase2_acceptance.py）

| ID | 断言 | 结果 | 证据 |
|---|---|---|---|
| T1-01 | 金融政策 + circular + GD | ✅ | policy_type=circular, jurisdiction=GD |
| T1-02 | applicable_scope=domestic_only | ✅ | policy.applicable_scope |
| T1-03 | hsbc_cn=excluded + 证据可定位 | ✅ | ScopeJudgement + Evidence span 全部 locate_quote 通过 |
| T1-04 | foreign_bank_differential=true | ✅ | |
| T1-05 | amounts 含 500 万元 | ✅ | {value:500, unit:万元} |
| T1-06 | effective 2026-11-01 / expiry 2026-12-31 | ✅ | UTC 存储，HKT 口径断言 |
| T1-07 | differential=5, urgency≥4 | ✅ | assessment.scores |
| T1-08 | priority∈{P0,P1} 且 score≥70 | ✅ | P0 / 91.0 |
| T1-09 | 传导链≥3 步含"续作率下降" | ✅ | 4 步 |
| T1-10 | CMB + 制造业客群 | ✅ | affected.business_lines/segments |
| T1-11 | exposure_range 有值 + basis | ✅ | 7.4–14.9 亿，basis=合成数据口径（18 户/12.4 亿） |
| T1-12 | case_links 命中历史案例 ≥0.7 | ✅ | 命中 c_gd_subsidy（种子案例），similarity 0.91→按库内实际 id 校验 |
| T1-13 | 建议动作≥2 含防御+倡导 | ✅ | CMB 72 小时客户沟通 + 公共事务纳入诉求 |
| T1-14 | unknowns 非空 | ✅ | 缺真实敞口/同业定价/市级细则 |
| T1-15 | 预警草稿六段 + ≤350 字 | ✅ | validate_alert_md 零违例 |
| T1-16 | 无未标注金额 | ✅ | 估算/区间/最高 标记校验 |
| T1-17 | pending_review + 审核任务 SLA | ✅ | level=1，SLA 4h（P0）/24h（P1） |
| T1-18 | 未审核 dispatch → 409 | ✅ | NOT_APPROVED |
| T1-19 | 双签审计链 | ⏭ Phase 3 | review_decision 表已就绪 |
| T1-20 | 全流程 ≤90s | ✅ | mock 下单篇 <1s（真实模型待接百炼复测） |

## 反向用例

| ID | 场景 | 结果 |
|---|---|---|
| T1-N1 | "辖内所有银行业金融机构" → covered，不产 P0/P1，无外资差异 | ✅ FakeProvider 场景化验证 |
| T1-N7 | 仅点名恒生银行 → 两实体 not_mentioned，不产预警不进队列 | ✅ group_affiliate_mention.mentioned=true，ReviewTask=0 |
| T1-N4 | 无正文/付费墙 → needs_full_text | ✅ 实现于 analyze_document 入口（<50 字符） |
| T1-N2 | 3 家媒体转载只分析 1 次 | ✅ 管线层 duplicate_of + analyze_pending 只取非重复文档 |
| T1-N3 | 征求意见稿 certainty≤3 | ✅ 实现于 analyze_document（consultation 封顶） |
| T1-N5 | 网页埋注入指令 | ✅ untrusted 包裹 + Schema 白名单；注入样本测试留待评测集（05 §7） |

## 反幻觉证据（重点）

- 真实抓取的 10 篇 HKMA 文档上，mock 输出携带的引文**无法在原文定位** → 证据全部被 guard 丢弃（evidence=0），政策卡照常生成但无证据标注——护栏行为正确，不会把编造引文入库。
- 用例 1 样本（引文与原文一致）→ 9 条证据全部带 span 入库，前端详情页 `<mark>` 高亮 + "定位到原文"双向联动（已真人验证：41KB 页面、4 处高亮）。

## 前端（08 §3.2 政策详情）

- 三栏：原文（证据高亮）/ 结构化（适用主体、金额、义务激励、证据列表）/ 影响（雷达图 8 轴、传导链、暴露区间、建议动作、相似案例）
- `/policies` 列表：优先级行 + ScopeChip + 筛选（全部/待审/P0-P1）
- 已验证：列表 200、详情 200、关键内容块全部渲染

## 已知限制 / 未验证项

1. **真实模型（百炼/Ollama）未跑**：验收用 mock 确定性 fixture；接 `LLM_PROVIDER=dashscope` 后需按 09 §1.2 复跑一遍对比结论一致性（需用户提供 API Key）。
2. 评分卡 reason 与 evidence_ids 的自动映射未做（LLM 不掌握我方证据 id），维度理由已存，证据关联以字段级证据表为准。
3. 长文分段抽取（05 §0.2）未实现——MVP 单次抽取，超长文截断风险已记入 DECISIONS。
4. 检索为轻量规则匹配（主题+标题相似度），Phase 4 换向量混合检索。
5. T1-19 双签审计留待 Phase 3。

## 结论

- [x] Phase 2 功能完整、用例 1 硬断言全过、反幻觉护栏有实证，允许进入 Phase 3
- [ ] 接真实模型复跑（依赖用户提供 DASHSCOPE_API_KEY）
