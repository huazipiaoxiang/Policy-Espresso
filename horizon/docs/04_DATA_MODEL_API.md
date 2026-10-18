# 04 · 数据模型与 API 契约

## 1. 实体关系（文字版）

```
source 1─n job_run 1─n document 1─n document_version
document 1─1 policy 1─n assessment 1─n evidence
policy n─n case            (通过 policy_case_link 关联，带相似度)
policy 1─1 scope_judgement
policy 1─n review_task 1─n review_decision
assessment 1─n alert 1─n dispatch
studio_project 1─n proposal 1─n proposal_section
* ── audit_log / llm_call_log
```

## 2. 表结构（关键字段）

### source
| 字段 | 类型 | 说明 |
|---|---|---|
| id | uuid | |
| code | str unique | 如 `hkma_press` |
| name | str | 香港金管局 · 新闻稿 |
| org | str | 发文机构 |
| jurisdiction | enum | `HK / GD / SZ / GBA / CN / MO` |
| tier | int | 1 官方 / 2 媒体 / 3 智库 |
| adapter | enum | `rss / sitemap / listing / pdf / manual` |
| url | str | 入口 |
| config | json | 选择器、分页规则、编码 |
| lang | enum | `zh-Hant / zh-Hans / en` |
| poll_interval_min | int | 默认 30 |
| enabled | bool | |
| health | json | `{last_ok_at, consecutive_fail, success_rate_7d, avg_latency_ms}` |

### document
| 字段 | 类型 | 说明 |
|---|---|---|
| id | uuid | |
| source_id | fk | |
| url / canonical_url | str | canonical 去 utm |
| title | str | |
| lang | enum | |
| published_at | datetime(UTC) | 原文发布时间 |
| fetched_at | datetime(UTC) | |
| content_text | text | 清洗后正文 |
| content_html_path | str | 快照路径（本地卷/OSS） |
| content_hash | str(64) | sha256(正文归一化) |
| simhash | bigint | 近重复 |
| doc_type | enum | `law / regulation / guideline / circular / consultation / press_release / budget / speech / news / report` |
| attachments | json | `[{name, url, local_path, parsed_text_path}]` |
| status | enum | `new / processing / processed / failed / ignored` |

### document_version
`id, document_id, version_no, content_hash, diff_json, changed_at, changed_ratio`

### policy（政策卡片，核心表）
| 字段 | 类型 | 说明 |
|---|---|---|
| id | uuid | |
| document_id | fk unique | |
| title | str | |
| issuing_body | str | 发文机关（可多个） |
| doc_number | str? | 文号 |
| published_at / effective_at / expiry_at | date? | 生效日未知时置 null 并在 UI 标注 |
| jurisdiction | enum | |
| policy_type | enum | 见 02 §5.1 |
| themes | array[str] | 主题标签（受控词表） |
| applicable_entities_text | text | 原文适用主体表述 |
| applicable_scope | enum | `all / domestic_only / foreign_included / qualified_only / unclear` |
| target_entity_status | enum | `covered / excluded / not_mentioned / na` |
| foreign_bank_differential | bool | **外资行差异标记** |
| group_affiliate_mention | json | `{mentioned, entities[], note}`：原文是否点名恒生等集团其他成员。**仅作提示，不参与判定、不触发预警** |
| amounts | json | `[{value, currency, unit, description, span}]` |
| deadlines | json | `[{date, description, span}]` |
| obligations | json | `[{actor, action, condition, span}]` |
| incentives | json | `[{beneficiary, benefit, condition, span}]` |
| summary_zh | text | 200 字内摘要 |
| confidence | float | 抽取整体置信度 |
| status | enum | `draft / ai_checked / pending_review / in_review / approved / rejected / published / archived` |
| priority | enum | `P0 / P1 / P2 / P3` |
| score_total | float | 0–100 |
| prompt_version | str | 用于回溯 |

### assessment（影响评估）
```json
{
  "id": "a_01H...",
  "policy_id": "p_01H...",
  "scores": {
    "relevance":    {"score": 5, "reason": "直接涉及大湾区贷款贴息，汇丰(中国)有对应产品", "evidence_ids": ["e1"]},
    "exposure":     {"score": 4, "reason": "CMB 大湾区制造业贷款余额约 XX 亿（合成数据）", "evidence_ids": ["e2"]},
    "urgency":      {"score": 5, "reason": "2026-11-01 生效，距今 14 天", "evidence_ids": ["e3"]},
    "certainty":    {"score": 5, "reason": "已正式印发，非征求意见稿", "evidence_ids": ["e4"]},
    "actionability":{ "score": 4, "reason": "可在生效前完成客户沟通与定价方案", "evidence_ids": []},
    "differential": { "score": 5, "reason": "适用主体限'境内法人银行'，外资行被排除", "evidence_ids": ["e5"]},
    "compliance":   { "score": 2, "reason": "无额外报备要求", "evidence_ids": []}
  },
  "direction": "negative",
  "score_total": 86.5,
  "priority": "P0",
  "transmission_chain": [
    "贴息仅覆盖内资行 → 内资行实际融资成本低 50-100bps",
    "→ 价格敏感型制造业客户比价",
    "→ 汇丰(中国)大湾区 CMB 贷款续作率下降",
    "→ 利息收入与客户关系双损失"
  ],
  "affected": {
    "business_lines": ["CMB", "GBM-GTB"],
    "segments": ["大湾区制造业中小企业", "有跨境结算需求的外贸客户"],
    "exposure_range": {"low": 8.0, "high": 15.0, "currency": "CNY", "unit": "亿",
                       "basis": "合成数据集口径：符合贴息条件的贷款余额", "confidence": 0.5}
  },
  "recommended_actions": [
    {"owner": "CMB 大湾区团队", "action": "72 小时内对 Top 50 客户做定向沟通，说明综合服务价值", "deadline": "2026-10-24"},
    {"owner": "公共事务", "action": "通过行业协会反馈外资行纳入诉求，参考 2023 年先例", "deadline": "2026-11-15"}
  ],
  "case_links": [{"case_id": "c_gd_2023", "similarity": 0.91, "takeaway": "同类政策曾导致数十亿贷款流失，推动纳入后扭转"}],
  "confidence": 0.78,
  "model": "qwen-max",
  "prompt_version": "impact@v1.3"
}
```

### evidence（证据）
`id, policy_id, assessment_id?, document_id, span_start, span_end, quote, field_name, created_at`
> 强约束：`quote` 必须等于 `content_text[span_start:span_end]`（做空白/全半角归一化后比较），否则整条证据作废。

### scope_judgement
`id, policy_id, entity_id, result(covered/excluded/not_mentioned), rule_hit[], llm_reason, conflict(bool), evidence_ids[]`

### case（历史案例库）
`id, title, year, jurisdiction, themes[], policy_summary, impact, hsbc_response, outcome, lessons[], source_refs[], embedding`

### review_task / review_decision
`task: id, policy_id, level(1|2), assignee, sla_due_at, status, created_at`
`decision: id, task_id, actor, action(approve/reject/request_info), reason_code, note, field_diffs json, created_at`

### alert / dispatch
`alert: id, assessment_id, title, body_md, channel_scope, status(draft/approved/sent)`
`dispatch: id, alert_id, channel, target, sent_at, result`

### studio_project / proposal
`project: id, name, theme, corpus_doc_ids[], constraints json, status`
`proposal: id, project_id, version, sections json, boundary_check json, reviewer_notes`

### audit_log / llm_call_log
`audit: id, actor, action, object_type, object_id, before, after, reason, ip, at`
`llm: id, provider, model, task, prompt_version, input_hash, tokens_in, tokens_out, latency_ms, status, error, at`

## 3. 状态机（显式转移表）

```python
POLICY_TRANSITIONS = {
  "draft":          {"ai_checked", "pending_review", "archived"},
  "ai_checked":     {"pending_review", "archived"},
  "pending_review": {"in_review", "archived"},
  "in_review":      {"approved", "rejected", "needs_info"},
  "needs_info":     {"pending_review", "rejected"},
  "approved":       {"published", "archived"},
  "published":      {"archived"},
  "rejected":       {"archived", "draft"},   # 重开需新建 task
  "archived":       set(),
}
```
规则：
- 只有 `approved` 能进 `published`；`published` 才能被分发。
- `rejected → draft` 必须记录重开原因，且清空旧 assessment（避免污染）。
- 所有转移写 audit_log，禁止直接 UPDATE status。

## 4. API 契约（v1）

### 4.1 约定
- Base：`/api/v1`
- 认证：MVP 用 `X-API-Key`（本地单用户）；云端换 OIDC Bearer，接口不变。
- 分页：`?page=1&page_size=20`，响应 `{items, total, page, page_size}`
- 错误：`{"error": {"code": "SCOPE_CONFLICT", "message": "...", "detail": {...}}}`
- 时间：ISO8601 UTC（`2026-10-17T05:00:00Z`）

### 4.2 端点

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/healthz` | 存活 + 依赖检查 |
| GET | `/sources` | 数据源列表（含 health） |
| POST | `/sources` | 新建源 |
| PATCH | `/sources/{id}` | 启停/改配置 |
| POST | `/sources/{id}/run` | 手动触发抓取（异步，返回 job_id） |
| GET | `/jobs` | 任务运行历史 |
| GET | `/documents` | 文档流（过滤：source/date/status） |
| GET | `/documents/{id}` | 含正文与版本列表 |
| GET | `/documents/{id}/versions/{no}/diff` | 段落级 diff |
| GET | `/policies` | 政策列表（过滤：priority/status/theme/jurisdiction） |
| GET | `/policies/{id}` | 政策全量（含 assessment、evidence、scope） |
| POST | `/policies/{id}/analyze` | 触发/重跑 AI 分析 |
| GET | `/policies/{id}/evidence/{evidence_id}` | 返回原文片段 + 上下文窗口（前端高亮用） |
| POST | `/policies/{id}/submit-review` | 提交审核（校验必填） |
| GET | `/review-tasks` | 我的待审（按 sla 排序） |
| POST | `/review-tasks/{id}/claim` | 领取（防并发双审） |
| POST | `/review-tasks/{id}/decision` | approve / reject / request_info |
| POST | `/policies/{id}/dispatch` | 分发（**未 approved 返回 409**） |
| GET | `/alerts` | 预警列表 |
| GET | `/cases` | 案例库（支持语义检索 `?q=`） |
| GET | `/business-map` | 业务线 × 政策敏感度矩阵 |
| POST | `/studio/projects` | 建政策 2.0 项目 |
| POST | `/studio/projects/{id}/generate` | 生成建议书（异步） |
| GET | `/studio/proposals/{id}` | 建议书详情（含 boundary_check） |
| POST | `/studio/proposals/{id}/review` | 专家/合规双审 |
| GET | `/analytics/overview` | KPI 汇总（今日新增/待审/P0/P1/平均响应） |
| GET | `/admin/audit` | 审计查询（actor/object/date） |
| GET | `/stream/events` | SSE：新政策、任务完成、审核提醒 |

### 4.3 示例：提交审核

```http
POST /api/v1/policies/p_01H/submit-review
Content-Type: application/json

{ "level": 1, "assignee": "analyst.chan", "note": "建议优先处理，涉及 CMB 大湾区" }
```

```json
// 200
{ "task_id": "rt_01H", "sla_due_at": "2026-10-17T09:30:00Z", "status": "pending_review" }
```

```json
// 422 必填缺失
{ "error": { "code": "MISSING_REQUIRED",
  "message": "缺少以下必填项，无法提交审核",
  "detail": { "missing": ["evidence", "recommended_actions"] } } }
```

### 4.4 示例：分发拦截

```json
// 409
{ "error": { "code": "NOT_APPROVED",
  "message": "内容未通过人工审核，禁止分发",
  "detail": { "policy_id": "p_01H", "current_status": "in_review" } } }
```

## 5. 索引与性能

```sql
CREATE INDEX idx_policy_status_priority ON policy(status, priority);
CREATE INDEX idx_policy_published ON policy(published_at DESC);
CREATE INDEX idx_doc_source_pub ON document(source_id, published_at DESC);
CREATE INDEX idx_evidence_policy ON evidence(policy_id);
CREATE INDEX idx_audit_object ON audit_log(object_type, object_id, at DESC);
-- pgvector
CREATE INDEX idx_policy_vec ON policy_chunks USING hnsw (embedding vector_cosine_ops);
-- 全文
CREATE INDEX idx_policy_fts ON policy USING gin (to_tsvector('simple', title || ' ' || coalesce(summary_zh,'')));
```

## 6. 数据字典：主题标签（受控词表，初版 16 个）

跨境支付 · 人民币国际化 · 贷款与贴息 · 跨境理财通 · 债券与资本市场 · 保险与再保险 · 资产管理 · 税务与优惠 · 数据跨境 · 绿色与转型金融 · 金融科技与虚拟资产 · 专业资格互认 · 市场准入与牌照 · 资本与流动性要求 · 消费者保护 · 反洗钱与制裁

> 词表放 `seed/themes.yaml`，新增标签须走审核（避免标签爆炸导致检索失效）。
