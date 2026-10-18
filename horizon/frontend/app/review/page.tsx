import ReviewConsole from "@/components/ReviewConsole";
import Topbar from "@/components/Topbar";
import { getOverview, getReviewTasks } from "@/lib/api";

export const dynamic = "force-dynamic";

// 审核台（08 §3.3）
export default async function ReviewPage() {
  const [overview, tasks] = await Promise.all([getOverview(), getReviewTasks()]);
  return (
    <>
      <Topbar
        sourcesTotal={overview?.sources_total ?? 0}
        sourcesUnhealthy={overview?.sources_unhealthy ?? 0}
        pendingReview={overview?.pending_review ?? 0}
      />
      <main className="mx-auto max-w-content px-6 pb-10 pt-[72px]">
        <div className="mb-3 flex items-center gap-2">
          <h1 className="text-[16px] font-semibold">审核台</h1>
          <span className="text-[12px] text-[var(--text-3)]">
            P0/P1 双签 · P2/P3 单签 · 驳回必填原因码 · 全程审计留痕
          </span>
        </div>
        <ReviewConsole initialTasks={tasks?.items ?? []} />
      </main>
    </>
  );
}
