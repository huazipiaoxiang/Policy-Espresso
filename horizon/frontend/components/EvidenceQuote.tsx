"use client";

// EvidenceQuote（08 §4）：引用块 + 定位按钮（点击回跳原文高亮）
export default function EvidenceQuote({
  quote,
  spanStart,
  spanEnd,
  field,
  id,
}: {
  quote: string;
  spanStart: number;
  spanEnd: number;
  field?: string;
  id?: string;
}) {
  const anchor = id ?? `span-${spanStart}`;
  return (
    <div
      data-evidence-id={anchor}
      className="my-1 rounded-md border border-[var(--border)] bg-[var(--surface-2)] px-2.5 py-1.5"
    >
      <div className="mb-0.5 flex items-center gap-2">
        <span className="section-label">{field || "证据"}</span>
        <span className="font-mono text-[10px] text-[var(--text-3)]">
          [{spanStart}, {spanEnd})
        </span>
      </div>
      <blockquote className="border-l-2 border-[var(--accent)] pl-2 font-serif text-[13px] text-[var(--text-2)]">
        {quote}
      </blockquote>
      <button
        className="mt-1 text-[11px] text-[var(--accent)] hover:underline"
        onClick={() => document.getElementById(anchor)?.scrollIntoView({ behavior: "smooth", block: "center" })}
      >
        定位到原文 →
      </button>
    </div>
  );
}
