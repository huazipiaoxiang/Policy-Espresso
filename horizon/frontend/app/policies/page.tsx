import Link from "next/link";
import EmptyState from "@/components/EmptyState";
import PolicyRow from "@/components/PolicyRow";
import Topbar from "@/components/Topbar";
import { getOverview, getPolicies } from "@/lib/api";

export const dynamic = "force-dynamic";

const FILTERS: { label: string; href: string }[] = [
  { label: "全部", href: "/policies" },
  { label: "待审", href: "/policies?status=pending_review" },
  { label: "P0/P1", href: "/policies?priority=P0" },
];

// 政策列表（08 §3.2 的入口）
export default async function PoliciesPage({
  searchParams,
}: {
  searchParams: { status?: string; priority?: string };
}) {
  const [overview, policies] = await Promise.all([
    getOverview(),
    getPolicies(
      `${searchParams.status ? `&status=${searchParams.status}` : ""}${
        searchParams.priority ? `&priority=${searchParams.priority}` : ""
      }`,
    ),
  ]);
  const items = policies?.items ?? [];

  return (
    <>
      <Topbar
        sourcesTotal={overview?.sources_total ?? 0}
        sourcesUnhealthy={overview?.sources_unhealthy ?? 0}
        pendingReview={overview?.pending_review ?? 0}
      />
      <main className="mx-auto max-w-content px-6 pb-10 pt-[72px]">
        <div className="mb-3 flex items-center gap-2">
          <h1 className="text-[16px] font-semibold">政策库</h1>
          <span className="text-[12px] text-[var(--text-3)]">共 {policies?.total ?? 0} 条</span>
          <div className="ml-auto flex gap-1.5">
            {FILTERS.map((f) => (
              <Link
                key={f.label}
                href={f.href}
                className="rounded-btn border border-[var(--border)] bg-[var(--surface-2)] px-2.5 py-1 text-[12px] text-[var(--text-2)] hover:text-[var(--text)]"
              >
                {f.label}
              </Link>
            ))}
          </div>
        </div>

        <div className="card overflow-hidden">
          <div className="flex h-10 items-center border-b border-[var(--border)] px-3">
            <span className="section-label">政策卡片（按发布时间）</span>
          </div>
          {items.length === 0 ? (
            <div className="p-6">
              <EmptyState
                title="暂无政策卡片"
                hint="抓取与分析管线产出政策卡后在此展示（Phase 1/2 已实现，当前库为空）"
                action="make seed && make crawl && python -m app.jobs.analyze_job"
              />
            </div>
          ) : (
            items.map((p) => (
              <Link key={p.id} href={`/policies/${p.id}`} className="block">
                <PolicyRow policy={p} />
              </Link>
            ))
          )}
        </div>
      </main>
    </>
  );
}
