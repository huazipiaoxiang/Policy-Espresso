// 空状态（08 §4）：必须给"下一步做什么"
export default function EmptyState({
  title,
  hint,
  action,
}: {
  title: string;
  hint: string;
  action?: string;
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-card border border-dashed border-[var(--border-strong)] px-6 py-12 text-center">
      <div className="text-[13px] text-[var(--text-2)]">{title}</div>
      <div className="mt-1 text-[12px] text-[var(--text-3)]">{hint}</div>
      {action && (
        <div className="mt-3 rounded-btn border border-[var(--border)] bg-[var(--surface-2)] px-3 py-1.5 text-[12px] text-[var(--accent)]">
          {action}
        </div>
      )}
    </div>
  );
}
