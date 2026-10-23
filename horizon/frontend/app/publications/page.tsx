import Link from "next/link";
import { getPolicies } from "@/lib/api";

export const dynamic = "force-dynamic";

function hk(dateStr: string | null): string {
  if (!dateStr) return "—";
  const d = new Date(dateStr);
  if (Number.isNaN(d.getTime())) return dateStr;
  return new Intl.DateTimeFormat("zh-HK", { timeZone: "Asia/Hong_Kong", dateStyle: "medium" }).format(d);
}

export default async function PublicationsPage() {
  const data = await getPolicies();
  const policies = data?.items ?? [];

  const published = policies.filter((p) => p.status === "approved" || p.status === "published");
  const pending = policies.filter((p) => p.status !== "approved" && p.status !== "published");

  return (
    <main className="mx-auto max-w-content px-6 pb-10 pt-[72px]">
      <div className="mb-6">
        <div className="mb-1 text-[10px] uppercase tracking-wider text-[var(--text-3)]">Publications Center</div>
        <h1 className="text-[20px] font-semibold">发布中心</h1>
        <p className="mt-1 text-[13px] text-[var(--text-2)]">
          已审核通过的政策将在此发布，供业务团队查阅和下载
        </p>
      </div>

      <div className="mb-6 grid grid-cols-3 gap-4">
        <div className="card p-4">
          <div className="mb-2 text-[11px] text-[var(--text-3)]">已发布</div>
          <div className="font-mono text-[28px] font-semibold text-[var(--ok)]">{published.length}</div>
          <div className="mt-1 text-[11px] text-[var(--text-2)]">可供查阅</div>
        </div>
        <div className="card p-4">
          <div className="mb-2 text-[11px] text-[var(--text-3)]">待发布</div>
          <div className="font-mono text-[28px] font-semibold text-[var(--warn)]">{pending.length}</div>
          <div className="mt-1 text-[11px] text-[var(--text-2)]">审核通过，等待发布</div>
        </div>
        <div className="card p-4">
          <div className="mb-2 text-[11px] text-[var(--text-3)]">本月新增</div>
          <div className="font-mono text-[28px] font-semibold">{published.length}</div>
          <div className="mt-1 text-[11px] text-[var(--text-2)]">较上月 +0</div>
        </div>
      </div>

      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-[16px] font-semibold">已发布政策</h2>
        <div className="flex gap-2">
          <button className="rounded-md border border-[var(--border)] bg-[var(--surface-2)] px-3 py-1.5 text-[12px] text-[var(--text-2)] hover:bg-[var(--surface)]">
            导出 CSV
          </button>
          <button className="rounded-md bg-[var(--accent)] px-3 py-1.5 text-[12px] text-white hover:bg-[var(--accent)]/90">
            批量发布
          </button>
        </div>
      </div>

      <div className="card overflow-hidden">
        <div className="flex h-10 items-center border-b border-[var(--border)] bg-[var(--surface-2)] px-4 text-[11px] text-[var(--text-3)]">
          <div className="w-20">优先级</div>
          <div className="flex-1">政策标题</div>
          <div className="w-32">发布时间</div>
          <div className="w-24">版本</div>
          <div className="w-20">操作</div>
        </div>
        {published.length === 0 ? (
          <div className="p-12 text-center">
            <div className="mb-2 text-[14px] text-[var(--text-2)]">暂无已发布政策</div>
            <div className="text-[12px] text-[var(--text-3)]">
              政策审核通过后将自动进入发布队列
            </div>
          </div>
        ) : (
          published.map((policy) => (
            <div
              key={policy.id}
              className="flex h-14 items-center border-b border-[var(--border)] px-4 last:border-b-0 hover:bg-[var(--surface-2)]"
            >
              <div className="w-20">
                <span className={`rounded-full px-2 py-0.5 text-[10px] ${
                  policy.priority === "P0" || policy.priority === "P1"
                    ? "bg-[var(--danger)]/10 text-[var(--danger)]"
                    : policy.priority === "P2"
                      ? "bg-[var(--warn)]/10 text-[var(--warn)]"
                      : "bg-[var(--ok)]/10 text-[var(--ok)]"
                }`}>
                  {policy.priority}
                </span>
              </div>
              <div className="flex-1 min-w-0">
                <Link href={`/policies/${policy.id}`} className="block truncate text-[13px] hover:text-[var(--accent)]">
                  {policy.title}
                </Link>
                <div className="text-[11px] text-[var(--text-3)]">{policy.issuing_body}</div>
              </div>
              <div className="w-32 text-[12px] text-[var(--text-2)]">{hk(policy.published_at)}</div>
              <div className="w-24 font-mono text-[12px] text-[var(--text-2)]">V1.0</div>
              <div className="w-20">
                <button className="text-[11px] text-[var(--accent)] hover:underline">
                  下载 PDF
                </button>
              </div>
            </div>
          ))
        )}
      </div>

      {pending.length > 0 && (
        <div className="mt-6">
          <h2 className="mb-4 text-[16px] font-semibold">待发布（{pending.length}）</h2>
          <div className="card overflow-hidden">
            {pending.slice(0, 5).map((policy) => (
              <div
                key={policy.id}
                className="flex h-14 items-center border-b border-[var(--border)] px-4 last:border-b-0 hover:bg-[var(--surface-2)]"
              >
                <div className="w-20">
                  <span className={`rounded-full px-2 py-0.5 text-[10px] ${
                    policy.priority === "P0" || policy.priority === "P1"
                      ? "bg-[var(--danger)]/10 text-[var(--danger)]"
                      : policy.priority === "P2"
                        ? "bg-[var(--warn)]/10 text-[var(--warn)]"
                        : "bg-[var(--ok)]/10 text-[var(--ok)]"
                  }`}>
                    {policy.priority}
                  </span>
                </div>
                <div className="flex-1 min-w-0">
                  <Link href={`/policies/${policy.id}`} className="block truncate text-[13px] hover:text-[var(--accent)]">
                    {policy.title}
                  </Link>
                  <div className="text-[11px] text-[var(--text-3)]">{policy.issuing_body}</div>
                </div>
                <div className="w-32 text-[12px] text-[var(--text-3)]">待发布</div>
                <div className="w-24">
                  <button className="rounded-md bg-[var(--accent)] px-2 py-1 text-[11px] text-white hover:bg-[var(--accent)]/90">
                    发布
                  </button>
                </div>
                <div className="w-20" />
              </div>
            ))}
          </div>
        </div>
      )}
    </main>
  );
}
