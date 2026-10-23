import ReviewConsole from "@/components/ReviewConsole";
import { getOverview, getReviewTasks } from "@/lib/api";

export const dynamic = "force-dynamic";

// 审核台（08 §3.3）
export default async function ReviewPage() {
  const [overview, tasks] = await Promise.all([getOverview(), getReviewTasks()]);
  return (
    <main className="mx-auto max-w-content px-6 pb-10 pt-[72px]">
      <div className="mb-6">
        <div className="mb-1 text-[10px] uppercase tracking-wider text-[var(--text-3)]">Review Workspace</div>
        <h1 className="text-[20px] font-semibold">审核工作台</h1>
        <p className="mt-1 text-[13px] text-[var(--text-2)]">
          P0/P1 双签 · P2/P3 单签 · 驳回必填原因码 · 全程审计留痕
        </p>
      </div>
      <ReviewConsole initialTasks={tasks?.items ?? []} />
    </main>
  );
}
