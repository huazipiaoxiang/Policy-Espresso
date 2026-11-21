"use client";

// 可排序表头：点击在「升序 / 降序」间切换，再点其它列重置为升序。
// 用于管理员各列表「点击表头筛选/排序」，箭头指示当前排序状态。
interface SortableThProps {
  label: string;
  field: string;
  sortField: string | null;
  sortDir: "asc" | "desc";
  onSort: (field: string) => void;
  style?: React.CSSProperties;
}

export default function SortableTh({ label, field, sortField, sortDir, onSort, style }: SortableThProps) {
  const active = sortField === field;
  const arrow = active ? (sortDir === "asc" ? "▲" : "▼") : "⇅";
  return (
    <th style={style}>
      <button type="button" className="th-sort" onClick={() => onSort(field)} aria-label={`按${label}排序`}>
        <span>{label}</span>
        <span className={`th-sort-arrow${active ? " active" : ""}`}>{arrow}</span>
      </button>
    </th>
  );
}
