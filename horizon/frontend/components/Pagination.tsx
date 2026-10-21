interface PaginationProps {
  page: number;
  pageSize: number;
  total: number;
  onChange: (page: number) => void;
}

export default function Pagination({ page, pageSize, total, onChange }: PaginationProps) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  if (totalPages <= 1) return null;

  return (
    <div className="flex items-center justify-between border-t border-[var(--border)] px-3 py-2 text-[12px] text-[var(--text-3)]">
      <span>
        第 {page} / {totalPages} 页 · 共 {total} 条
      </span>
      <div className="flex gap-1">
        <button
          disabled={page <= 1}
          onClick={() => onChange(page - 1)}
          className="rounded border border-[var(--border)] px-2 py-0.5 transition hover:bg-[var(--surface-2)] disabled:opacity-30"
        >
          上一页
        </button>
        <button
          disabled={page >= totalPages}
          onClick={() => onChange(page + 1)}
          className="rounded border border-[var(--border)] px-2 py-0.5 transition hover:bg-[var(--surface-2)] disabled:opacity-30"
        >
          下一页
        </button>
      </div>
    </div>
  );
}
