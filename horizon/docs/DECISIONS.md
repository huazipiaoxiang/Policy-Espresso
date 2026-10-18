# DECISIONS · 最小合理假设记录

格式：`日期 | 问题 | 假设 | 影响范围 | 回滚方式`

| 日期 | 问题 | 假设 | 影响范围 | 回滚方式 |
|---|---|---|---|---|
| 2026-10-17 | 本机无 Docker，Phase 0 验收如何执行 | compose 文件照常交付；本地验收用 venv + npm 直跑等价命令（uvicorn / next dev），compose 行为在阿里云 ECS（Phase 5）或装 Docker 的机器上复核 | 仅验收方式，不影响交付物 | 安装 Docker 后 `docker compose up` 复验 |
| 2026-10-17 | Alembic 首个迁移手写 17 表成本高 | 初始 revision 调 `Base.metadata.create_all`（upgrade）/ `drop_all`（downgrade），后续变更走正常 autogenerate revision | db/migrations | 删除初始 revision，改为 autogenerate 全量脚本 |
| 2026-10-17 | MVP 认证 | `X-API-Key` 单用户，云端换 OIDC，接口不变（04 §4.1 已规定） | core/security | 替换 dependency 实现 |
| 2026-10-17 | LLM_PROVIDER 默认值 | 默认 `mock`，保证无网/CI 可跑；显式切 `ollama`/`dashscope` | 部署配置 | 改环境变量即可 |
| 2026-10-17 | 04 文档 assessment 示例 score_total=86.5 与 02 §5.2 权重表计算结果（91.0）不一致 | 以 02 §5.2 权重表为准（文档冲突以 02 为准，见 01 §九）；示例 JSON 视为示意 | domain/scoring.py 与测试断言 | 若业务确认另有折算规则，调整 compute_score |
| 2026-10-17 | 证据归一化是否保留空白 | 中文语境空格无意义，NFKC 后去除全部空白再比对 | ai/guard.py | 改回折叠空白即可 |
| 2026-10-17 | SQLite 读回 datetime 丢失时区 | 新增 `UTCDateTime(TypeDecorator)`，读回 naive 值按 UTC 解释；写入仍存 UTC | db/models.py 全部时间列 | 换 PG 后可移除装饰器（PG 原生 tz） |
| 2026-10-17 | 无正文/仅标题文档（付费墙，T1-N4） | document.status 增加 `needs_full_text`（04 枚举外延，前端与 API 已兼容） | document.status | 若严格枚举，改回 failed + 独立队列表 |
| 2026-10-17 | ≥5 维 null 的 assessment（05 §0.3.4） | confidence 压到 ≤0.3 且不进审核队列，policy 留 ai_checked | analyze_job | 增加显式 low_confidence 状态位 |
| 2026-10-17 | 长文分段抽取（05 §0.2） | MVP 未实现，单次抽取；超长文截断 | ai/chains/extract.py | Phase 2.5 补分段+merge |
| 2026-10-17 | Phase 1 全量入库量级（≥50 条） | 用户指示限量 1~2 条/源验证，全量命令就绪未跑 | reports/phase-1 | 随时 `make crawl`（不设 CRAWL_MAX_ITEMS_PER_SOURCE） |
| 2026-10-17 | mock 引文在真实文档不可定位 | 视为护栏正确行为：证据丢弃、不给结论配证据 | ai/guard + evidence.py | 不需要回滚 |
| 2026-10-17 | P7 红队质疑 LLM 版 | 先落规则版（双通道冲突/无证据维度/时效虚高/零证据），LLM 版可选项 | domain/review.challenge_assessment | 接 p7_challenge 链路 |
| 2026-10-17 | 前端 API Key 不暴露 | Next BFF 代理 `/api/proxy/*`，服务端注入 X-API-Key | frontend/app/api/proxy | 换 OIDC 后改 BFF |
| 2026-10-17 | pgvector 迁移在 SQLite 下跳过 | 0002 迁移用 offline/online 双通道 dialect 检测，SQLite 不建扩展 | db/migrations/0002 | PG 部署后删除离线探测亦可 |
| 2026-10-17 | 附件/快照存储抽象 | Storage 接口 local/oss 两实现，快照落 storage；MVP 未接 trafilatura 后的 HTML 快照 | app/storage | 在 pipeline 落快照调用 save_snapshot |
| 2026-10-17 | ECS APScheduler 与 FC 双触发 | 默认 APScheduler；FC 走 /internal/jobs/* 带 X-Job-Token；两者二选一避免双跑 | jobs/scheduler + api/internal | 关其一 |
| 2026-10-17 | robots.txt 抓取方式 | 部分站点对 urllib 默认 UA 返回 403，robotparser 据此判"全站禁止"造成误杀；改为 httpx + 可识别 UA 抓取 robots，403/401 → 全站禁止，其他 4xx/5xx → 放行 | ingest/http.py | 回退 `rp.read()` 一行改动 |
| 2026-10-17 | fstb 列表链接为 ISD TuniS 代理（sc.isd.gov.hk robots 全站禁止） | 抓取前把 TuniS 代理 URL 还原为 info.gov.hk 真实地址（与 canonicalize 同一规则），不抓代理域 | ingest/dedupe.py rewrite_fetch_url、pipeline.py | 删除 rewrite 调用即可 |
| 2026-10-17 | trafilatura 对中文日期误解析（"2026年11月1日" → 2026-01-01） | CJK 页面优先用正文中文日期正则；RSS 给的 published 优先于一切；meta.date 仅作兜底 | ingest/normalize.py 日期优先级 | 恢复原优先级 |
| 2026-10-17 | simhash64 高位溢出（SQLite/PG BIGINT 有符号 64 位） | 指纹掩码至 63 位，牺牲 1 位精度换跨库兼容 | ingest/dedupe.py | 改用字符串存储指纹 |
| 2026-10-17 | 跨源近重复是否含同源 | 同源同内容由 canonical URL 精确去重覆盖；近重复聚类只跨源（06 §5.5 语义为"多源转载"） | ingest/pipeline.py _find_near_duplicate | 去掉 source_id 过滤 |
| 2026-10-17 | seed 源配置漂移（DB 为 Phase 0 旧配置，seed 文件已更新） | seed_sources 改为 upsert：按 code 匹配，字段以 seed/sources.json 为准 | jobs/seed_job.py | 改回 skip-existing |
| 2026-10-17 | 同一坏附件 URL 被多文档引用导致重复抓取失败 | URL 级失败负缓存 24h（storage/attachments/failed/） | ingest/pdf_parse.py | 删除负缓存逻辑 |
| 2026-10-17 | 设置页应展示哪些系统配置 | 只读脱敏快照（GET /settings）：密钥/令牌/webhook 只返回「是否已配置」；本地存储目录路径脱敏为布尔；不引入运行时可变配置表（进程级配置由 .env 注入、重启生效） | api/v1/settings.py + frontend/app/settings | 如需运行时热改，再加 settings 表 + 写接口 |
