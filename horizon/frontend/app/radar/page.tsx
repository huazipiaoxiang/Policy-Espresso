import KpiStat from "@/components/KpiStat";
import PolicyList from "@/components/PolicyList";
import RadarClient from "@/components/RadarClient";
import Topbar from "@/components/Topbar";
import { getOverview } from "@/lib/api";

// 雷达总览（08 §3.1）：KPI 条 + 政策流（分页） + 侧栏（待审队列/数据源健康）
export default async function RadarPage() {
  const overview = await getOverview();

  return (
    <RadarClient>
      <Topbar
        sourcesTotal={overview?.sources_total ?? 0}
        sourcesUnhealthy={overview?.sources_unhealthy ?? 0}
        pendingReview={overview?.pending_review ?? 0}
      />
      <main className="mx-auto max-w-content px-6 pb-10 pt-[72px]">
        <section className="flex gap-4">
          <KpiStat label="今日新增" value={overview?.today_new ?? 0} hint="vs 昨日 —" />
          <KpiStat label="待审" value={overview?.pending_review ?? 0} hint="0 项超 SLA" tone="accent" />
          <KpiStat label="P0 / P1" value={overview?.p0_p1_open ?? 0} hint="未完成" tone="danger" />
          <KpiStat
            label="平均响应"
            value={overview?.avg_response_min != null ? `${overview.avg_response_min}min` : "—"}
            hint="目标 ≤30min"
          />
        </section>

        <div className="mt-4 grid grid-cols-12 gap-4">
          <PolicyList />
          <aside className="col-span-4 space-y-4">
            <div className="card p-3">
              <div className="section-label">待审队列</div>
              <div className="mt-2 text-[12px] text-[var(--text-3)]">
                暂无待审任务（Phase 3 审核台上线）
              </div>
            </div>
            <div className="card p-3">
              <div className="section-label">数据源健康</div>
              <div className="mt-2 text-[12px] text-[var(--text-2)]">
                {overview
                  ? `${overview.sources_total} 个源已配置，${overview.sources_unhealthy} 个异常`
                  : "API 未连接"}
              </div>
            </div>
          </aside>
        </div>
      </main>
    </RadarClient>
  );
}
