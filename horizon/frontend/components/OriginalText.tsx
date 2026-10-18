"use client";

import { useState } from "react";

export interface Span {
  span_start: number;
  span_end: number;
  quote: string;
  field_name?: string;
  id?: string;
}

// 原文 + 证据高亮（08 §3.2）：点击中栏字段 → 左栏滚动并高亮对应 span
export default function OriginalText({
  text,
  spans,
}: {
  text: string;
  spans: Span[];
}) {
  const [activeId, setActiveId] = useState<string | null>(null);
  const sorted = [...spans].sort((a, b) => a.span_start - b.span_start);

  const segments: { text: string; span?: Span }[] = [];
  let cursor = 0;
  for (const span of sorted) {
    if (span.span_start < cursor) continue; // 跳过重叠
    if (span.span_start > cursor) segments.push({ text: text.slice(cursor, span.span_start) });
    segments.push({ text: text.slice(span.span_start, span.span_end), span });
    cursor = span.span_end;
  }
  if (cursor < text.length) segments.push({ text: text.slice(cursor) });

  return (
    <div className="max-h-[560px] overflow-y-auto font-serif text-[15px] leading-[26px]" id="original-text">
      {segments.map((seg, i) =>
        seg.span ? (
          <mark
            key={i}
            id={seg.span.id ?? `span-${seg.span.span_start}`}
            className={`cursor-pointer rounded px-0.5 transition-colors ${
              activeId && activeId !== (seg.span.id ?? `span-${seg.span.span_start}`)
                ? "bg-[var(--accent-weak)] text-[var(--text)]"
                : "bg-yellow-500/30 text-[var(--text)]"
            }`}
            title={`支撑字段：${seg.span.field_name || "未标注"}`}
            onClick={() => {
              const id = seg.span!.id ?? `span-${seg.span!.span_start}`;
              setActiveId(id);
              document
                .querySelector(`[data-evidence-id="${id}"]`)
                ?.scrollIntoView({ behavior: "smooth", block: "center" });
            }}
          >
            {seg.text}
          </mark>
        ) : (
          <span key={i}>{seg.text}</span>
        ),
      )}
      {spans.length === 0 && <span className="text-[var(--text-3)]">（本篇暂无证据标注）</span>}
    </div>
  );
}
