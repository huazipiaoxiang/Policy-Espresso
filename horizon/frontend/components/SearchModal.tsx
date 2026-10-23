"use client";

import { useState, useEffect, useRef } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8001/api/v1";
const API_KEY = process.env.HORIZON_API_KEY ?? "dev-local-key";

type SearchResult = {
  id: number;
  title: string;
  issuing_body?: string;
  published_at?: string;
  priority?: string;
  type: "policy" | "case";
};

export default function SearchModal({ onClose }: { onClose: () => void }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const modalRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      } else if (e.key === "ArrowDown") {
        e.preventDefault();
        setSelectedIndex((prev) => Math.min(prev + 1, results.length - 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setSelectedIndex((prev) => Math.max(prev - 1, 0));
      } else if (e.key === "Enter" && results[selectedIndex]) {
        e.preventDefault();
        const item = results[selectedIndex];
        const path = item.type === "policy" ? `/policies/${item.id}` : `/cases/${item.id}`;
        window.location.href = path;
        onClose();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [results, selectedIndex, onClose]);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (modalRef.current && !modalRef.current.contains(e.target as Node)) {
        onClose();
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [onClose]);

  useEffect(() => {
    if (!query.trim()) {
      setResults([]);
      return;
    }

    const controller = new AbortController();
    const timeoutId = setTimeout(async () => {
      setLoading(true);
      try {
        const [policiesRes, casesRes] = await Promise.all([
          fetch(`${API_BASE}/policies?q=${encodeURIComponent(query)}&limit=5`, {
            signal: controller.signal,
            headers: { "X-API-Key": API_KEY },
          }),
          fetch(`${API_BASE}/cases?q=${encodeURIComponent(query)}&limit=5`, {
            signal: controller.signal,
            headers: { "X-API-Key": API_KEY },
          }),
        ]);

        const policiesData = policiesRes.ok ? await policiesRes.json() : { items: [] };
        const casesData = casesRes.ok ? await casesRes.json() : { items: [] };

        const policies = policiesData.items || [];
        const cases = casesData.items || [];

        const combined: SearchResult[] = [
          ...policies.map((p: any) => ({ ...p, type: "policy" as const })),
          ...cases.map((c: any) => ({ ...c, type: "case" as const })),
        ];

        setResults(combined);
        setSelectedIndex(0);
      } catch (err: any) {
        if (err.name !== "AbortError") {
          console.error("Search failed:", err);
        }
      } finally {
        setLoading(false);
      }
    }, 300);

    return () => {
      clearTimeout(timeoutId);
      controller.abort();
    };
  }, [query]);

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/50 pt-[15vh]">
      <div
        ref={modalRef}
        className="w-[600px] rounded-lg border border-[var(--border)] bg-[var(--surface)] shadow-xl"
      >
        <div className="flex items-center border-b border-[var(--border)] px-4">
          <span className="text-[14px] text-[var(--text-3)]">🔍</span>
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="搜索政策标题、发文机构、案例…"
            className="flex-1 bg-transparent px-3 py-3 text-[14px] text-[var(--text)] placeholder:text-[var(--text-3)] focus:outline-none"
          />
          {loading && <span className="text-[12px] text-[var(--text-3)]">搜索中…</span>}
        </div>

        <div className="max-h-[400px] overflow-y-auto">
          {results.length === 0 && query.trim() && !loading ? (
            <div className="px-4 py-8 text-center text-[13px] text-[var(--text-3)]">
              未找到匹配结果
            </div>
          ) : (
            results.map((item, idx) => (
              <a
                key={`${item.type}-${item.id}`}
                href={item.type === "policy" ? `/policies/${item.id}` : `/cases/${item.id}`}
                onClick={onClose}
                className={`flex items-center gap-3 border-b border-[var(--border)] px-4 py-3 last:border-b-0 hover:bg-[var(--surface-2)] ${
                  idx === selectedIndex ? "bg-[var(--surface-2)]" : ""
                }`}
              >
                <span className="rounded bg-[var(--surface-3)] px-1.5 py-0.5 text-[10px] font-medium text-[var(--text-2)]">
                  {item.type === "policy" ? "政策" : "案例"}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-[13px] font-medium text-[var(--text)]">
                    {item.title}
                  </div>
                  <div className="mt-0.5 flex items-center gap-2 text-[11px] text-[var(--text-3)]">
                    {item.issuing_body && <span>{item.issuing_body}</span>}
                    {item.priority && (
                      <span className="rounded bg-[var(--surface-3)] px-1.5 py-0.5 font-mono text-[10px]">
                        {item.priority}
                      </span>
                    )}
                  </div>
                </div>
              </a>
            ))
          )}
        </div>

        <div className="flex items-center justify-between border-t border-[var(--border)] px-4 py-2 text-[11px] text-[var(--text-3)]">
          <div className="flex items-center gap-3">
            <span>↑↓ 选择</span>
            <span>↵ 打开</span>
            <span>esc 关闭</span>
          </div>
          <span>共 {results.length} 条结果</span>
        </div>
      </div>
    </div>
  );
}
