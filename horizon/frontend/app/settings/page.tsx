import Topbar from "@/components/Topbar";
import { getSettings, getOverview, type SystemSettings } from "@/lib/api";

export const dynamic = "force-dynamic";

// 设置页（只读系统状态与配置快照）。进程级配置由 .env 注入、运行期不可热改。
function KV({ k, v, mono = false }: { k: string; v: React.ReactNode; mono?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-4 py-2">
      <span className="text-[12px] text-[var(--text-2)]">{k}</span>
      <span className={mono ? "font-mono text-[12px] text-[var(--text)]" : "text-[12px] text-[var(--text)]"}>{v}</span>
    </div>
  );
}

function StatusPill({ ok }: { ok: boolean }) {
  return (
    <span
      className="inline-flex items-center gap-1.5 text-[12px]"
      style={{ color: ok ? "var(--ok)" : "var(--danger)" }}
    >
      <span className="h-2 w-2 rounded-full" style={{ background: ok ? "var(--ok)" : "var(--danger)" }} />
      {ok ? "已配置" : "未配置"}
    </span>
  );
}

function Card({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="card p-4">
      <div className="section-label mb-1">{label}</div>
      <div className="divide-y divide-[var(--border)]">{children}</div>
    </div>
  );
}

export default async function SettingsPage() {
  const settings = await getSettings();
  const overview = await getOverview();

  if (!settings) {
    return (
      <>
        <Topbar />
        <main className="mx-auto max-w-content px-6 pb-10 pt-[72px]">
          <h1 className="text-[16px] font-semibold">设置</h1>
          <div className="card mt-3 p-8 text-center text-[12px] text-[var(--text-3)]">
            无法加载系统设置（后端未就绪或鉴权失败）。请确认 API 已启动并配置 HORIZON_API_KEY。
          </div>
        </main>
      </>
    );
  }

  const dbOk = settings.runtime.db === "ok";

  return (
    <>
      <Topbar
        sourcesTotal={overview?.sources_total ?? 0}
        sourcesUnhealthy={overview?.sources_unhealthy ?? 0}
        pendingReview={overview?.pending_review ?? 0}
      />
      <main className="mx-auto max-w-content px-6 pb-10 pt-[72px]">
        <div className="mb-3 flex items-center gap-2">
          <h1 className="text-[16px] font-semibold">设置</h1>
          <span className="text-[12px] text-[var(--text-3)]">
            只读系统状态与配置快照 · 运行期配置由环境变量注入，需改 .env 后重启生效
          </span>
        </div>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          <Card label="运行时状态">
            <KV k="数据库" v={<span style={{ color: dbOk ? "var(--ok)" : "var(--danger)" }}>{dbOk ? "正常" : "异常"}</span>} />
            <KV k="LLM Provider" v={settings.runtime.llm_provider} mono />
            <KV k="存储后端" v={settings.runtime.storage_backend} mono />
            <KV k="调度器" v={settings.runtime.scheduler} mono />
            <KV k="时区" v={settings.runtime.timezone} mono />
            <KV k="版本" v={settings.runtime.version} mono />
          </Card>

          <Card label="模型分层路由">
            <KV k="Provider" v={settings.llm.provider} mono />
            <KV k="分类 / 打标" v={settings.llm.model_tier.classify} mono />
            <KV k="结构化抽取" v={settings.llm.model_tier.extract} mono />
            <KV k="影响分析" v={settings.llm.model_tier.impact} mono />
            <KV k="Studio 建议书" v={settings.llm.model_tier.studio} mono />
            <KV k="百炼 Key" v={<StatusPill ok={settings.llm.dashscope_configured} />} />
            <KV k="Ollama 端点" v={settings.llm.ollama_base_url} mono />
          </Card>

          <Card label="存储">
            <KV k="后端" v={settings.storage.backend} mono />
            <KV k="本地存储目录" v={<StatusPill ok={settings.storage.storage_dir_configured} />} />
            <KV k="OSS" v={<StatusPill ok={settings.storage.oss_configured} />} />
            <KV k="Bucket" v={settings.storage.oss_bucket || "—"} mono />
          </Card>

          <Card label="抓取合规">
            <KV k="User-Agent" v={settings.crawl.user_agent} mono />
            <KV k="每域限速" v={`${settings.crawl.max_rps_per_domain} req/s`} mono />
            <KV k="遵守 robots.txt" v={settings.crawl.respect_robots ? "是" : "否"} />
            <KV k="每文档附件上限" v={settings.crawl.max_attachments_per_doc} mono />
            <KV k="单源单轮条数上限" v={settings.crawl.max_items_per_source === 0 ? "不限制" : settings.crawl.max_items_per_source} mono />
          </Card>

          <Card label="通知通道">
            <KV k="站内通知" v={<StatusPill ok />} />
            <KV k="邮件 Webhook" v={<StatusPill ok={!!settings.notify.email} />} />
            <KV k="企微 Webhook" v={<StatusPill ok={!!settings.notify.wecom} />} />
            <KV k="飞书 Webhook" v={<StatusPill ok={!!settings.notify.feishu} />} />
          </Card>

          <Card label="安全">
            <KV k="鉴权方式" v={settings.security.auth === "api_key" ? "X-API-Key（单用户）" : "无鉴权"} />
            <KV k="FC 定时触发令牌" v={<StatusPill ok={settings.security.job_trigger_token_configured} />} />
          </Card>
        </div>
      </main>
    </>
  );
}
