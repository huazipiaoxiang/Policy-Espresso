// ScopeChip（08 §4）：政策对目标实体的相关性（high/medium/low/not_mentioned/na）
export const RELEVANCE_LABELS: Record<string, { text: string; color: string; icon: string }> = {
  high: { text: "高相关", color: "var(--ok)", icon: "✓" },
  medium: { text: "中相关", color: "var(--warn)", icon: "◆" },
  low: { text: "低相关", color: "var(--text-3)", icon: "—" },
  not_mentioned: { text: "未提及", color: "var(--text-2)", icon: "—" },
  na: { text: "不适用", color: "var(--text-3)", icon: "—" },
};

export default function ScopeChip({ status }: { status: string }) {
  const item = RELEVANCE_LABELS[status] ?? RELEVANCE_LABELS.not_mentioned;
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px]"
      style={{ color: item.color, background: "var(--surface-2)", border: `1px solid ${item.color}` }}
    >
      <span aria-hidden>{item.icon}</span>
      {item.text}
    </span>
  );
}
