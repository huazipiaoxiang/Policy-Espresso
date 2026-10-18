# Phase 0 验收报告 · 可运行骨架

日期：2026-10-17 · 执行人：编码 Agent · 验收依据：`docs/01_AGENT_PROMPT.md` §六 Phase 0

## 验收项核对

| 验收标准 | 结果 | 证据 |
|---|---|---|
| 数据库迁移可跑 | ✅ 通过 | `alembic upgrade head` 建 17 表（SQLite）；PG 同构待 Phase 5 复验 |
| 健康检查 `/healthz` | ✅ 通过 | 返回 `{status: ok, checks: {db: ok, llm_provider: mock}}` |
| 前端 CURE 空壳：侧边导航 + KPI 条 + 空列表 | ✅ 通过 | `/radar` 1440 宽无横向滚动；Token 取自 `08 §1`；空态含"下一步做什么" |
| `LLMProvider` 三实现齐备 | ✅ 通过 | `mock`（确定性，已测）/ `ollama` / `dashscope`（OpenAI 兼容端点，缺 key 时显式报错），`LLM_PROVIDER` 环境变量切换 |
| `make test` 全绿 | ✅ 通过 | pytest **28 passed**；前端 `next build` 通过（4 路由） |
| `.env.example` 覆盖所有配置项 | ✅ 通过 | 与 `core/config.py` 字段一一对应 |
| `make dev`（docker compose）两端可访问 | ⚠️ 未在本机验证 | 本机未安装 Docker；已用等价命令直跑验证：uvicorn(8001) + next start(3000) 端到端联通（雷达页取到 6 个已配置源）。compose 文件已交付，待有 Docker 的机器复验（记入 `docs/DECISIONS.md`） |

## 已落实的硬规则抽查

- **反幻觉**：`ai/guard.py` 证据校验（quote 必须可在原文定位，NFKC+去空白归一化）；编造证据的测试用例被作废 ✅
- **人审不可绕过**：`POST /policies/{id}/dispatch` 对非 published 状态返回 `409 NOT_APPROVED`（测试覆盖）✅
- **抓取合规**：UA / 限速 / robots 配置项已入 `.env.example`；适配器注册表就位（实现属 Phase 1）✅
- **合成数据**：`seed/synthetic_customers.json` 全合成 ✅
- **状态机**：显式转移表 + 非法转移抛异常 + `rejected→draft` 强制重开原因（测试覆盖）✅
- **评分卡**：`domain/scoring.py` 纯函数，权重按 `02 §5.2`；发现 `04` 示例总分与权重表不符，已按"以 02 为准"裁决并记入 `docs/DECISIONS.md` ✅

## 遗留与风险

1. Docker 未本机验证（环境限制，非交付物缺陷）。
2. Alembic 初始 revision 用 `metadata.create_all`，后续变更需走 autogenerate（已记录）。
3. `npm` 全局缓存目录权限损坏（`~/.npm/_cacache` EACCES），本次用项目内 `--cache` 绕过；建议修复：`sudo chown -R $(id -u):$(id -g) ~/.npm`。

## 下一步（Phase 1 · 抓取管线）

接入 6 源 RSS/列表页抓取、trafilatura 正文抽取、simhash 去重、变更检测；验收：`make crawl` 入库 ≥50 条真实文档。

**NEXT**：确认后回复"进入 Phase 1"，我将按 `docs/06_SOURCE_CATALOG_CRAWL.md` 实现适配器并产出 `reports/phase-1-acceptance.md`。
