"use client";

import { useCallback, useEffect, useState } from "react";
import EmptyState from "@/components/EmptyState";
import Pagination from "@/components/Pagination";
import PolicyRow from "@/components/PolicyRow";
import type { PolicyItem } from "@/lib/api";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000/api/v1";
const API_KEY = process.env.HORIZON_API_KEY ?? "dev-local-key";
const PAGE_SIZE = 20;

export default function ExclusionsPage() {
  const [page, setPage] = useState(1);
  const [items, setItems] = useState<PolicyItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [restoring, setRestoring] = useState<string | null>(null);

  const fetchExclusions = useCallback(async (p: number) => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/policies?page=${p}&page_size=${PAGE_SIZE}&scope=excluded`, {
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
    fetchExclusions(page);
  }, [page, fetchExclusions]);

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
    <main className="mx-auto max-w-content px-6 pb-10 py-6">
        <div className="mb-3 flex items-center gap-2">
          <h1 className="text-[16px] font-semibold">排除记录库</h1>
          <span className="text-[12px] text-[var(--text-3)]">共 {total} 条</span>
          <span className="ml-auto text-[12px] text-[var(--text-3)]">
            被排除的政策可在此恢复审核
          </span>
        </div>

        <div className="card flex flex-col">
          <div className="flex h-10 items-center justify-between border-b border-[var(--border)] px-3">
            <span className="section-label">排除记录（按时间）</span>
          </div>
          <div className="flex-1">
            {loading ? (
              <div className="flex h-32 items-center justify-center text-[12px] text-[var(--text-3)]">加载中…</div>
            ) : items.length === 0 ? (
              <div className="p-6">
                <EmptyState
                  title="暂无排除记录"
                  hint="所有政策均未被排除，或已恢复审核"
                />
              </div>
            ) : (
              items.map((p) => (
                <div
                  key={p.id}
                  className="relative flex h-12 items-center gap-3 border-b border-[var(--border)] px-3 hover:bg-[var(--surface-2)]"
                >
                  <div className="min-w-0 flex-1">
                    <PolicyRow policy={p} />
                  </div>
                  <button
                    onClick={() => handleRestore(p.id)}
                    disabled={restoring === p.id}
                    className="shrink-0 rounded border border-[var(--accent)] px-2 py-0.5 text-[11px] text-[var(--accent)] transition hover:bg-[var(--accent)] hover:text-white disabled:opacity-50"
                  >
                    {restoring === p.id ? "恢复中..." : "恢复审核"}
                  </button>
                </div>
              ))
            )}
          </div>
          <Pagination page={page} pageSize={PAGE_SIZE} total={total} onChange={setPage} />
        </div>
      </main>
  );
}
