import Link from "next/link";
import PolicyTable from "@/components/PolicyTable";

export const dynamic = "force-dynamic";

const FILTERS: { label: string; href: string }[] = [
  { label: "全部", href: "/policies" },
  { label: "待审", href: "/policies?status=pending_review" },
  { label: "P0/P1", href: "/policies?priority=P0" },
  { label: "低相关", href: "/policies?scope=low" },
];

// 政策库 — 基于 Policy Espresso V8.4 原型
export default async function PoliciesPage({
  searchParams,
}: {
  searchParams: { status?: string; priority?: string; scope?: string };
}) {
  return (
    <main className="mx-auto max-w-content px-6 py-6">
      <div className="mb-4 flex items-start justify-between">
        <div>
          <div className="text-[11px] font-semibold tracking-wider text-[var(--accent)] uppercase">Policy Repository</div>
          <h1 className="text-[28px] font-bold tracking-tight mt-1">政策库</h1>
          <p className="text-[13px] text-[var(--text-3)] mt-1">所有已采集政策记录，含排除、异常与未评估项</p>
        </div>
        <div className="flex gap-1.5">
          {FILTERS.map((f) => (
            <Link
              key={f.label}
              href={f.href}
              className="rounded-md border border-[var(--border)] bg-[var(--surface)] px-3 py-1.5 text-[12px] text-[var(--text-2)] hover:border-[var(--accent)] hover:text-[var(--accent)] transition-colors"
            >
              {f.label}
            </Link>
          ))}
        </div>
      </div>

      <PolicyTable
        initialStatus={searchParams.status}
        initialPriority={searchParams.priority}
        initialScope={searchParams.scope}
      />
    </main>
  );
}
