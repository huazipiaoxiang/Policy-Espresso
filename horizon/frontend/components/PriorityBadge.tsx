// PriorityBadge（08 §4）：色 + 文字 + 图标三重编码
const COLORS: Record<string, string> = {
  P0: "var(--p0)",
  P1: "var(--p1)",
  P2: "var(--p2)",
  P3: "var(--p3)",
};

const ICONS: Record<string, string> = { P0: "▲", P1: "◆", P2: "■", P3: "●" };

export default function PriorityBadge({ level, score }: { level: string; score?: number }) {
  const color = COLORS[level] ?? "var(--p3)";
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 font-mono text-[10px]"
      style={{ color, background: "var(--surface-2)", border: `1px solid ${color}` }}
      title={score != null ? `综合分 ${score}` : undefined}
    >
      <span aria-hidden>{ICONS[level] ?? "●"}</span>
      {level}
    </span>
  );
}
