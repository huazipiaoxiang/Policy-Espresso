.PHONY: dev test seed crawl migrate backend frontend install health deploy-check deploy migrate-pg migrate-sqlite-to-pg

# 优先使用本地 venv（docker 容器内无 .venv，回退系统 python）
PYTHON := $(shell [ -x backend/.venv/bin/python ] && echo backend/.venv/bin/python || echo python)

# 一条命令启动（docker）
dev:
	docker compose up --build

# 本地直跑（无 docker 时）
install:
	cd backend && pip install -e ".[dev]"
	cd frontend && npm install

migrate:
	cd backend && $(PYTHON:backend/%=%) -m alembic upgrade head

backend:
	cd backend && $(PYTHON:backend/%=%) -m uvicorn app.main:app --reload --port 8000

frontend:
	cd frontend && npm run dev

test:
	cd backend && $(PYTHON:backend/%=%) -m pytest -q
	cd frontend && npm run build

seed:
	cd backend && $(PYTHON:backend/%=%) -m app.jobs.seed_job

crawl:
	cd backend && $(PYTHON:backend/%=%) -m app.jobs.crawl_job

health:
	cd backend && $(PYTHON:backend/%=%) -m app.jobs.health_job

# ===== Phase 5 部署（阿里云）=====
deploy-check:
	python3 -c "import yaml; [yaml.safe_load(open(f)) for f in ['docker-compose.yml','deploy/docker-compose.prod.yml']]; print('compose YAML OK')"
	cd backend && $(PYTHON:backend/%=%) -c "from app.storage import get_storage; print('storage backend:', get_storage().name)"

deploy:
	docker compose -f deploy/docker-compose.prod.yml up -d --build

migrate-pg:
	cd backend && $(PYTHON:backend/%=%) -m alembic upgrade head

migrate-sqlite-to-pg:
	cd backend && $(PYTHON:backend/%=%) ../deploy/scripts/migrate_sqlite_to_pg.py
