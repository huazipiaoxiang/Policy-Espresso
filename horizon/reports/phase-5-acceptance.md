# Phase 5 验收报告 · 阿里云部署（迁移资产 + 本地等价验证）

日期：2026-10-17 · 验收依据：`docs/01_AGENT_PROMPT.md` §六 Phase 5 + `docs/10_DEPLOY_ALIYUN_ROADMAP.md`

## 交付物（deploy/ 目录 + 根目录 .env）

| 资产 | 说明 |
|---|---|
| `deploy/docker-compose.prod.yml` | ECS 生产编排：nginx(443) + web + api（仅 expose 8000，不暴露公网）；存储卷 |
| `deploy/nginx.conf` | TLS + 安全头 + `/api`、`/stream`（SSE 关缓冲）+ 300s 读超时 |
| `deploy/scripts/migrate_sqlite_to_pg.py` | SQLite→PG 逐表 upsert（ON CONFLICT，幂等） |
| `deploy/runbook.md` | 部署步骤 / 回滚（30min）/ 备份巡检 / 告警 / 降级预案 / 成本 |
| `.env.production.example`（仓库根） | 生产环境样例（密钥不落仓） |

## 代码侧迁移点（不改业务逻辑，只换实现）

| 层 | 实现 | 切换 |
|---|---|---|
| 存储 | `app/storage/{local,oss}.py` + 工厂 | `STORAGE_BACKEND=local|oss` |
| 数据库 | `0002_pgvector.py` 迁移（仅 PG 生效，HNSW m=16/ef=64；SQLite 自动跳过） | `DATABASE_URL` |
| 模型 | `LLMProvider` 已有 `DashScopeProvider` | `LLM_PROVIDER=dashscope` |
| 调度 | FC 定时触发 `POST /internal/jobs/{crawl,analyze}`（`X-Job-Token` 签名） | 与 ECS APScheduler 二选一 |
| 向量 | Case 表 `embedding` 列就绪（SQLite 下 NULL，检索降级关键词） | 接入 EmbeddingProvider |

## 本地等价验证（无 Docker/云环境，可复现项）

| 验收标准 | 结果 | 证据（tests/test_phase5_deploy.py） |
|---|---|---|
| 存储抽象可切换、OSS 缺配置显式报错 | ✅ | local roundtrip / oss ValueError |
| alembic 离线 SQL 在 PG dialect 下渲染 pgvector | ✅ | `CREATE EXTENSION IF NOT EXISTS vector` 出现 |
| alembic 离线 SQL 在 SQLite 下不含 pgvector | ✅ | `CREATE EXTENSION` 不出现（本地降级） |
| FC 内部触发鉴权 | ✅ | 未配置 403 / 错令牌 401 / 正确 200 |
| 百炼缺 Key 快速失败（不静默降级到幻觉） | ✅ | ValueError |

## 待云端真验（需阿里云账号 + Docker，属部署阶段动作）

1. `make deploy` 拉起 compose（本机无 Docker，未跑）
2. RDS 建库 + `make migrate-pg` + `make migrate-sqlite-to-pg`
3. OSS bucket + `STORAGE_BACKEND=oss` 快照上传
4. 跑 Phase 1–3 验收脚本（本地脚本已就绪，云端只换 `NEXT_PUBLIC_API_BASE` 与 `.env`）
5. FC 定时触发器（crawl */30min、analyze */5min）

## 上线前检查清单对照（10 §8）

- [x] 功能：用例 1/2 验收全过（报告归档）；未审核分发 409 有测试；驳回可重开；源健康页反映故障
- [x] 质量：无证据结论率=0（护栏实证）；注入防护（untrusted + Schema 白名单）
- [x] 安全：密钥不入库不入日志；管理接口鉴权；审计只追加保留 ≥7 年；前端不渲染模型 HTML
- [ ] 运维：每日备份 + 恢复演练（runbook 已定义，云端执行）；告警接入 SLS（未接线）；OIDC/SSO（MVP 单 Key，接口已预留）

## 结论

- [x] Phase 5 迁移资产齐备、本地等价验证全过、回滚与降级预案成文，**本地仍可跑**（`LLM_PROVIDER=mock` + SQLite）
- [ ] 云端实部署：待用户提供阿里云账号/Docker 环境后执行 `make deploy`
