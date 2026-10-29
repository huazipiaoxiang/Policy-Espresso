import { RELEVANCE_LABELS } from "./ScopeChip";
import type { PolicyItem } from "@/lib/api";

// 政策行组件 — 基于 Policy Espresso V8.4 原型
// 显示四维度状态：Scope / AI / 审核 / 发布

const PRIORITY_COLOR: Record<string, string> = {
  P0: "var(--p0)",
  P1: "var(--p1)",
  P2: "var(--p2)",
  P3: "var(--p3)",
};

function fmtTime(iso: string | null): string {
  if (!iso) return "—";
  return iso.slice(0, 10);
}

// 状态徽章颜色映射
function getBadgeClass(status: string | undefined): string {
  if (!status) return "bg-[var(--surface-2)] text-[var(--text-3)]";
  if (/高相关|high|已批准|已完成|已发布/.test(status)) return "bg-[var(--ok)]/10 text-[var(--ok)]";
  if (/中相关|medium|待|处理中|初审|复核|审核中/.test(status)) return "bg-[var(--warn)]/10 text-[var(--warn)]";
  if (/低相关|low|失败|拒绝|退回/.test(status)) return "bg-[var(--surface-2)] text-[var(--text-3)]";
  if (/存疑|Uncertain|Failed|Not Assessed|未提及|not_mentioned|不适用|na/.test(status)) return "bg-[var(--surface-2)] text-[var(--text-3)]";
  return "bg-[var(--surface-2)] text-[var(--text-2)]";
}

function StatusBadge({ label, value }: { label: string; value: string | undefined }) {
  return (
    <div className="flex flex-col items-start gap-1 min-w-[80px]">
      <span className="text-[10px] text-[var(--text-3)]">{label}</span>
      <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${getBadgeClass(value)}`}>
        {value ?? "—"}
      </span>
    </div>
  );
}

export default function PolicyRow({ policy }: { policy: PolicyItem }) {
  const isLowRelevance = policy.target_entity_status === "low";
  const relevanceStatus = RELEVANCE_LABELS[policy.target_entity_status]?.text ?? policy.target_entity_status;

  return (
    <div className={`relative flex items-center gap-3 border-b border-[var(--border)] px-3 py-2.5 hover:bg-[var(--surface-2)] ${isLowRelevance ? "opacity-60" : ""}`}>
      {/* 优先级竖条 */}
      <span
        className="absolute left-0 top-0 h-full w-[3px]"
        style={{ background: PRIORITY_COLOR[policy.priority] ?? "var(--p3)" }}
      />

      {/* 政策标题 */}
      <div className="min-w-0 flex-1">
        <div className="text-[13px] font-medium truncate">{policy.title}</div>
        <div className="text-[11px] text-[var(--text-3)] mt-0.5">{policy.issuing_body} · {fmtTime(policy.published_at)}</div>
      </div>

      {/* 四维度状态 */}
      <div className="flex gap-2 shrink-0">
        <StatusBadge label="相关性" value={relevanceStatus} />
        <StatusBadge label="AI" value={policy.status === "processed" ? "已完成" : policy.status === "processing" ? "处理中" : "未开始"} />
        <StatusBadge label="审核" value={policy.status === "pending_review" ? "待审核" : policy.status === "approved" ? "已批准" : policy.status} />
        <StatusBadge label="发布" value={policy.status === "published" ? "已发布" : "未发布"} />
      </div>

      {/* 优先级 */}
      <span
        className="shrink-0 rounded-full px-2 py-0.5 font-mono text-[10px] font-semibold"
        style={{ color: PRIORITY_COLOR[policy.priority], background: "var(--surface-2)" }}
      >
        {policy.priority}
      </span>

      {/* 外资行差异标签 */}
      {policy.foreign_bank_differential && (
        <span className="shrink-0 rounded border border-[var(--danger)] px-1.5 text-[10px] text-[var(--danger)]">
          ⚠ 外资行差异
        </span>
      )}
    </div>
  );
}
