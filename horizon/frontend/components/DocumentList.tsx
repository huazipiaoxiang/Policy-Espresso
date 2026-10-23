"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import EmptyState from "@/components/EmptyState";
import Pagination from "@/components/Pagination";
import type { DocumentItem } from "@/lib/api";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000/api/v1";
const API_KEY = process.env.HORIZON_API_KEY ?? "dev-local-key";
const PAGE_SIZE = 20;

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

export default function DocumentList() {
  const [page, setPage] = useState(1);
  const [items, setItems] = useState<DocumentItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);

  const fetchDocuments = useCallback(async (p: number) => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/documents?page=${p}&page_size=${PAGE_SIZE}`, {
        headers: { "X-API-Key": API_KEY },
      });
      if (res.ok) {
        const data = await res.json();
        setItems(data.items ?? []);
        setTotal(data.total ?? 0);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDocuments(page);
  }, [page, fetchDocuments]);

  return (
    <div className="card flex flex-col">
      <div className="flex h-10 items-center justify-between border-b border-[var(--border)] px-3">
        <span className="section-label">文档流 · 抓取入库</span>
        <span className="text-[11px] text-[var(--text-3)]">共 {total} 条</span>
      </div>
      <div className="flex-1">
        {loading ? (
          <div className="flex h-32 items-center justify-center text-[12px] text-[var(--text-3)]">加载中…</div>
        ) : items.length === 0 ? (
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
      </div>
      <Pagination page={page} pageSize={PAGE_SIZE} total={total} onChange={setPage} />
    </div>
  );
}
