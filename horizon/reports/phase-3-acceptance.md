# Phase 3 验收报告 · 审核台与分发

日期：2026-10-17 · 验收依据：`docs/01_AGENT_PROMPT.md` §六 Phase 3 + `docs/08` §3.3

## 验收项核对

| 验收标准 | 结果 | 证据 |
|---|---|---|
| 审核队列（按 SLA 排序） | ✅ | `GET /review-tasks`；前端 /review 左列表 + Countdown 组件 |
| 双签（P0/P1 两级，P2/P3 单签） | ✅ | `domain/review.decide`：一级通过生成 L2 任务留 in_review；`required_review_levels` |
| 驳回必填原因码 | ✅ | 422 REASON_REQUIRED；6 个原因码（证据不足/影响误判/适用性误判/表述不当/重复/其他） |
| 退回补充 | ✅ | request_info → needs_info（状态机合法转移） |
| 领取防并发双审 | ✅ | claim 409 TASK_NOT_CLAIMABLE（测试覆盖） |
| 批量操作（仅 P3 通过/标记重复） | ✅ | `batch_decide`；非 P3 批量通过被拒（测试覆盖） |
| 键盘 J/K/Enter/a/x | ✅ | ReviewConsole 键盘导航（前端实现） |
| 提交审核强制字段校验 | ✅ | 422 MISSING_REQUIRED（evidence/confidence/affected/recommended_actions/summary） |
| Notifier 分发（站内必做 + webhook 可选） | ✅ | InAppNotifier 必有；Email/企微/飞书 webhook 未配置自动降级站内（E2E 实证 channels=[inapp]） |
| 审计日志（状态变更/字段修改/模型调用可查可导出） | ✅ | /admin/audit + CSV 导出 + /admin/llm-calls；claim 时 policy 状态转移也留痕（本轮修的根因） |
| **未审核分发 409** | ✅ | rejected/in_review 状态 dispatch 均 409 NOT_APPROVED（测试 + E2E） |
| **审核通过后审计链可回放** | ✅ | E2E：submit_review → claim_task → review_approve×2 → dispatch 全链可查 |
| **驳回后不可直接发布** | ✅ | rejected → dispatch 409；重开 rejected→draft 必须带原因（状态机强制） |
| SSE 事件流 | ✅ | `/stream/events` 零依赖实现（统计增量推送） |

## 真人功能验证（E2E，经 BFF 代理）

```
claim → approve(L1, in_review) → L2 任务自动生成 → claim → approve(L2, approved)
→ dispatch → published + Alert(approved) + Dispatch(inapp)
```
BFF 代理（`/api/proxy/*`）保证 `X-API-Key` 只在服务端，不进浏览器包。

## 测试

- pytest：**62 passed**（新增 Phase 3 七个用例：双签链、驳回拦截、必填校验、批量两种、红队质疑、CSV 导出）
- 前端 build 通过；/review /audit /alerts /sources 全部 200

## 已知限制

1. SSE 为统计增量快照，未做细粒度事件（政策/任务/审核提醒分类推送）。
2. 审核中字段修改的 diff 二次确认（08 §3.3）UI 未做弹层，field_diffs 已入模型与 API。
3. P7 LLM 版红队质疑未接（当前为确定性规则版：双通道冲突/无证据维度/时效虚高/零证据）。
4. actor 固定 `local.analyst`（MVP 单用户），OIDC 接入后替换。

## 结论

- [x] Phase 3 功能完整、硬规则（409/双签/审计）全部有测试与 E2E 证据，进入 Phase 4
