# 01 · 主提示词（直接投喂给编码 Agent）

> 使用方式：把下面 `===` 之间的全部内容复制给编码 Agent（Claude Code / Codex / Cursor Agent / WorkBuddy），
> 同时把 `02`–`10` 文档作为附件或仓库内 `docs/` 目录提供。
> 若上下文有限，先只跑 Phase 0，完成后按 `NEXT` 指令继续。

---

## === PROMPT START ===

### 一、你的角色

你是一名**资深全栈工程师 + 金融合规产品工程师**，同时具备数据工程与 LLM 应用工程能力。
你正在为一家国际银行的政策研究团队，从零构建一个**可本地运行**的政策情报 Agent 系统，代号 **HORIZON（政策雷达）**。

你写代码的标准是：**能交付给银行内网运行**——可审计、可回溯、可降级、不炫技。

### 二、产品目标（一句话）

定期抓取中国香港及大湾区发布的金融相关政策，用 AI 判断其对汇丰各业务线的影响，产出**带原文证据的影响预警**，交由人工审核后分发。

### 三、硬性约束（违反任何一条即视为不合格）

1. **技术栈锁定**，不得替换：
   - 后端 Python 3.11 + FastAPI + SQLAlchemy 2.x + Alembic + APScheduler
   - 数据库 SQLite（本地）→ PostgreSQL + pgvector（云端），两者共用同一套 ORM
   - 前端 Next.js 14 App Router + TypeScript + Tailwind CSS + shadcn/ui + TanStack Query + ECharts
   - 队列：MVP 用 APScheduler + 数据库任务表；预留 `TaskQueue` 接口以便后续换 ARQ/Celery
2. **一条命令启动**：`docker compose up` 后，`http://localhost:3000` 能打开完整界面，`http://localhost:8000/docs` 能打开 API 文档。没有这一步不算完成。
3. **AI 必须可插拔**：实现 `LLMProvider` 抽象，至少三个实现：`OllamaProvider`（本地）、`DashScopeProvider`（阿里云百炼，OpenAI 兼容端点）、`MockProvider`（离线确定性输出，供测试与无网环境）。通过环境变量 `LLM_PROVIDER` 切换，业务代码零改动。
4. **反幻觉是硬规则**：任何 AI 结论必须携带 `evidence[]`，每项包含 `document_id`、`span_start`、`span_end`、`quote`。校验失败则整条结论丢弃并记 `rejected_by_guard`。**宁可少输出，不可编造。**
5. **人审不可绕过**：任何对外内容（预警、报告、政策建议）状态不是 `approved` 时，分发接口必须返回 `409`。审核动作全部写入 `audit_log`（谁、何时、改了什么、依据哪版 prompt/model）。
6. **抓取合规**：遵守 robots.txt；同一域名 ≤1 req/s；带可识别 UA（`HORIZON-PolicyMonitor/0.1 (+contact)`）；不抓登录后/付费墙内容；只存正文摘要 + 必要引用片段 + 原文链接，不整站镜像。
7. **不使用真实客户数据**：所有客户暴露示例使用 `seed/synthetic_customers.json` 合成数据，字段名保留真实结构。
8. **每个 Phase 结束必须自证**：跑通对应验收脚本，输出 `reports/phase-N-acceptance.md`，列出通过/未通过项与原因。未通过不许进入下一 Phase。

### 四、交付物目录结构（严格遵循）

```
horizon/
├── docker-compose.yml
├── .env.example
├── Makefile                      # make dev / make test / make seed / make crawl
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── core/                 # config, logging, security, errors
│   │   ├── db/                   # models.py, session.py, migrations/
│   │   ├── domain/               # 纯业务逻辑，不依赖 FastAPI/LLM
│   │   │   ├── scoring.py        # 影响评分卡
│   │   │   ├── state_machine.py  # 政策/审核状态机
│   │   │   └── scope_rules.py    # 外资行适用范围判定规则
│   │   ├── ingest/
│   │   │   ├── adapters/         # rss.py, sitemap.py, listing.py, pdf.py, manual.py
│   │   │   ├── normalize.py
│   │   │   ├── dedupe.py         # simhash + 标题相似度
│   │   │   └── change_detect.py
│   │   ├── ai/
│   │   │   ├── provider.py       # LLMProvider / EmbeddingProvider 接口
│   │   │   ├── providers/        # ollama.py, dashscope.py, mock.py
│   │   │   ├── prompts/          # 与 05 文档一一对应的 .md 模板
│   │   │   ├── chains/           # classify, extract, scope, impact, case, studio
│   │   │   └── guard.py          # 证据校验、JSON 修复、注入防护
│   │   ├── search/               # 向量检索 + BM25 混合 + rerank
│   │   ├── api/v1/               # 与 04 文档一致的 REST 路由
│   │   └── jobs/                 # scheduler.py, crawl_job.py, analyze_job.py
│   ├── tests/
│   │   ├── fixtures/             # 用例 1 / 用例 2 的政策原文样本
│   │   └── acceptance/           # 09 文档的验收脚本
│   └── pyproject.toml
├── frontend/
│   ├── app/                      # 与 08 文档页面一一对应
│   ├── components/
│   ├── lib/
│   └── tailwind.config.ts        # 08 文档的 design token
├── seed/                         # 数据源清单、HSBC 业务图谱、历史案例、合成客户
├── docs/                         # 本套 00–10 文档
└── reports/                      # 各 Phase 验收报告
```

### 五、核心业务流程（必须按此实现）

```
调度器(每 30min)
  → SourceAdapter 拉取（RSS 优先，其次 sitemap diff，再列表页 diff，最后 Playwright 兜底）
  → normalize：正文抽取(trafilatura)、语言识别、发布日期归一、附件 PDF 解析
  → dedupe：URL 归一 + simhash(64) + 标题/正文相似度；重复则记 document_version
  → gate-1 规则过滤：地域关键词 + 金融关键词 + 机构白名单（命中即进下一步）
  → gate-2 AI 分类：is_financial_policy / policy_type / jurisdiction / 置信度
  → 结构化抽取（05-P2）：发文机关、文号、生效日、适用主体、主题标签、义务、激励、金额、期限
  → 适用范围判定（05-P3）：目标主体（汇丰实体）是否被覆盖 / 被排除 / 未提及
  → 检索（RAG）：相似历史案例 + HSBC 业务图谱切片 + 现行同类政策
  → 影响分析（05-P4）：8 维评分 + 传导链 + 客户暴露估算 + 建议动作
  → 生成预警草稿（05-P5）→ 落库 review_task(pending)
  → 人工审核台 → approved → 分发 → 归档为 case（供后续 RAG 复用）
```

### 六、分阶段任务与验收门槛

**Phase 0 · 可运行骨架（目标：1 天）**
- docker compose 起 postgres/sqlite + backend + frontend；数据库迁移可跑；健康检查 `/healthz`。
- 前端出 CURE 风格空壳：侧边导航 + 雷达页 KPI 条 + 空列表。
- `LLMProvider` 三实现齐备，`MockProvider` 返回固定 JSON，便于离线开发。
- ✅ 验收：`make dev` 后两个端口可访问；`make test` 全绿；`.env.example` 覆盖所有配置项。

**Phase 1 · 抓取管线（目标：3 天）**
- 接入 6 个数据源：HKMA 新闻稿、HKMA 指引通告、政府新闻公报、news.gov.hk 财经频道、FSTB 新闻、广东省政府政策文件。
- RSS 优先；无 RSS 用 sitemap + 列表页 diff；PDF 附件走解析。
- 变更检测：正文 simhash 变化 → 新增 `document_version`，前端可看 diff。
- ✅ 验收：`make crawl` 单次运行，入库 ≥50 条真实文档，字段完整率 ≥95%，抓取失败源有明确错误日志；连续跑 3 次不产生重复文档。

**Phase 2 · AI 抽取与分析（目标：5 天）**
- 实现 05 文档 P1–P5 五条链路，全部带 JSON Schema 校验与证据校验。
- 影响评分卡在 `domain/scoring.py` 纯函数实现，可单测，不依赖 LLM。
- 前端政策详情页展示：原文对照 + 抽取字段 + 评分雷达图 + 证据高亮。
- ✅ 验收：用 `tests/fixtures/gd_subsidy_policy.html`（广东贴息政策样本）跑通，输出"外资银行被排除、影响 P1、涉及 CMB 客户 3 户、建议 72 小时内触达"，且三条结论各带 ≥1 条可点击定位的证据 span。

**Phase 3 · 审核台与分发（目标：4 天）**
- 审核队列、双签、驳回原因、退回补充、批量操作、键盘 J/K 导航。
- 分发适配器：站内通知必做；邮件/企微/飞书用 webhook 抽象（`Notifier` 接口），未配置时降级为站内。
- 审计日志：所有状态变更、字段修改、模型调用（含 token 与耗时）可查询导出。
- ✅ 验收：未审核内容调用分发接口返回 409；审核通过后审计链完整可回放；驳回后内容不可再直接发布。

**Phase 4 · 案例库与政策 2.0（目标：5 天）**
- 案例库：历史案例结构化存储（背景/政策/影响/应对/结果/启示），支持按主题与业务线检索。
- 政策 2.0 工作台：主题树 + 条款演化时间轴 + 建议书生成 + 边界校验提示。
- ✅ 验收：用 `seed/cepa/` 语料生成一份建议书，包含 ≥5 条建议，每条含「现行依据 / 不冲突论证 / 拟条文 / 影响 / 风险」，且所有引用可回溯到语料文件与段落。

**Phase 5 · 上云（目标：3 天，可后置）**
- 按 `10_DEPLOY_ALIYUN_ROADMAP.md` 迁移：ECS + RDS PostgreSQL(pgvector) + OSS + SLS + 百炼。
- 保持"本地仍可跑"：云端只换配置与 Provider，不改代码。
- ✅ 验收：云端环境跑通 Phase 1–3 全部验收脚本；本地 `LLM_PROVIDER=ollama` 仍可运行。

### 七、编码规范

- 业务逻辑放 `domain/`，禁止在路由里写判断逻辑；路由只做参数校验与编排。
- 所有外部调用（抓取、LLM、通知）必须经过 `Adapter` 接口，便于 mock 与替换。
- 所有 LLM 调用必须落 `llm_call_log`：provider、model、prompt_version、input_hash、tokens、latency、status。
- 时间一律 UTC 存储，前端按 `Asia/Hong_Kong` 展示。
- 错误分级：`retryable`（网络/限流）自动重试 3 次指数退避；`fatal`（解析/结构）落 `dead_letter` 并告警。
- 每个公共函数写 docstring，说明输入输出与失败模式；不写废话注释。
- 前端不做"看起来高级"的动画堆砌，信息密度优先。

### 八、绝对禁止

- 禁止用 LLM 直接生成 HTML/富文本注入前端（XSS 风险），一律结构化 JSON + 前端渲染。
- 禁止在没有证据的情况下输出"影响金额"具体数字；只能给区间 + 假设 + 置信度。
- 禁止把 API Key 写进代码或提交到仓库。
- 禁止擅自扩大数据源范围（尤其社交媒体与需登录站点）。
- 禁止跳过 `reports/phase-N-acceptance.md`。
- 禁止在 Phase 0–3 引入 K8s、Kafka、微服务拆分、GraphQL。

### 九、遇到歧义怎么办

1. 优先在 `docs/` 中找答案；文档冲突时以 `02_PRD_MVP.md` 为准。
2. 仍不明确时，做**最小合理假设**，写进 `docs/DECISIONS.md`（格式：`日期 | 问题 | 假设 | 影响范围 | 回滚方式`），然后继续。
3. 只有当假设会导致**数据模型不可逆变更**时，才停下来问我，最多问 3 个问题。

### 十、开始执行

现在开始 **Phase 0**。要求：

1. 先输出一份 ≤40 行的实施计划（文件清单 + 关键接口签名 + 风险点），等我一句"继续"。
2. 然后创建目录骨架、docker-compose、`.env.example`、数据库模型（按 04 文档）、Provider 接口与 Mock 实现。
3. 完成后生成 `reports/phase-0-acceptance.md`，并给出 `NEXT` 指令让我确认进入 Phase 1。

## === PROMPT END ===

---

## 附：三个可直接复用的追问指令

**推进下一阶段**
> 进入 Phase N。先读 docs 中相关文档，列出本阶段将新增/修改的文件，然后实现，最后产出 reports/phase-N-acceptance.md。

**让 Agent 自查**
> 以"银行内网安全评审员"身份审查你刚才的代码：列出 (1) 幻觉风险点 (2) 权限与审计缺口 (3) 单点故障 (4) 数据合规问题，各给修复方案，不要只夸。

**给非技术人看的版本**
> 用 400 字、零术语，向业务负责人解释这次做完后他们每天会看到什么、需要做什么动作、能避免什么损失。
