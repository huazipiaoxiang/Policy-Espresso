import type { PolicyItem } from "@/lib/api";

// 48px 紧凑政策行（08 §3.1）：左侧 3px 优先级竖条 + 最多 3 个标签
const PRIORITY_COLOR: Record<string, string> = {
  P0: "var(--p0)",
  P1: "var(--p1)",
  P2: "var(--p2)",
  P3: "var(--p3)",
};

const SCOPE_LABEL: Record<string, { text: string; danger?: boolean }> = {
  covered: { text: "被覆盖" },
  excluded: { text: "⚠ 被排除", danger: true },
  not_mentioned: { text: "未提及" },
  na: { text: "不适用" },
};

function fmtTime(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return new Intl.DateTimeFormat("zh-HK", { timeZone: "Asia/Hong_Kong", dateStyle: "short" }).format(d);
}

export default function PolicyRow({ policy }: { policy: PolicyItem }) {
  const scope = SCOPE_LABEL[policy.target_entity_status];
  return (
    <div className="relative flex h-12 items-center gap-3 border-b border-[var(--border)] px-3 hover:bg-[var(--surface-2)]">
      <span
        className="absolute left-0 top-0 h-full w-[3px]"
        style={{ background: PRIORITY_COLOR[policy.priority] ?? "var(--p3)" }}
      />
      <span className="min-w-0 flex-1 truncate text-[13px]">{policy.title}</span>
      <span className="shrink-0 text-[11px] text-[var(--text-3)]">{policy.issuing_body}</span>
      <span className="shrink-0 font-mono text-[11px] text-[var(--text-3)]">{fmtTime(policy.published_at)}</span>
      {policy.foreign_bank_differential && (
        <span className="shrink-0 rounded-full border border-[var(--p0)] px-1.5 text-[10px] text-[var(--p0)]">
          ⚠ 外资行差异
        </span>
      )}
      {scope && (
        <span
          className={`shrink-0 rounded-full px-1.5 text-[10px] ${
            scope.danger ? "bg-[var(--p0)]/10 text-[var(--p0)]" : "bg-[var(--surface-2)] text-[var(--text-2)]"
          }`}
        >
          {scope.text}
        </span>
      )}
      <span
        className="shrink-0 rounded-full px-1.5 font-mono text-[10px]"
        style={{ color: PRIORITY_COLOR[policy.priority], background: "var(--surface-2)" }}
      >
        {policy.priority}
      </span>
    </div>
  );
}
