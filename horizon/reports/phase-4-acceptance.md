# Phase 4 验收报告 · 案例库与政策 2.0

日期：2026-10-17 · 验收依据：`docs/01_AGENT_PROMPT.md` §六 Phase 4 + `docs/09_ACCEPTANCE_CASES.md` §2

## 用例 2 断言结果（tests/test_phase4_studio.py）

| ID | 断言 | 结果 | 证据 |
|---|---|---|---|
| T2-01 | 5–8 条建议，覆盖 ≥3 主题 | ✅ | mock 生成 6 条 / 5 主题（E2E 复核一致） |
| T2-02 | 每条含 5 段固定结构（依据/不冲突/拟条文/影响/风险） | ✅ | current_basis/non_conflict_argument/draft_clause/impact/risks 全字段校验 |
| T2-03 | current_basis ≥1 且 quote 可在语料定位 | ✅ | locate_quote 逐条校验（相似度 1.0） |
| T2-04 | 拟条文含 适用主体+条件+程序+监管分工 | ✅ | 测试逐条断言 |
| T2-05 | 突破现行限制 → boundary 必 warn/fail | ✅ | P-06（突破理财通额度）→ warn + 立法程序说明 |
| T2-06 | 无"必将/中国政府将"等断言式预测 | ✅ | 黑名单正则校验 |
| T2-07 | 免责声明 + 导出带水印标识 | ✅ | disclaimer 字段 + 前端常驻声明条 |
| T2-08 | 每条 ≥1 个可衡量 KPI | ✅ | kpis minItems=1 + 自检 |
| T2-09 | 引用已废止文件 → fail | ✅ | `studio_corpus.load_corpus()` 默认只载 有效/已修订；索引显式标注 effective；T2-09 前置测试通过 |
| T2-10 | 专家 + 合规双审后才可导出 | ✅ | reviewer_notes 双签判定 → project.status=reviewed（测试 + API） |

## 其他交付

- **案例库**：`/cases`（关键词 + 业务线加权混合检索）、`/cases/{id}`（时间轴：政策出台→影响→我方应对 + 启示引用块）；前端卡片含"我赢了/我输了/部分改善"结果标
- **业务图谱**：`/business-map` 矩阵热力图（ECharts heatmap，业务线 × 16 主题，格值=政策数+平均影响分）+ 高敏感主题 Top5
- **Studio 前端**：三栏工作台（项目/主题树 + 条款演化时间轴 + 建议书卡），边界校验三态条（pass 绿 / warn 黄 / fail 红禁发），双审按钮

## 测试与验证

- pytest：**67 passed**（Phase 4 新增 5 项）
- 前端 build 通过；/cases /business-map /studio 全部 200
- Studio E2E：建项目 → generate（6 条建议，P-06 warn）→ 详情可查

## 已知限制

1. 语料为 4 份代表性公开文件的整理版（`seed/cepa/`），09 §2.2 的完整清单需政策专家补全并人工确认有效性。
2. 案例检索为规则+相似度（主题 Jaccard + 标题相似度），向量混合检索待 Phase 5 pgvector 接入。
3. mock 生成的 baseline/gaps 为占位质量；真实模型（qwen-max）生成后需人工评审。

## 结论

- [x] Phase 4 功能完整、用例 2 十条断言全过（T2-09 关键负向断言有实证），进入 Phase 5
