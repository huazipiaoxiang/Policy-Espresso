"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import EmptyState from "@/components/EmptyState";
import Pagination from "@/components/Pagination";
import PolicyRow from "@/components/PolicyRow";
import type { PolicyItem } from "@/lib/api";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000/api/v1";
const API_KEY = process.env.HORIZON_API_KEY ?? "dev-local-key";
const PAGE_SIZE = 20;

interface PolicyTableProps {
  initialStatus?: string;
  initialPriority?: string;
}

export default function PolicyTable({ initialStatus, initialPriority }: PolicyTableProps) {
  const [page, setPage] = useState(1);
  const [items, setItems] = useState<PolicyItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);

  const fetchPolicies = useCallback(async (p: number) => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ page: String(p), page_size: String(PAGE_SIZE) });
      if (initialStatus) params.set("status", initialStatus);
      if (initialPriority) params.set("priority", initialPriority);
      const res = await fetch(`${API_BASE}/policies?${params.toString()}`, {
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
  }, [initialStatus, initialPriority]);

  useEffect(() => {
    fetchPolicies(page);
  }, [page, fetchPolicies]);

  return (
    <div className="card overflow-hidden flex flex-col">
      <div className="flex h-10 items-center border-b border-[var(--border)] px-3">
        <span className="section-label">政策卡片（按发布时间）</span>
      </div>
      <div className="flex-1">
        {loading ? (
          <div className="flex h-32 items-center justify-center text-[12px] text-[var(--text-3)]">加载中…</div>
        ) : items.length === 0 ? (
          <div className="p-6">
            <EmptyState
              title="暂无政策卡片"
              hint="抓取与分析管线产出政策卡后在此展示（Phase 1/2 已实现，当前库为空）"
              action="make seed && make crawl && python -m app.jobs.analyze_job"
            />
          </div>
        ) : (
          items.map((p) => (
            <Link key={p.id} href={`/policies/${p.id}`} className="block">
              <PolicyRow policy={p} />
            </Link>
          ))
        )}
      </div>
      <Pagination page={page} pageSize={PAGE_SIZE} total={total} onChange={setPage} />
    </div>
  );
}
