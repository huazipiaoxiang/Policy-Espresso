// 数据源健康三态点（08 §4 SourceHealthDot）：绿/黄/红 + tooltip
const COLORS: Record<string, string> = {
  ok: "var(--ok)",
  warn: "var(--warn)",
  bad: "var(--danger)",
  unknown: "var(--text-3)",
};

const LABELS: Record<string, string> = {
  ok: "全部正常",
  warn: "部分异常",
  bad: "多源故障",
  unknown: "暂无数据",
};

export default function SourceHealthDot({
  state,
  total,
  unhealthy,
}: {
  state: "ok" | "warn" | "bad" | "unknown";
  total: number;
  unhealthy: number;
}) {
  return (
    <span
      className="flex items-center gap-1.5 text-[11px] text-[var(--text-2)]"
      title={`数据源健康：${LABELS[state]}（${total} 源，${unhealthy} 异常）`}
    >
      <span className="h-2 w-2 rounded-full" style={{ background: COLORS[state] }} />
      数据源
    </span>
  );
}
