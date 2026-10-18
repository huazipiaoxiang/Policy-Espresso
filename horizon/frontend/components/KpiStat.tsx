// KPI 卡（08 §4 KpiStat）：大数字 + 变化说明
export default function KpiStat({
  label,
  value,
  hint,
  tone = "default",
}: {
  label: string;
  value: string | number;
  hint?: string;
  tone?: "default" | "accent" | "danger";
}) {
  const toneClass =
    tone === "accent" ? "text-[var(--accent)]" : tone === "danger" ? "text-[var(--p0)]" : "text-[var(--text)]";
  return (
    <div className="card flex-1 px-4 py-3">
      <div className="section-label">{label}</div>
      <div className={`mt-1 font-mono text-[32px] font-semibold leading-9 ${toneClass}`}>{value}</div>
      {hint && <div className="mt-0.5 text-[11px] text-[var(--text-3)]">{hint}</div>}
    </div>
  );
}
