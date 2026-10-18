import Link from "next/link";
import { notFound } from "next/navigation";

import Topbar from "@/components/Topbar";
import { getDocument, getVersionDiff } from "@/lib/api";
import type { DiffItem } from "@/lib/api";

// 文档详情（Phase 1）：正文 + 附件解析状态 + 版本 diff（06 §5.4）
const ATT_STATUS: Record<string, string> = {
  parsed: "已解析",
  scanned: "扫描件 · 需人工阅读",
  failed: "解析失败",
  unsupported: "暂不支持（待 MinerU/Docling）",
  skipped: "超出每文档附件上限",
};

function fmtTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("zh-HK", { timeZone: "Asia/Hong_Kong", hour12: false });
}

function DiffBlock({ item }: { item: DiffItem }) {
  return (
    <div className="space-y-1">
      {(item.op === "delete" || item.op === "replace") && item.before && (
        <pre className="whitespace-pre-wrap rounded border border-red-900/40 bg-red-950/30 px-3 py-2 text-[12px] text-red-300">
          − {item.before}
        </pre>
      )}
      {(item.op === "insert" || item.op === "replace") && item.after && (
        <pre className="whitespace-pre-wrap rounded border border-emerald-900/40 bg-emerald-950/30 px-3 py-2 text-[12px] text-emerald-300">
          + {item.after}
        </pre>
      )}
    </div>
  );
}

export default async function DocumentDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const doc = await getDocument(id);
  if (!doc) notFound();

  // 版本通常极少，服务端一次性取回所有 diff（MVP 不做懒加载）
  const diffs = await Promise.all(doc.versions.map((v) => getVersionDiff(doc.id, v.version_no)));

  return (
    <>
      <Topbar />
      <main className="mx-auto max-w-content px-6 pb-10 pt-[72px]">
        <div className="mb-3 text-[12px] text-[var(--text-3)]">
          <Link href="/documents" className="hover:text-[var(--text)]">
            ← 文档流
          </Link>
        </div>

        <section className="card p-4">
          <h1 className="text-[16px] font-semibold text-[var(--text)]">{doc.title}</h1>
          <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[12px] text-[var(--text-3)]">
            <span>发布 {fmtTime(doc.published_at)}</span>
            <span>抓取 {fmtTime(doc.fetched_at)}</span>
            <span>{doc.lang}</span>
            <span>状态 {doc.status}</span>
            <a href={doc.url} target="_blank" rel="noreferrer" className="text-[var(--accent)] hover:underline">
              原文链接 ↗
            </a>
          </div>
        </section>

        {doc.attachments?.length > 0 && (
          <section className="card mt-4">
            <div className="flex h-10 items-center border-b border-[var(--border)] px-3">
              <span className="section-label">附件 · {doc.attachments.length}</span>
            </div>
            {doc.attachments.map((a, i) => (
              <div key={i} className="flex items-center gap-3 border-b border-[var(--border)] px-3 py-2 last:border-0">
                <a href={a.url} target="_blank" rel="noreferrer" className="truncate text-[12px] text-[var(--accent)] hover:underline">
                  {a.name}
                </a>
                <span className="ml-auto text-[11px] text-[var(--text-3)]">
                  {ATT_STATUS[a.status ?? ""] ?? a.status ?? "未解析"}
                  {a.status === "parsed" && a.char_count ? ` · ${a.char_count} 字` : ""}
                </span>
              </div>
            ))}
          </section>
        )}

        {diffs.length > 0 && (
          <section className="card mt-4">
            <div className="flex h-10 items-center border-b border-[var(--border)] px-3">
              <span className="section-label">版本变更 · {diffs.length}</span>
            </div>
            {diffs.map(
              (d) =>
                d && (
                  <div key={d.version_no} className="border-b border-[var(--border)] px-3 py-3 last:border-0">
                    <div className="mb-2 flex gap-3 text-[11px] text-[var(--text-3)]">
                      <span className="text-[var(--text-2)]">v{d.version_no}</span>
                      <span>{fmtTime(d.changed_at)}</span>
                      <span>变更比例 {(d.changed_ratio * 100).toFixed(1)}%</span>
                      <span className={d.minor_edit ? "" : "text-[var(--danger)]"}>
                        {d.minor_edit ? "minor_edit" : "实质修订"}
                      </span>
                    </div>
                    <div className="space-y-2">
                      {d.diff.map((item, i) => (
                        <DiffBlock key={i} item={item} />
                      ))}
                    </div>
                  </div>
                ),
            )}
          </section>
        )}

        <section className="card mt-4">
          <div className="flex h-10 items-center border-b border-[var(--border)] px-3">
            <span className="section-label">正文</span>
          </div>
          <pre className="max-h-[560px] overflow-y-auto whitespace-pre-wrap px-4 py-3 text-[13px] leading-6 text-[var(--text-2)]">
            {doc.content_text || "（正文为空）"}
          </pre>
        </section>
      </main>
    </>
  );
}
