# 07 · 可集成的 Skills / MCP / 开源组件（市面调研）

## 1. 三种"可下载能力"的形态，别搞混

| 形态 | 是什么 | 怎么接入 | 适用 |
|---|---|---|---|
| **Agent Skill** | 一个文件夹 + `SKILL.md`（YAML frontmatter + 指令 + 可选脚本），模型按需加载 | 放进 `skills/` 目录，或用 `npx skills add <repo>` 安装 | 给**编码 Agent** 扩能力（写文档、跑测试）；也可给运行时 Agent 当"操作手册" |
| **MCP Server** | 标准协议的服务端，暴露 tools/resources | 写进 `mcp.json` / `claude_desktop_config.json`，或代码里用 MCP client 连接 | 接外部系统（浏览器、搜索、数据库、IM） |
| **Python/Node 库** | 普通依赖 | `pip install` / `npm i` | 系统内部的确定能力（解析、向量、检索） |

> 关键判断：**MCP 适合"工具"，Skill 适合"流程"，库适合"组件"**。
> 本项目的抓取、解析、检索应当用**库**直接写在代码里（可控、可测、可离线）；只有需要"人机协作式操作"（如编码期用浏览器查文档）才用 MCP。

## 2. 推荐直接集成的 Skill（开发期）

| Skill / 仓库 | 能力 | 许可证 | 在本项目怎么用 |
|---|---|---|---|
| `anthropics/skills` → `docx` / `pdf` / `pptx` / `xlsx` | 生成 Word/PDF/PPT/Excel 的成熟流程（含版式、表格、目录） | 源可用（source-available，参考实现） | 把每日/每周预警导出为 Word 简报、把政策 2.0 建议书导出为 PPT 汇报 |
| `anthropics/skills` 其余示例集 | 创意/技术/企业流程示例（Apache 2.0 居多） | Apache 2.0 | 抄它的 `SKILL.md` 结构，自建本项目专属 Skill |
| WorkBuddy 内置 `workbuddy-docx` / `workbuddy-pptx` / `workbuddy-sheet-generation` | 中文研报级 Word/PPT/Excel 生成与美化 | 随产品 | 交付物排版（比手写 python-docx 快且好看） |
| `workbuddy-sheetagent` | 已有 Excel 的分析/清洗/透视 | 随产品 | 政策影响台账、客户暴露表分析 |
| Firecrawl 的 Claude Code / Codex skills | 一键配置抓取与结构化抽取 | 官方 | 开发期快速验证某个站点的抓取可行性 |

**自建 Skill 建议（给编码 Agent 用，强烈推荐）**
在仓库里建 `skills/`，写三个项目专属 Skill：
```
skills/
├── policy-extract/SKILL.md      # 如何跑抽取、如何校验证据、失败怎么修
├── source-onboard/SKILL.md      # 新增一个数据源的 6 个步骤（探测→试抓→选 adapter→写选择器→回归→上线）
└── review-console/SKILL.md      # 审核台的交互规范与快捷键，改 UI 时必须遵守
```
每个 `SKILL.md` 只写"怎么做"，不写"是什么"——后者属于文档。控制在 200 行内，超过就说明该拆。

## 3. 推荐 MCP Server（按用途）

| MCP | 用途 | 接入方式 | 是否需要 Key | 本项目价值 |
|---|---|---|---|---|
| **Firecrawl MCP** | 整站抓取、结构化抽取、变更监控 | `npx -y firecrawl-mcp` + `FIRECRAWL_API_KEY` | 是（付费，免费额度 500 页/月） | 开发期探测新数据源；生产建议自建，不依赖第三方 |
| **Playwright MCP** | 浏览器自动化，走无障碍树而非截图 | `npx -y @playwright/mcp@latest` | 否 | 调试 JS 渲染页、临时兜底抓取 |
| **fetch MCP** | 单页取回转 markdown | `npx -y @kazuph/mcp-fetch` 等 | 否 | 快速验证 URL 内容 |
| **Brave / Exa Search MCP** | 网络搜索 | 各自 API Key | 是 | 政策线索发现（"某主题最新文件"） |
| **filesystem MCP** | 本地文件读写 | `npx -y @modelcontextprotocol/server-filesystem <dir>` | 否 | 让 Agent 读 `docs/`、写 `reports/` |
| **postgres MCP** | 直连数据库查询 | `npx -y @modelcontextprotocol/server-postgres <dsn>` | 否 | 排查数据问题 |
| **Slack / 飞书 / 企业微信 MCP** | 消息分发 | 各自配置 | 是 | 预警推送（也可用自建 webhook，更简单） |
| **阿里云百炼 MCP** | 调用云端模型/知识库 | 按官方文档 | 是 | 云端阶段使用 |

> **生产环境建议**：只保留 `filesystem` 与 `postgres` 两个 MCP 做运维辅助；抓取走自建代码。理由：抓取逻辑一旦放在外部 SaaS，出问题无法本地复现，且政策原文属于敏感信息。

## 4. 开源组件选型矩阵（本地可集成）

### 4.1 抓取与解析
| 组件 | 作用 | 优点 | 注意 |
|---|---|---|---|
| `httpx` | HTTP 客户端 | 异步、HTTP/2 | 配 `tenacity` 重试 |
| `feedparser` | RSS/Atom 解析 | 容错强（脏 XML 也能啃） | 无 RSS 的站用不上 |
| `trafilatura` | 正文抽取 | 中文效果优于 readability，能去导航/广告 | 对表格页效果一般 |
| `selectolax` / `lxml` | HTML 解析 | 快 | 选择器要写稳（多候选） |
| `Playwright` | 浏览器渲染 | 能处理 SPA、翻页 | 重，只做兜底；注意内存 |
| `Crawl4AI` | LLM 友好抓取（含 markdown 输出、并发） | 开箱即用，支持 JS | 依赖较重；可作 Playwright 的上层封装替代 |
| `MinerU` / `Docling` | PDF→结构化（含表格、公式） | 中文政策 PDF 表格还原好 | 资源占用高，建议独立进程/队列 |
| `pdfplumber` | PDF 文本层判断 | 轻 | 扫描件需 OCR |
| `changedetection.io` | 网页变更监控（独立服务） | 现成的监控+通知 | 适合做"兜底哨兵"，不做主链路 |

### 4.2 检索与 RAG
| 组件 | 作用 | 说明 |
|---|---|---|
| `sqlite-vec` / `Chroma` | 本地向量库 | MVP 用前者的零运维；Chroma 功能更全 |
| `pgvector` | 云端向量 | HNSW 索引，与业务库同库，事务一致 |
| `rank_bm25` / SQLite FTS5 | 关键词检索 | 政策文号、专有名词必须靠关键词 |
| `bge-m3` / `text-embedding-v4` | 中文/多语 embedding | 前者可本地跑，后者走百炼 |
| `bge-reranker-v2-m3` / `gte-rerank` | 重排 | 提升 Top5 精度，性价比高 |
| `LlamaIndex` / `LangChain` | RAG 编排 | **建议只用其 loader/splitter，不用其 Agent 黑盒** |
| `Ragas` | RAG 评测 | 生成 faithfulness / context recall 指标 |

### 4.3 编排与人审
| 组件 | 作用 | 结论 |
|---|---|---|
| `LangGraph` | 状态机式编排 + `interrupt` 人工介入 | **推荐**：与"审核台"天然契合，状态可持久化、可回放 |
| `Dify` / `n8n` / `Coze` | 低代码编排 | 原型可，**生产不建议**：审核流、审计、证据校验都做不细 |
| `CrewAI` / `AutoGen` | 多 Agent 协作 | MVP 不需要；"多 Agent 讨论"难审计，慎用 |
| `Qwen-Agent` | 阿里系 Agent 框架 | 上云后可作为工具调用层备选 |
| `APScheduler` / `ARQ` | 定时与轻队列 | MVP 前者，云端可换后者 |

### 4.4 可观测与质量
`structlog`（结构化日志）、`OpenTelemetry`（链路）、`Langfuse`（LLM 调用追踪，可自建）、`promptfoo`（prompt 回归测试）、`pytest` + `respx`（HTTP mock）。

## 5. 阿里云侧能力（Phase 5）

| 能力 | 服务 | 在本项目的用法 |
|---|---|---|
| 模型推理 | 阿里云百炼（DashScope） | OpenAI 兼容端点：`https://dashscope.aliyuncs.com/compatible-mode/v1`，可直接复用 `openai` SDK |
| 模型分层 | qwen-flash / qwen-plus / qwen-max / qwen-long | flash 打标、plus 抽取分析、max 复杂推理、long 吃整本政策 |
| Embedding | `text-embedding-v4` | 政策与案例向量化 |
| 重排 | gte-rerank | 检索 Top5 精排 |
| 知识库 | 百炼知识库（RAG） | 可选：把案例库/业务图谱托管，减少自研；注意地域限制（知识库目前主要在中国内地地域提供） |
| 计算 | ECS（2c4g 起步） | 跑 docker compose |
| 数据库 | RDS PostgreSQL + pgvector | 业务库 + 向量同库 |
| 存储 | OSS | 原文快照、PDF、导出文件 |
| 日志 | SLS | 结构化日志采集与检索 |
| 定时 | 函数计算 FC 定时触发器 | 触发 `/internal/jobs/crawl`，省一台常驻机 |
| 安全 | RAM 子账号 + KMS | 密钥不落代码；按最小权限授权 |
| 内容安全 | 内容安全服务 | 对外文案合规扫描（可选） |

> 迁移原则：**云端只换配置与 Provider，不改业务代码**。本地 `LLM_PROVIDER=ollama` 必须始终可用，作为断网/断供的兜底。

## 6. 集成优先级（别一次装太多）

**必装（P0）**：httpx、feedparser、trafilatura、lxml、sqlalchemy、alembic、pydantic、apscheduler、jsonschema、structlog、pytest
**强烈建议（P1）**：sqlite-vec（或 Chroma）、rank_bm25、bge-m3（或走百炼 embedding）、LangGraph（做审核状态机）、MinerU/Docling（PDF）
**可选（P2）**：Playwright（兜底渲染）、Ragas（评测）、Langfuse（追踪）、Firecrawl（探测期）
**不建议（MVP）**：Kafka、K8s、多 Agent 框架、低代码平台做主线

## 7. 三个"看起来很美但会坑"的选择

1. **用 Firecrawl 做生产抓取**：省事，但抓取失败无法本地复现，且政策原文经第三方中转，合规评审难过。→ 只在开发期探测用。
2. **用 Dify 搭全流程**：两天能出 Demo，但"双签审核 + 字段级 diff + 证据定位 + 审计回放"四件事它都做不细，后期必然重写。→ 只用来做内部演示。
3. **上多 Agent（研究员 Agent + 审核 Agent + 写手 Agent）**：听起来高级，实际每次输出不一致、无法定位错误、成本翻倍。→ 用**固定链路 + 确定性规则 + 单点人审**，效果更稳。
