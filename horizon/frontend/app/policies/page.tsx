import Link from "next/link";
import PolicyTable from "@/components/PolicyTable";
import Topbar from "@/components/Topbar";
import { getOverview } from "@/lib/api";

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
  const overview = await getOverview();

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

        <PolicyTable initialStatus={searchParams.status} initialPriority={searchParams.priority} />
      </main>
    </>
  );
}
