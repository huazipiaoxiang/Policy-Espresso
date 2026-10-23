import HeatmapMatrix from "@/components/HeatmapMatrix";
import { getBusinessMap, getOverview } from "@/lib/api";

export const dynamic = "force-dynamic";

// 业务图谱（08 §3.5）
export default async function BusinessMapPage() {
  const [overview, data] = await Promise.all([getOverview(), getBusinessMap()]);

  return (
    <main className="mx-auto max-w-content px-6 pb-10 py-6">
        <div className="mb-3 flex items-center gap-2">
          <h1 className="text-[16px] font-semibold">业务图谱</h1>
          <span className="text-[12px] text-[var(--text-3)]">
            业务线 × 政策主题 敏感度矩阵（近 {data?.months ?? 12} 个月相关政策数与平均影响分）
          </span>
        </div>
        {data ? (
          <>
            <div className="card p-4">
              <HeatmapMatrix data={data} />
            </div>
            <div className="card mt-4 p-4">
              <div className="section-label">高敏感主题 Top 5（相关政策数）</div>
              <div className="mt-2 space-y-1.5">
                {Object.entries(data.top_themes).map(([theme, count]) => (
                  <div key={theme} className="flex items-center gap-2 text-[12px]">
                    <span className="w-32 shrink-0 text-[var(--text-2)]">{theme}</span>
                    <div className="h-3 rounded bg-[var(--accent)]" style={{ width: `${Math.max(count * 24, 4)}px` }} />
                    <span className="font-mono text-[var(--text-3)]">{count}</span>
                  </div>
                ))}
              </div>
            </div>
          </>
        ) : (
          <div className="card p-8 text-center text-[12px] text-[var(--text-3)]">API 未连接</div>
        )}
      </main>
  );
}
