# 运行时提示词模板

与 `docs/05_AI_PROMPT_PACK.md` 一一对应，Phase 2 落地：

| 文件 | 链路 | 版本号 |
|---|---|---|
| `p1_classify.md` | 金融政策分类 | classify@v1 |
| `p2_extract.md` | 12 字段结构化抽取 | extract@v1 |
| `p3_scope.md` | 适用范围判定（LLM 通道） | scope@v1 |
| `p4_impact.md` | 8 维影响分析 | impact@v1 |
| `p5_alert.md` | 预警草稿 | alert@v1 |
| `p6_case.md` | 案例比对 | case@v1 |
| `p7_challenge.md` | AI 质疑（审核台侧栏） | challenge@v1 |
| `p8_studio.md` | 政策 2.0 建议书 | studio@v1 |

所有模板必须：声明输出 JSON Schema、要求 evidence span、含 `UNTRUSTED_NOTICE`。
