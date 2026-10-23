import { getAlerts, getOverview } from "@/lib/api";

export const dynamic = "force-dynamic";

// 预警列表（04 §4.2 /alerts）
export default async function AlertsPage() {
  const [overview, alerts] = await Promise.all([getOverview(), getAlerts()]);
  const items = alerts?.items ?? [];

  return (
    <main className="mx-auto max-w-content px-6 pb-10 py-6">
        <h1 className="mb-3 text-[16px] font-semibold">预警分发</h1>
        <div className="space-y-3">
          {items.map((a) => (
            <article key={a.id} className="card p-4">
              <div className="mb-1 flex items-center gap-2">
                <span className="text-[13px] font-semibold">{a.title}</span>
                <span
                  className={`rounded-full px-1.5 py-0.5 text-[10px] ${
                    a.status === "sent"
                      ? "bg-[var(--ok)]/15 text-[var(--ok)]"
                      : a.status === "approved"
                        ? "bg-[var(--accent-weak)] text-[var(--accent)]"
                        : "bg-[var(--surface-2)] text-[var(--text-3)]"
                  }`}
                >
                  {a.status}
                </span>
                <span className="ml-auto text-[11px] text-[var(--text-3)]">
                  {new Intl.DateTimeFormat("zh-HK", { timeZone: "Asia/Hong_Kong", dateStyle: "short", timeStyle: "short" }).format(new Date(a.created_at))}
                </span>
              </div>
              <pre className="whitespace-pre-wrap font-sans text-[12px] leading-5 text-[var(--text-2)]">{a.body_md}</pre>
            </article>
          ))}
          {items.length === 0 && (
            <div className="card p-8 text-center text-[12px] text-[var(--text-3)]">
              暂无预警（审核通过并分发后在此可见）
            </div>
          )}
        </div>
      </main>
  );
}
