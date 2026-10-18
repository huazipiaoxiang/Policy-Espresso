import SourceHealthDot from "./SourceHealthDot";

// 顶栏（08 §2）：面包屑 | 搜索占位 | 数据源健康点 | 待审徽章 | 用户
export default function Topbar({
  sourcesTotal = 0,
  sourcesUnhealthy = 0,
  pendingReview = 0,
}: {
  sourcesTotal?: number;
  sourcesUnhealthy?: number;
  pendingReview?: number;
}) {
  const healthState =
    sourcesTotal === 0 ? "unknown" : sourcesUnhealthy === 0 ? "ok" : sourcesUnhealthy >= 3 ? "bad" : "warn";

  return (
    <header className="fixed left-[232px] right-0 top-0 z-10 flex h-14 items-center gap-4 border-b border-[var(--border)] bg-[var(--surface)] px-6">
      <span className="text-[13px] text-[var(--text-2)]">雷达总览</span>
      <div className="ml-auto flex items-center gap-4">
        <button
          className="flex h-8 w-56 items-center rounded-md border border-[var(--border)] bg-[var(--surface-2)] px-3 text-[12px] text-[var(--text-3)]"
          title="全局搜索（Phase 3 接入）"
        >
          搜索政策 / 案例 …<span className="ml-auto font-mono text-[10px]">⌘K</span>
        </button>
        <SourceHealthDot state={healthState} total={sourcesTotal} unhealthy={sourcesUnhealthy} />
        <span className="rounded-full bg-[var(--accent-weak)] px-2 py-0.5 text-[11px] text-[var(--accent)]">
          待审 {pendingReview}
        </span>
        <span className="flex h-7 w-7 items-center justify-center rounded-full bg-[var(--surface-2)] text-[11px] text-[var(--text-2)]">
          我
        </span>
      </div>
    </header>
  );
}
