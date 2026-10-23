import { getOverview, getSettings } from "@/lib/api";

export const dynamic = "force-dynamic";

// 系统概览（管理员首页）
export default async function HealthPage() {
  const [overview, settings] = await Promise.all([getOverview(), getSettings()]);

  return (
    <main className="mx-auto max-w-content px-6 pb-10 py-6">
      <div className="mb-3 flex items-center gap-2">
        <h1 className="text-[16px] font-semibold">系统概览</h1>
        <span className="text-[12px] text-[var(--text-3)]">
          运行状态与关键指标
        </span>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* 关键指标 */}
        <div className="card p-4">
          <div className="section-label mb-3">关键指标</div>
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-[12px] text-[var(--text-2)]">今日新增政策</span>
              <span className="font-mono text-[14px] font-semibold text-[var(--text)]">
                {overview?.today_new ?? 0}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-[12px] text-[var(--text-2)]">待审核</span>
              <span className="font-mono text-[14px] font-semibold text-[var(--warn)]">
                {overview?.pending_review ?? 0}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-[12px] text-[var(--text-2)]">P0/P1 未完成</span>
              <span className="font-mono text-[14px] font-semibold text-[var(--danger)]">
                {overview?.p0_p1_open ?? 0}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-[12px] text-[var(--text-2)]">平均响应时间</span>
              <span className="font-mono text-[14px] text-[var(--text)]">
                {overview?.avg_response_min ? `${overview.avg_response_min} min` : "—"}
              </span>
            </div>
          </div>
        </div>

        {/* 数据源健康 */}
        <div className="card p-4">
          <div className="section-label mb-3">数据源状态</div>
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-[12px] text-[var(--text-2)]">总数据源</span>
              <span className="font-mono text-[14px] font-semibold text-[var(--text)]">
                {overview?.sources_total ?? 0}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-[12px] text-[var(--text-2)]">异常数据源</span>
              <span
                className="font-mono text-[14px] font-semibold"
                style={{ color: (overview?.sources_unhealthy ?? 0) > 0 ? "var(--danger)" : "var(--ok)" }}
              >
                {overview?.sources_unhealthy ?? 0}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-[12px] text-[var(--text-2)]">最近抓取</span>
              <span className="font-mono text-[12px] text-[var(--text-3)]">
                {overview?.last_crawl_at
                  ? new Intl.DateTimeFormat("zh-HK", { timeZone: "Asia/Hong_Kong", dateStyle: "short", timeStyle: "short" }).format(new Date(overview.last_crawl_at))
                  : "—"}
              </span>
            </div>
          </div>
        </div>

        {/* 运行时状态 */}
        {settings && (
          <div className="card p-4">
            <div className="section-label mb-3">运行时</div>
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-[12px] text-[var(--text-2)]">数据库</span>
                <span
                  className="text-[12px] font-medium"
                  style={{ color: settings.runtime.db === "ok" ? "var(--ok)" : "var(--danger)" }}
                >
                  {settings.runtime.db === "ok" ? "正常" : "异常"}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[12px] text-[var(--text-2)]">LLM Provider</span>
                <span className="font-mono text-[12px] text-[var(--text)]">{settings.runtime.llm_provider}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[12px] text-[var(--text-2)]">存储后端</span>
                <span className="font-mono text-[12px] text-[var(--text)]">{settings.runtime.storage_backend}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[12px] text-[var(--text-2)]">版本</span>
                <span className="font-mono text-[12px] text-[var(--text)]">{settings.runtime.version}</span>
              </div>
            </div>
          </div>
        )}

        {/* 快速链接 */}
        <div className="card p-4">
          <div className="section-label mb-3">快速链接</div>
          <div className="grid grid-cols-2 gap-2">
            <a href="/sources" className="rounded-md border border-[var(--border)] p-3 text-[12px] hover:border-[var(--accent)] hover:text-[var(--accent)] transition-colors">
              <div className="font-semibold">数据源管理</div>
              <div className="text-[11px] text-[var(--text-3)] mt-1">监控抓取状态</div>
            </a>
            <a href="/rules" className="rounded-md border border-[var(--border)] p-3 text-[12px] hover:border-[var(--accent)] hover:text-[var(--accent)] transition-colors">
              <div className="font-semibold">Agent 与规则</div>
              <div className="text-[11px] text-[var(--text-3)] mt-1">配置分析管线</div>
            </a>
            <a href="/audit" className="rounded-md border border-[var(--border)] p-3 text-[12px] hover:border-[var(--accent)] hover:text-[var(--accent)] transition-colors">
              <div className="font-semibold">审计日志</div>
              <div className="text-[11px] text-[var(--text-3)] mt-1">查看操作记录</div>
            </a>
            <a href="/settings" className="rounded-md border border-[var(--border)] p-3 text-[12px] hover:border-[var(--accent)] hover:text-[var(--accent)] transition-colors">
              <div className="font-semibold">系统设置</div>
              <div className="text-[11px] text-[var(--text-3)] mt-1">配置与参数</div>
            </a>
          </div>
        </div>
      </div>
    </main>
  );
}
