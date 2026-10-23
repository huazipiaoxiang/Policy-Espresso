"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import EmptyState from "@/components/EmptyState";
import Pagination from "@/components/Pagination";
import PolicyRow from "@/components/PolicyRow";
import type { PolicyItem } from "@/lib/api";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8001/api/v1";
const API_KEY = process.env.HORIZON_API_KEY ?? "dev-local-key";
const PAGE_SIZE = 20;

interface PolicyTableProps {
  initialStatus?: string;
  initialPriority?: string;
  initialScope?: string;
}

export default function PolicyTable({ initialStatus, initialPriority, initialScope }: PolicyTableProps) {
  const [page, setPage] = useState(1);
  const [items, setItems] = useState<PolicyItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [restoring, setRestoring] = useState<string | null>(null);

  const isLowRelevance = initialScope === "low";

  const fetchPolicies = useCallback(async (p: number) => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ page: String(p), page_size: String(PAGE_SIZE) });
      if (initialStatus) params.set("status", initialStatus);
      if (initialPriority) params.set("priority", initialPriority);
      if (initialScope) params.set("scope", initialScope);
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
  }, [initialStatus, initialPriority, initialScope]);

  useEffect(() => {
    fetchPolicies(page);
  }, [page, fetchPolicies]);

  const handleRestore = async (policyId: string) => {
    setRestoring(policyId);
    try {
      const res = await fetch(`${API_BASE}/policies/${policyId}/restore`, {
        method: "POST",
        headers: { "X-API-Key": API_KEY },
      });
      if (res.ok) {
        setItems(items.filter((p) => p.id !== policyId));
        setTotal(total - 1);
      }
    } finally {
      setRestoring(null);
    }
  };

  return (
    <div className="card overflow-hidden flex flex-col">
      <div className="flex h-11 items-center justify-between border-b border-[var(--border)] px-4">
        <span className="text-[13px] font-semibold">
          {isLowRelevance ? "低相关政策" : "政策列表"}
        </span>
        <div className="flex items-center gap-3">
          <span className="text-[11px] text-[var(--text-3)]">共 {total} 条</span>
          {isLowRelevance && (
            <span className="text-[11px] text-[var(--text-3)]">
              低相关政策可在此重新送入分析
            </span>
          )}
        </div>
      </div>
      <div className="flex-1">
        {loading ? (
          <div className="flex h-32 items-center justify-center text-[12px] text-[var(--text-3)]">加载中…</div>
        ) : items.length === 0 ? (
          <div className="p-6">
            <EmptyState
              title={isLowRelevance ? "暂无低相关政策" : "暂无政策卡片"}
              hint={
                isLowRelevance
                  ? "所有政策均非低相关，或已重新送入分析"
                  : "抓取与分析管线产出政策卡后在此展示（Phase 1/2 已实现，当前库为空）"
              }
              action={!isLowRelevance ? "make seed && make crawl && python -m app.jobs.analyze_job" : undefined}
            />
          </div>
        ) : isLowRelevance ? (
          items.map((p) => (
            <div
              key={p.id}
              className="flex h-12 items-center gap-3 border-b border-[var(--border)] px-3 hover:bg-[var(--surface-2)]"
            >
              <div className="min-w-0 flex-1">
                <PolicyRow policy={p} />
              </div>
              <button
                onClick={() => handleRestore(p.id)}
                disabled={restoring === p.id}
                className="shrink-0 rounded border border-[var(--accent)] px-2 py-0.5 text-[11px] text-[var(--accent)] transition hover:bg-[var(--accent)] hover:text-white disabled:opacity-50"
              >
                {restoring === p.id ? "送入分析中..." : "送入分析"}
              </button>
            </div>
          ))
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
