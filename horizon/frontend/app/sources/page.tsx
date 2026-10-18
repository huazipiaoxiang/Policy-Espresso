import Topbar from "@/components/Topbar";
import { getOverview } from "@/lib/api";
import { getSources } from "@/lib/api";

export const dynamic = "force-dynamic";

// 数据源健康（08 §3.7）
export default async function SourcesPage() {
  const [overview, sources] = await Promise.all([getOverview(), getSources()]);
  const items = sources?.items ?? [];

  const stateOf = (health: Record<string, unknown>) => {
    const fail = Number(health.consecutive_fail ?? 0);
    if (health.circuit_open_until) return { label: "熔断", color: "var(--danger)" };
    if (fail >= 3) return { label: "异常", color: "var(--danger)" };
    if (fail >= 1) return { label: "波动", color: "var(--warn)" };
    return { label: "正常", color: "var(--ok)" };
  };

  return (
    <>
      <Topbar
        sourcesTotal={overview?.sources_total ?? 0}
        sourcesUnhealthy={overview?.sources_unhealthy ?? 0}
        pendingReview={overview?.pending_review ?? 0}
      />
      <main className="mx-auto max-w-content px-6 pb-10 pt-[72px]">
        <div className="mb-3 flex items-center gap-2">
          <h1 className="text-[16px] font-semibold">数据源健康</h1>
          <span className="text-[12px] text-[var(--text-3)]">
            {overview?.sources_total ?? 0} 个源 · {overview?.sources_unhealthy ?? 0} 个异常 · 连续失败 5 次熔断 6h
          </span>
        </div>
        <div className="card overflow-hidden">
          <table className="w-full text-[12px]">
            <thead>
              <tr className="border-b border-[var(--border)] text-left text-[var(--text-3)]">
                <th className="px-3 py-2 font-medium">源</th>
                <th className="px-3 py-2 font-medium">层级</th>
                <th className="px-3 py-2 font-medium">适配器</th>
                <th className="px-3 py-2 font-medium">最近成功</th>
                <th className="px-3 py-2 font-medium">最近新增</th>
                <th className="px-3 py-2 font-medium">状态</th>
              </tr>
            </thead>
            <tbody>
              {items.map((s) => {
                const state = stateOf(s.health ?? {});
                const lastStats = (s.health?.last_run_stats ?? {}) as Record<string, number>;
                return (
                  <tr key={s.id} className="border-b border-[var(--border)] last:border-0">
                    <td className="px-3 py-2">
                      <div className="text-[var(--text)]">{s.name}</div>
                      <div className="font-mono text-[10px] text-[var(--text-3)]">{s.code}</div>
                    </td>
                    <td className="px-3 py-2 text-[var(--text-2)]">T{s.tier}</td>
                    <td className="px-3 py-2 text-[var(--text-2)]">{s.adapter}</td>
                    <td className="px-3 py-2 text-[var(--text-3)]">
                      {s.health?.last_ok_at
                        ? new Intl.DateTimeFormat("zh-HK", { timeZone: "Asia/Hong_Kong", dateStyle: "short", timeStyle: "short" }).format(new Date(String(s.health.last_ok_at)))
                        : "—"}
                    </td>
                    <td className="px-3 py-2 font-mono text-[var(--text-2)]">{lastStats.created ?? 0}</td>
                    <td className="px-3 py-2">
                      <span className="inline-flex items-center gap-1.5" style={{ color: state.color }}>
                        <span className="h-2 w-2 rounded-full" style={{ background: state.color }} />
                        {state.label}
                      </span>
                    </td>
                  </tr>
                );
              })}
              {items.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-3 py-8 text-center text-[var(--text-3)]">
                    暂无数据源（make seed 导入）
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </main>
    </>
  );
}
