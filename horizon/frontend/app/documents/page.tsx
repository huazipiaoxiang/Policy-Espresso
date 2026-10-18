import Link from "next/link";

import EmptyState from "@/components/EmptyState";
import Topbar from "@/components/Topbar";
import { getDocuments } from "@/lib/api";

// 文档流（Phase 1）：抓取入库的原始政策文档，含状态与附件解析情况
const STATUS_LABEL: Record<string, { text: string; cls: string }> = {
  new: { text: "待分析", cls: "text-[var(--accent)]" },
  processing: { text: "分析中", cls: "text-[var(--accent)]" },
  processed: { text: "已分析", cls: "text-[var(--ok)]" },
  failed: { text: "失败", cls: "text-[var(--danger)]" },
  ignored: { text: "已忽略", cls: "text-[var(--text-3)]" },
};

function fmtTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("zh-HK", { timeZone: "Asia/Hong_Kong", hour12: false });
}

export default async function DocumentsPage() {
  const data = await getDocuments();
  const items = data?.items ?? [];

  return (
    <>
      <Topbar />
      <main className="mx-auto max-w-content px-6 pb-10 pt-[72px]">
        <section className="card">
          <div className="flex h-10 items-center justify-between border-b border-[var(--border)] px-3">
            <span className="section-label">文档流 · 抓取入库</span>
            <span className="text-[11px] text-[var(--text-3)]">{data?.total ?? 0} 条</span>
          </div>
          {items.length === 0 ? (
            <div className="p-6">
              <EmptyState
                title="暂无抓取文档"
                hint="Phase 1 抓取管线：6 个 Tier-1 数据源，RSS 优先"
                action="下一步：make seed && make crawl"
              />
            </div>
          ) : (
            items.map((d) => {
              const st = STATUS_LABEL[d.status] ?? { text: d.status, cls: "text-[var(--text-3)]" };
              return (
                <Link
                  key={d.id}
                  href={`/documents/${d.id}`}
                  className="flex items-center gap-3 border-b border-[var(--border)] px-3 py-2.5 last:border-0 hover:bg-[var(--surface-2)]"
                >
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-[13px] text-[var(--text)]">{d.title}</div>
                    <div className="mt-0.5 flex gap-3 text-[11px] text-[var(--text-3)]">
                      <span>{fmtTime(d.published_at)}</span>
                      <span>{d.lang}</span>
                      <span>{d.content_len} 字</span>
                      {d.attachments?.length > 0 && <span>{d.attachments.length} 个附件</span>}
                      {d.duplicate_of && <span>转载副本</span>}
                    </div>
                  </div>
                  <span className={`text-[11px] ${st.cls}`}>{st.text}</span>
                </Link>
              );
            })
          )}
        </section>
      </main>
    </>
  );
}
