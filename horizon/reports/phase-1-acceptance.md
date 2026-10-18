# Phase 1 验收报告 · 抓取管线

日期：2026-10-17 · 验收依据：`docs/01_AGENT_PROMPT.md` §六 Phase 1 + `docs/06_SOURCE_CATALOG_CRAWL.md`

## 环境

- LLM_PROVIDER 不涉及（纯抓取）；Python 3.12 venv；SQLite
- 数据源 6 个，入口均经 `curl` 实测核验（非猜测选择器）：HKMA 新闻稿/指引通告（RSS）、政府新闻公报（列表页）、news.gov.hk 财经（RSS）、FSTB（列表页，ISD 代理链接已归一化）、广东省政府 qbwj（列表页 + 分页）

## 验收项核对

| 验收标准 | 结果 | 证据 |
|---|---|---|
| 接入 6 个数据源 | ✅ 通过 | `seed/sources.json` 全部 `verified_at: 2026-10-17` |
| RSS 优先，无 RSS 用列表页 | ✅ 通过 | rss/listing 适配器；FSTB 原始 URL 404 已改实测入口 `/sc/news/press/index.php` |
| 正文抽取 + 字段完整 | ✅ 通过 | trafilatura 抽取；抽样：标题/正文/语言/日期齐备（14 条入库文档） |
| URL 归一 + simhash 去重 | ✅ 通过 | `dedupe.py`：utm/fbclid/anchor/www/https 归一、TuniS 代理还原；simhash64 汉明 ≤3 判近重复；FSTB 与 GIA 同源文档被正确标 duplicate_of |
| 变更检测 document_version + diff | ✅ 通过 | `change_detect.py` + 单测（小改动 minor_edit ≤0.3，实质修订 >0.3）；API `/documents/{id}/versions/{n}/diff` |
| gate-1 规则过滤 | ✅ 通过 | 金融关键词命中放行；GIA 非财经公报被标 ignored 且仍入库备查 |
| 礼让合规 | ✅ 通过 | UA 可识别、单域 ≤1req/s + 抖动、robots 遵守、429/503 退避 |
| **make crawl 入库 ≥50 条** | ⚠️ 按用户指示限量验证 | 限量模式（每源 2 条，`CRAWL_MAX_ITEMS_PER_SOURCE=2`）3 轮共入库 14 条真实文档；全量命令已就绪（不设该变量即可，GIA 单日常见 50+ 条），因用户明确"限量 1~2 条测试就行"未跑全量 |
| **连跑 3 次不产生重复文档** | ✅ 通过 | 第 1 轮新增 14；第 2/3 轮新增 0、重复 0、更新 0（幂等键：canonical_url + 30min run_window） |
| 抓取失败源有明确错误日志 | ✅ 通过 | job_run.error + source.health.last_errors；连续失败 5 次熔断 6h |

## 已知限制 / 未验证项

1. **全量 ≥50 条入库未实跑**（用户指示限量）；风险低——去重/礼让/解析均已验证，全量只是数量问题。
2. PDF 附件解析（MinerU/Docling）未实现，Phase 1 仅登记附件链接（04 模型 attachments 字段已就绪）。
3. Playwright 兜底适配器未实现（当前 6 源均无需 JS 渲染）。
4. docker compose 未在本机验证（无 Docker，见 phase-0 报告）。

## 结论

- [x] 抓取管线功能完整、幂等成立，允许进入 Phase 2（已完成）
- [ ] 全量入库量级验证：待用户需要时执行一次不限量 `make crawl`
