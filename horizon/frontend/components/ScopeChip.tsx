// ScopeChip（08 §4）：适用范围状态，"被排除"必须带 ⚠ 图标
const MAP: Record<string, { text: string; color: string; icon: string }> = {
  covered: { text: "被覆盖", color: "var(--ok)", icon: "✓" },
  excluded: { text: "被排除", color: "var(--p0)", icon: "⚠" },
  not_mentioned: { text: "未提及", color: "var(--text-2)", icon: "—" },
  na: { text: "不适用", color: "var(--text-3)", icon: "—" },
};

export default function ScopeChip({ status }: { status: string }) {
  const item = MAP[status] ?? MAP.not_mentioned;
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
