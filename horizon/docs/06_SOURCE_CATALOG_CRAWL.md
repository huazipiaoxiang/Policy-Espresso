# 06 · 数据源清单与抓取策略

## 1. 分层原则

| 层级 | 定义 | 处理方式 |
|---|---|---|
| **Tier 1 一手权威** | 政府/监管机构官网、宪报、立法会 | 必抓、优先、30 分钟轮询、字段全量抽取 |
| **Tier 2 财经媒体** | 主流财经媒体 | 抓标题+摘要+链接，用于**线索发现**（反向找原始文件） |
| **Tier 3 智库/律所** | 研究报告、客户通讯 | 每日一次，用于案例与解读补充 |
| **Tier 4 非结构化** | 社交平台、公众号 | MVP 不做（合规与稳定性风险高） |

> 关键设计：Tier 2/3 的文章**不是结论来源**，只用来触发"去 Tier 1 找原文"。预警必须引用 Tier 1 原文。

## 2. Tier 1 清单（中国香港）

| code | 机构 | 入口 | 适配器 | 核验状态 |
|---|---|---|---|---|
| `hkma_press` | 香港金融管理局 · 新闻稿 | https://www.hkma.gov.hk/chi/news-and-media/press-releases/ | rss_index → listing | RSS 频道页已确认：`/chi/other-information/rss/` |
| `hkma_circular` | 金管局 · 指引及通告 | https://www.hkma.gov.hk/chi/news-and-media/guidelines-circulars/ | rss_index | 同上（含 Guidelines & Circulars 频道） |
| `hkma_speech` | 金管局 · 演讲辞 | 同上 | rss_index | 同上 |
| `hkma_legco` | 金管局 · 立法会事务 | 同上 | rss_index | 同上 |
| `gia_today` | 政府新闻公报 | https://www.info.gov.hk/gia/general/today.htm | listing | 需按日归档 URL 规律补抓 |
| `newsgov_fin` | 政府新闻网 · 财经 | https://www.news.gov.hk/ | rss | 已确认财经频道 RSS：`/en/categories/finance/html/articlelist.rss.xml`（中文 `/tc/` 同构） |
| `fstb` | 财经事务及库务局 | https://www.fstb.gov.hk/ | listing | 待核验列表页结构 |
| `legco_bill` | 立法会 · 法案 | https://www.legco.gov.hk/ | listing | 待核验 |
| `legco_panel` | 立法会 · 事务委员会文件 | https://www.legco.gov.hk/ | listing | 待核验（财经事务委员会优先） |
| `gazette` | 香港宪报 | https://www.gld.gov.hk/egazette/ | listing + pdf | 待核验（法律修订的唯一权威源） |
| `policy_address` | 施政报告 | https://www.policyaddress.gov.hk/ | manual/pdf | 年度，人工触发 |
| `budget` | 财政预算案 | https://www.budget.gov.hk/ | manual/pdf | 年度 |
| `sfc` | 证券及期货事务监察委员会 | https://www.sfc.hk/ | rss/listing | 待核验 |
| `ia` | 保险业监管局 | https://www.ia.org.hk/ | listing | 待核验 |
| `mpfa` | 积金局 | https://www.mpfa.org.hk/ | listing | 待核验 |
| `hkmc` | 香港按证保险公司 | https://www.hkmc.com.hk/ | listing | 待核验 |

> 「待核验」= 实现时先用 `curl -I` + 解析首页找 RSS/sitemap，再决定 adapter。**不要凭猜测写选择器。**

## 3. Tier 1 清单（内地 / 大湾区）

| code | 机构 | 入口 | 关注点 |
|---|---|---|---|
| `mofcom_cepa` | 商务部 · 台港澳司（CEPA） | http://tfs.mofcom.gov.cn/ | CEPA 及补充协议、服务贸易协议修订 |
| `hmo` | 国务院港澳事务办公室 | https://www.hmo.gov.cn/ | 中央对港政策 |
| `pbc` | 中国人民银行 | http://www.pbc.gov.cn/ | 跨境人民币、支付、金融市场开放 |
| `safe` | 国家外汇管理局 | https://www.safe.gov.cn/ | 跨境资金流动、外债、QFLP/QDII |
| `nfra` | 国家金融监督管理总局 | https://www.nfra.gov.cn/ | 银行保险监管、外资行准入 |
| `ndrc` | 国家发展改革委 | https://www.ndrc.gov.cn/ | 负面清单、产业政策 |
| `gd_gov` | 广东省人民政府 | https://www.gd.gov.cn/ | 省级政策（**用例 1 的来源**） |
| `gd_finance` | 广东省财政厅 / 地方金融管理局 | 待核验 | 贴息、补贴、风险补偿 |
| `sz_gov` | 深圳市人民政府 | https://www.sz.gov.cn/ | 市级配套 |
| `nansha` | 广州南沙 | https://www.gzns.gov.cn/ | 先行先试 |
| `qianhai` | 深圳前海 | https://qh.sz.gov.cn/ | 跨境金融 |
| `hengqin` | 横琴粤澳深度合作区 | https://www.hengqin.gov.cn/ | 跨境、澳门衔接 |
| `hetao` | 河套深港科技创新合作区 | 待核验 | 数据跨境、科研资金 |

## 4. Tier 2 / 3（线索与解读）

- 中国香港：信报、明报、香港01、经济日报、SCMP、Now 财经、AAStocks
- 内地：财新、21 世纪经济报道、第一财经
- 国际：Reuters、Bloomberg（需订阅，按授权使用）
- 智库/律所：HKIMR、HKTDC Research、金管局研究公报、主要律所客户通讯

抓取策略：RSS 优先；仅存标题、摘要（≤300 字）、发布时间、链接。**不存全文**（版权）。

## 5. 抓取实现规范

### 5.1 适配器接口

```python
class SourceAdapter(Protocol):
    def discover(self, since: datetime) -> list[ItemRef]: ...
    def fetch(self, ref: ItemRef) -> RawDoc: ...      # html + headers + pdf bytes
```

- `discover` 只做"发现新条目"，产出 `{url, title, published_at_guess, external_id}`
- `fetch` 只做"取回原始内容"，不做解析
- 解析统一在 `normalize.py`，便于替换解析器

### 5.2 优先级与兜底

```
RSS → sitemap diff → 列表页 diff（前 3 页）→ Playwright 渲染 → 人工上传
```
每降一级记录 `fallback_level`，用于监控站点改版。

### 5.3 限速与礼让

- 单域名 ≤1 req/s，随机 200–600ms 抖动
- 并发 ≤4（全局），单域名串行
- 夜间（02:00–06:00 HKT）可放宽到 2 req/s
- UA：`HORIZON-PolicyMonitor/0.1 (+policy-research; contact@example.com)`
- 遵守 `robots.txt`（`urllib.robotparser`），Disallow 即跳过并记录
- 响应 429/503：指数退避 30s/120s/600s，三次后熔断 6 小时

### 5.4 变更检测

1. 正文归一化（去空白、去导航、统一全半角）→ sha256
2. hash 变化 → 新建 `document_version`，用 `difflib.SequenceMatcher` 生成段落级 diff，`changed_ratio` 计算变化比例
3. `changed_ratio > 0.3` 视为"实质修订" → 重新触发完整分析
4. `0 < changed_ratio ≤ 0.3` → 只更新文本，打 `minor_edit` 标记，不重跑 LLM（省钱）
5. 标题变化但正文未变 → 记录，不触发

### 5.5 去重

- URL 归一化：去 `utm_*`、`fbclid`、`#anchor`、统一 `http→https`、去 `www.`、去末尾 `/`
- 跨源去重：同一政策常被多个源转载 → 用 `(标题 simhash, 发文机关, 发布日期)` 三元组聚类，保留 Tier 1 为 `primary_document`，其余挂 `duplicate_of`
- 附件去重：PDF 内容 sha256

### 5.6 PDF 与附件

- 政策文件常是 PDF/Word 附件，正文页只有一句"详见附件"
- 解析：MinerU / Docling（保留表格结构）→ markdown，作为 `attachment_text` 参与抽取
- 扫描件：先判断是否有文本层（`pdfplumber` 提取字符数 < 100 → 走 OCR），MVP 可先跳过并在审核台标注"附件为扫描件，需人工阅读"

## 6. 数据源健康与告警

`source.health` 每日计算：成功率、平均延迟、新增条数、连续失败次数。
- 连续失败 3 次 → 站内告警
- 连续失败 5 次 → 熔断 6 小时 + 邮件
- 某源 7 天新增 0 条（而历史日均 >0）→ "疑似改版"告警

> 这条最容易被忽略但最致命：站点改版后程序不报错，只是静默不产出，一个月后才发现漏了政策。

## 7. 合规与法律边界（必须遵守）

1. **robots.txt 优先**，Disallow 路径一律不抓。
2. **版权**：政府文件多数可转载但需注明来源；媒体内容只存摘要+链接，不存全文、不二次分发。
3. **数据库权利**：不批量复制他人数据库内容。
4. **个人资料**：抓到的网页若含个人姓名/联系方式，入库前脱敏（MVP 阶段可在解析时丢弃 `tel/email` 字段）。
5. **数据出境**：若抓取节点在中国香港、存储在内地，需评估是否构成数据出境（建议：只回传政策文本与元数据，不回传任何个人信息）。
6. **服务条款**：付费媒体内容需在授权范围内使用；不得绕过付费墙。
7. **内部合规**：预警内容属"内部研究材料"，不得直接对客户引用；对外须经审核并按 P8 改写。

## 8. 抓取自测清单（Phase 1 验收用）

- [ ] 每个源连续跑 3 次，无重复入库
- [ ] 断网重连后能自动恢复，不产生重复
- [ ] robots.txt 禁止的路径确实未抓
- [ ] 站点返回 404 时，任务记为 failed 但不影响其他源
- [ ] PDF 附件能正确解析并入库（至少 3 个真实样本）
- [ ] 修改某篇文章后，能生成 version 与 diff
- [ ] 单源熔断后，健康页显示红色且给出原因
