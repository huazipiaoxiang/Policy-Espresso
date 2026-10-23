import { getAudit, getOverview } from "@/lib/api";

export const dynamic = "force-dynamic";

const ACTION_LABEL: Record<string, string> = {
  ai_analyze: "AI 分析",
  submit_review: "提交审核",
  claim_task: "领取任务",
  review_approve: "审核通过",
  review_reject: "审核驳回",
  review_request_info: "退回补充",
  dispatch: "分发",
  skip_review: "跳过审核（不满足预警条件）",
};

function fmtTime(iso: string) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat("zh-HK", { timeZone: "Asia/Hong_Kong", dateStyle: "short", timeStyle: "medium" }).format(d);
}

// 审计查询（04 §4.2 /admin/audit；只追加、可导出）
export default async function AuditPage() {
  const [overview, audit] = await Promise.all([getOverview(), getAudit()]);
  const items = audit?.items ?? [];

  return (
    <main className="mx-auto max-w-content px-6 pb-10 py-6">
        <div className="mb-3 flex items-center gap-2">
          <h1 className="text-[16px] font-semibold">审计日志</h1>
          <span className="text-[12px] text-[var(--text-3)]">共 {audit?.total ?? 0} 条（只追加，保留 ≥7 年）</span>
          <a
            href="/api/proxy/admin/audit/export"
            className="ml-auto rounded-btn border border-[var(--border)] bg-[var(--surface-2)] px-2.5 py-1 text-[12px] text-[var(--accent)] hover:underline"
          >
            导出 CSV
          </a>
        </div>
        <div className="card overflow-hidden">
          <table className="w-full text-[12px]">
            <thead>
              <tr className="border-b border-[var(--border)] text-left text-[var(--text-3)]">
                <th className="px-3 py-2 font-medium">时间</th>
                <th className="px-3 py-2 font-medium">操作人</th>
                <th className="px-3 py-2 font-medium">动作</th>
                <th className="px-3 py-2 font-medium">对象</th>
                <th className="px-3 py-2 font-medium">变更</th>
              </tr>
            </thead>
            <tbody>
              {items.map((a) => (
                <tr key={a.id} className="border-b border-[var(--border)] last:border-0">
                  <td className="whitespace-nowrap px-3 py-1.5 text-[var(--text-3)]">{fmtTime(a.at)}</td>
                  <td className="px-3 py-1.5">{a.actor}</td>
                  <td className="px-3 py-1.5">{ACTION_LABEL[a.action] ?? a.action}</td>
                  <td className="px-3 py-1.5 font-mono text-[11px] text-[var(--text-3)]">
                    {a.object_type}:{a.object_id.slice(0, 12)}…
                  </td>
                  <td className="px-3 py-1.5 text-[var(--text-2)]">
                    {JSON.stringify(a.before) !== "{}" && (
                      <span className="text-[var(--text-3)]">{JSON.stringify(a.before)} → </span>
                    )}
                    {JSON.stringify(a.after)}
                    {a.reason && <span className="ml-1 text-[var(--text-3)]">（{a.reason}）</span>}
                  </td>
                </tr>
              ))}
              {items.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-3 py-8 text-center text-[var(--text-3)]">
                    暂无审计记录（审核与分发动作将在此留痕）
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </main>
  );
}
