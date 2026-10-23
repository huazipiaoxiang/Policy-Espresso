"use client";

import { useCallback, useEffect, useState } from "react";
import EmptyState from "@/components/EmptyState";
import Pagination from "@/components/Pagination";
import PolicyRow from "@/components/PolicyRow";
import type { PolicyItem } from "@/lib/api";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8001/api/v1";
const API_KEY = process.env.HORIZON_API_KEY ?? "dev-local-key";
const PAGE_SIZE = 20;

export default function PolicyList() {
  const [page, setPage] = useState(1);
  const [items, setItems] = useState<PolicyItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);

  const fetchPolicies = useCallback(async (p: number) => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/policies?page=${p}&page_size=${PAGE_SIZE}`, {
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
    fetchPolicies(page);
  }, [page, fetchPolicies]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="card col-span-8 flex flex-col">
      <div className="flex h-10 items-center justify-between border-b border-[var(--border)] px-3">
        <span className="section-label">政策流 · 按优先级</span>
        <span className="text-[11px] text-[var(--text-3)]">共 {total} 条</span>
      </div>
      <div className="flex-1">
        {loading ? (
          <div className="flex h-32 items-center justify-center text-[12px] text-[var(--text-3)]">加载中…</div>
        ) : items.length === 0 ? (
          <div className="p-6">
            <EmptyState
              title="暂无新增政策"
              hint="最近一次抓取：—（Phase 1 接入 6 个数据源后此处展示政策流）"
              action="下一步：make seed && make crawl"
            />
          </div>
        ) : (
          items.map((p) => <PolicyRow key={p.id} policy={p} />)
        )}
      </div>
      <Pagination page={page} pageSize={PAGE_SIZE} total={total} onChange={setPage} />
    </div>
  );
}
