# HORIZON 阿里云部署 Runbook（Phase 5）

对应 `docs/10_DEPLOY_ALIYUN_ROADMAP.md`。原则：**上云只换配置与实现，不改业务逻辑**。

## 1. 目标架构

```
办公网/VPN ── WAF? ── SLB/EIP:443 ── ECS (2c4g, docker compose)
                                    ├─ nginx (443)
                                    ├─ web (next:3000)
                                    ├─ api (uvicorn:8000，仅内网)
                                    ├─ RDS PostgreSQL 15 + pgvector
                                    ├─ OSS（原文快照）
                                    └─ SLS（日志）
出网：NAT/EIP → 抓取中国香港及内地政府站点
定时：FC 定时触发器 → POST /internal/jobs/{crawl,analyze}（X-Job-Token 签名）
```

## 2. 首次部署（半天）

1. **建库**：RDS PostgreSQL 15，开 pgvector 扩展白名单；`alembic upgrade head` 建表（0002_pgvector 自动建 HNSW 索引）。
2. **迁数据**：`make migrate-sqlite-to-pg`（逐表 upsert，幂等）。
3. **OSS**：建私有 bucket，配置 RAM 子账号 AK/SK（最小权限：只读写 horizon bucket）。
4. **环境**：`cp .env.production.example .env`，填 `DATABASE_URL` / `DASHSCOPE_API_KEY` / `OSS_*` / `API_KEY` / `JOB_TRIGGER_TOKEN`（密钥走 KMS 或 ECS 环境变量注入，禁止入镜像）。
5. **证书**：自签或企业 CA 证书放 `deploy/certs/`（horizon.crt / horizon.key）。
6. **拉起**：`make deploy` → `curl https://<域名>/api/v1/healthz` → 跑 Phase 1–3 验收脚本。
7. **定时**：FC 建两个定时触发器（crawl */30min、analyze */5min），与 ECS 内 APScheduler **二选一**（默认保留 APScheduler，FC 作为跨机灾备，需把其中一个关掉避免双跑）。
8. **DNS**：内网域名解析到 EIP；本地 SQLite 环境保留为演练/降级环境。

## 3. 回滚（30 分钟内）

1. 保留上一版镜像 tag（`horizon-api:prev`、`horizon-web:prev`），`docker compose ... up -d` 切回。
2. 数据回滚：每日 `pg_dump` 快照（见 §5），恢复后 `alembic downgrade -1`（若 schema 变更）。
3. 本地 SQLite 快照 + `migrate_sqlite_to_pg.py` 反向不同步——数据以 PG 为准，本地仅演练。

## 4. 安全基线（10 §8）

- [x] 密钥不在代码/镜像/日志（.env + KMS；.gitignore 已排除 .env）
- [x] 8000 不暴露公网（compose 仅 expose；安全组只放 443）
- [x] 管理接口（/admin、/internal）需 API Key / Job Token
- [x] 抓取内容全程 untrusted 标记；前端不渲染模型 HTML（结构化 JSON + 组件渲染）
- [x] 审计日志只追加；保留 ≥7 年（PG 表 + 每日备份）
- [ ] 上线前换 OIDC/企业 SSO（接口不变，替换 `core/security` dependency）
- [ ] WAF / IP 白名单按行内要求评估

## 5. 备份与巡检

| 频率 | 动作 |
|---|---|
| 每日 02:00 | `pg_dump -Fc horizon > /data/backups/horizon_$(date +%F).dump`（保留 30 天） |
| 每周 | 恢复演练一次（恢复到临时库校验行数） |
| 每小时 | `make health`（源健康、失败率、连续失败熔断） |
| 每日 | 模型成本核对（`/admin/llm-calls` tokens 汇总 vs 预算 ¥5–15/日） |

## 6. 告警接入（SLS）

- 抓取连续失败 ≥3 → 站内 + 邮件（health_job）
- 分析任务 failed → 站内 + 邮件
- 磁盘 >80%、证书到期 <30 天 → 运维群
- 日模型成本超预算 150% → 降级到 plus 档（settings 调整）

## 7. 降级预案

| 故障 | 降级 |
|---|---|
| 百炼不可用 | `LLM_PROVIDER=mock`（规则模式：关键词分类 + 模板提示，无新预警但系统可用） |
| 向量不可用 | 检索降级关键词（03 §3.3 已设计） |
| OSS 不可用 | `STORAGE_BACKEND=local`（卷内快照） |
| PG 不可用 | 切本地 SQLite 快照环境（数据为昨日备份） |

## 8. 成本（10 §4 估算）

ECS 2c4g + RDS 1c2g + OSS + SLS + 百炼 ≈ **500–1200 元/月**。省钱：夜间批处理、flash 打标、input_hash 缓存、只对 P1+ 用 max。
