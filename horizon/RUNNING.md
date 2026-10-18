# HORIZON · 政策雷达 — 运行说明（RUNNING）

面向金融机构的区域性金融政策监测与影响分析系统。分析主体：香港上海汇丰银行、汇丰银行（中国）。
本文档告诉你如何在**一台新机器**上把网站跑起来。

## 1. 环境要求

| 依赖 | 版本 | 说明 |
|---|---|---|
| Docker Desktop | 任意新版 | **方式 A 需要**（推荐） |
| Python | 3.11+（推荐 3.12） | 方式 B 需要 |
| Node.js | 18.17+（推荐 20） | 方式 B 需要 |

> 默认 LLM 走 `mock`（离线确定性输出），**不需要任何 API Key 即可跑通全站**。

## 2. 方式 A：Docker（最简单，推荐）

```bash
cd horizon
cp .env.example .env        # 首次
docker compose up --build
```

导入种子数据（数据源清单 + 业务图谱 + 历史案例 + 合成客户，否则列表为空）：

```bash
docker compose exec api python -m app.jobs.seed_job
```

访问：

- 前端界面：<http://localhost:3000>
- API 文档：<http://localhost:8000/docs>

## 3. 方式 B：本地直跑（无 Docker）

### 3.1 后端

```bash
cd horizon/backend
python3.12 -m venv .venv
.venv/bin/pip install -e ".[dev]"

# 建库 + 导入种子数据（自动建表）
DATABASE_URL=sqlite:///./horizon.db SEED_DIR=../seed .venv/bin/python -m app.jobs.seed_job

# 启动后端（默认 8000 端口）
DATABASE_URL=sqlite:///./horizon.db .venv/bin/uvicorn app.main:app --port 8000
```

### 3.2 前端（另开一个终端）

```bash
cd horizon/frontend
npm install
npm run dev                 # 开发模式
# 或生产模式：npm run build && npm start
```

访问 <http://localhost:3000>。

## 4. 常用命令

| 命令 | 作用 |
|---|---|
| `make seed` | 导入数据源/案例等种子数据（首次必做） |
| `make crawl` | 抓取政策（需联网访问香港/广东政府站点） |
| `make test` | 跑后端测试 + 前端构建 |

## 5. 关键环境变量（`.env`）

| 变量 | 默认 | 说明 |
|---|---|---|
| `LLM_PROVIDER` | `mock` | `mock`（离线）/ `ollama`（本地）/ `dashscope`（阿里云百炼） |
| `DATABASE_URL` | `sqlite:////data/horizon.db` | 本地直跑改用 `sqlite:///./horizon.db` |
| `NEXT_PUBLIC_API_BASE` | `http://localhost:8000/api/v1` | 前端连的后端地址 |
| `API_KEY` | `dev-local-key` | 前后端需一致（MVP 单用户） |
| `DASHSCOPE_API_KEY` | 空 | 切 `dashscope` 时必填，密钥不落仓 |

## 6. 常见问题

1. **页面是空的**：大概率没跑 `seed`（数据源/案例库为空）。先执行 `make seed`。
2. **8000 端口被占用**：换端口启动后端，并同步改 `NEXT_PUBLIC_API_BASE` 与 `API_PORT`。
3. **要真实 AI 分析**：`.env` 设 `LLM_PROVIDER=dashscope` 并填 `DASHSCOPE_API_KEY`；或本地装 Ollama 设 `LLM_PROVIDER=ollama`。
4. **抓取失败**：属正常，`make crawl` 依赖对香港/广东政府站点的网络访问。
5. **打包给他人时**：务必排除 `frontend/node_modules`、`frontend/.next`、`backend/.venv`、`backend/storage`、`backend/*.db`（`.gitignore` 已配置，用 git 分发会自动排除）。
