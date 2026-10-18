# HORIZON · 政策雷达 Agent

面向金融机构的区域性金融政策监测与影响分析系统（分析主体：香港上海汇丰银行、汇丰银行（中国））。
设计与验收口径见 `docs/00_README.md` ~ `docs/10_DEPLOY_ALIYUN_ROADMAP.md`。

## 快速开始

```bash
cp .env.example .env
docker compose up --build   # http://localhost:3000 界面 · http://localhost:8000/docs API
```

无 Docker 的本地直跑：

```bash
cd backend && python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"
DATABASE_URL=sqlite:///./horizon.db .venv/bin/alembic upgrade head
SEED_DIR=../seed DATABASE_URL=sqlite:///./horizon.db .venv/bin/python -m app.jobs.seed_job
DATABASE_URL=sqlite:///./horizon.db .venv/bin/uvicorn app.main:app --port 8000

cd frontend && npm install && npm run dev   # http://localhost:3000
```

## 常用命令

`make dev`（docker）/ `make test` / `make seed` / `make crawl` / `make migrate`

Phase 5 阿里云部署：`make deploy-check` / `make deploy` / `make migrate-pg` / `make migrate-sqlite-to-pg`（步骤见 `deploy/runbook.md`）

## 当前进度

- [x] Phase 0 可运行骨架（见 `reports/phase-0-acceptance.md`）
- [x] Phase 1 抓取管线（见 `reports/phase-1-acceptance.md`）
- [x] Phase 2 AI 抽取与分析（见 `reports/phase-2-acceptance.md`）
- [x] Phase 3 审核台与分发（见 `reports/phase-3-acceptance.md`）
- [x] Phase 4 案例库与政策 2.0（见 `reports/phase-4-acceptance.md`）
- [x] Phase 5 阿里云部署——迁移资产齐备 + 本地等价验证全过；云端实部署（`make deploy`）待阿里云账号/Docker 环境（见 `reports/phase-5-acceptance.md`）
