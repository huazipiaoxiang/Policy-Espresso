import Link from "next/link";
import { getPolicies } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function ForYouPage() {
  const data = await getPolicies();
  const policies = data?.items ?? [];

  const recommended = policies.slice(0, 6);

  return (
    <main className="mx-auto max-w-content px-6 pb-10 pt-[72px]">
      <div className="mb-6">
        <div className="mb-1 text-[10px] uppercase tracking-wider text-[var(--text-3)]">For You</div>
        <h1 className="text-[20px] font-semibold">为你推荐</h1>
        <p className="mt-1 text-[13px] text-[var(--text-2)]">
          基于你的业务线和订阅偏好，以下是可能相关的政策更新
        </p>
      </div>

      <div className="mb-6 grid grid-cols-3 gap-4">
        <div className="card p-4">
          <div className="mb-2 text-[11px] text-[var(--text-3)]">今日新增</div>
          <div className="font-mono text-[28px] font-semibold">{policies.length}</div>
          <div className="mt-1 text-[11px] text-[var(--ok)]">+2 较昨日</div>
        </div>
        <div className="card p-4">
          <div className="mb-2 text-[11px] text-[var(--text-3)]">与你相关</div>
          <div className="font-mono text-[28px] font-semibold">{recommended.length}</div>
          <div className="mt-1 text-[11px] text-[var(--text-2)]">基于业务线匹配</div>
        </div>
        <div className="card p-4">
          <div className="mb-2 text-[11px] text-[var(--text-3)]">高优先级</div>
          <div className="font-mono text-[28px] font-semibold text-[var(--danger)]">
            {policies.filter((p) => p.priority === "P0" || p.priority === "P1").length}
          </div>
          <div className="mt-1 text-[11px] text-[var(--text-2)]">需关注</div>
        </div>
      </div>

      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-[16px] font-semibold">推荐政策</h2>
        <Link href="/policies" className="text-[12px] text-[var(--accent)] hover:underline">
          查看全部 →
        </Link>
      </div>

      <div className="space-y-3">
        {recommended.map((policy) => (
          <Link
            key={policy.id}
            href={`/policies/${policy.id}`}
            className="block rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4 transition hover:border-[var(--accent)] hover:shadow-sm"
          >
            <div className="mb-2 flex items-start justify-between gap-3">
              <div className="flex-1">
                <div className="mb-1 flex items-center gap-2">
                  <span className={`rounded-full px-2 py-0.5 text-[10px] ${
                    policy.priority === "P0" || policy.priority === "P1"
                      ? "bg-[var(--danger)]/10 text-[var(--danger)]"
                      : policy.priority === "P2"
                        ? "bg-[var(--warn)]/10 text-[var(--warn)]"
                        : "bg-[var(--ok)]/10 text-[var(--ok)]"
                  }`}>
                    {policy.priority}
                  </span>
                  <span className="text-[11px] text-[var(--text-3)]">{policy.issuing_body}</span>
                </div>
                <h3 className="text-[14px] font-medium leading-5">{policy.title}</h3>
              </div>
              <div className="shrink-0 text-right">
                <div className="font-mono text-[20px] font-semibold">{policy.score_total.toFixed(1)}</div>
                <div className="text-[10px] text-[var(--text-3)]">影响评分</div>
              </div>
            </div>
            <p className="mb-2 line-clamp-2 text-[12px] leading-5 text-[var(--text-2)]">
              {policy.summary_zh || "暂无摘要"}
            </p>
            <div className="flex items-center gap-2">
              {policy.themes.slice(0, 3).map((theme) => (
                <span key={theme} className="rounded-full bg-[var(--surface-2)] px-2 py-0.5 text-[10px] text-[var(--text-2)]">
                  #{theme}
                </span>
              ))}
              {policy.themes.length > 3 && (
                <span className="text-[10px] text-[var(--text-3)]">+{policy.themes.length - 3}</span>
              )}
            </div>
          </Link>
        ))}
      </div>

      {recommended.length === 0 && (
        <div className="card p-12 text-center">
          <div className="mb-2 text-[14px] text-[var(--text-2)]">暂无推荐</div>
          <div className="text-[12px] text-[var(--text-3)]">
            请先订阅感兴趣的主题或业务线，系统将为你推荐相关政策
          </div>
          <Link
            href="/subscriptions"
            className="mt-4 inline-block rounded-md bg-[var(--accent)] px-4 py-2 text-[12px] text-white hover:bg-[var(--accent)]/90"
          >
            前往订阅
          </Link>
        </div>
      )}
    </main>
  );
}
