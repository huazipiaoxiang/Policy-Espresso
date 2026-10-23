"use client";

import { useState } from "react";

interface PolicyDetailClientProps {
  policyId: string;
  priority: string;
  status: string;
}

export default function PolicyDetailClient({ policyId, priority, status }: PolicyDetailClientProps) {
  const [reviewNote, setReviewNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);

  const handleSubmitReview = async () => {
    setSubmitting(true);
    try {
      const res = await fetch(`/api/review/${policyId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ note: reviewNote, action: "submit_review" }),
      });
      if (res.ok) {
        setSuccess(true);
        setReviewNote("");
        setTimeout(() => setSuccess(false), 3000);
      }
    } catch (err) {
      console.error("Review submission failed:", err);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section className="card p-4">
      <div className="mb-3 flex items-center justify-between">
        <span className="section-label">Human Review</span>
        <span className={`rounded-full px-2 py-0.5 text-[11px] ${
          status === "approved"
            ? "bg-[var(--ok)]/10 text-[var(--ok)]"
            : status === "rejected"
              ? "bg-[var(--danger)]/10 text-[var(--danger)]"
              : "bg-[var(--warn)]/10 text-[var(--warn)]"
        }`}>
          {status || "Pending First Review"}
        </span>
      </div>

      <div className="mb-3 text-[11px] text-[var(--text-3)]">
        Reviewer A / First Review
      </div>

      {success && (
        <div className="mb-3 rounded-md bg-[var(--ok)]/10 px-3 py-2 text-[12px] text-[var(--ok)]">
          ✓ 审核已提交
        </div>
      )}

      <div className="mb-3">
        <label className="mb-1 block text-[12px] text-[var(--text-3)]">审核备注</label>
        <textarea
          value={reviewNote}
          onChange={(e) => setReviewNote(e.target.value)}
          placeholder="输入证据验证备注、问题或退回原因..."
          className="w-full rounded-md border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2 text-[12px] leading-5 text-[var(--text)] placeholder:text-[var(--text-3)] focus:border-[var(--accent)] focus:outline-none"
          rows={4}
        />
      </div>

      <div className="flex gap-2">
        <button
          onClick={handleSubmitReview}
          disabled={submitting || !reviewNote.trim()}
          className="flex-1 rounded-md bg-[var(--accent)] px-3 py-2 text-[12px] font-medium text-white transition hover:bg-[var(--accent)]/90 disabled:opacity-50"
        >
          {submitting ? "提交中..." : "提交初审"}
        </button>
        <button
          disabled={submitting}
          className="rounded-md border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2 text-[12px] text-[var(--text-2)] transition hover:bg-[var(--surface)] disabled:opacity-50"
        >
          退回修改
        </button>
      </div>

      <div className="mt-4 border-t border-[var(--border)] pt-3">
        <div className="mb-2 text-[11px] text-[var(--text-3)]">Audit Trail</div>
        <div className="space-y-1 text-[11px] text-[var(--text-2)]">
          <div className="flex gap-2">
            <span className="shrink-0 text-[var(--text-3)]">Agent</span>
            <span>Scope filtering completed</span>
          </div>
          <div className="flex gap-2">
            <span className="shrink-0 text-[var(--text-3)]">System</span>
            <span>Routed to Reviewer A for first review</span>
          </div>
        </div>
      </div>
    </section>
  );
}
