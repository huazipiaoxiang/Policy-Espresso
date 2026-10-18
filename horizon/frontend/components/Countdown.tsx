"use client";

import { useEffect, useState } from "react";

// Countdown（08 §4）：SLA 倒计时，超时变红（闪一次，不循环）
export default function Countdown({ dueAt }: { dueAt: string | null }) {
  const [text, setText] = useState("—");
  const [overdue, setOverdue] = useState(false);

  useEffect(() => {
    if (!dueAt) return;
    const tick = () => {
      const diff = new Date(dueAt).getTime() - Date.now();
      setOverdue(diff < 0);
      const abs = Math.abs(diff);
      const h = Math.floor(abs / 3600000);
      const m = Math.floor((abs % 3600000) / 60000);
      setText(diff < 0 ? `超时 ${h}h${m}m` : `剩余 ${h}h${m}m`);
    };
    tick();
    const timer = setInterval(tick, 30000);
    return () => clearInterval(timer);
  }, [dueAt]);

  if (!dueAt) return <span className="text-[var(--text-3)]">无 SLA</span>;
  return (
    <span className={`font-mono text-[12px] ${overdue ? "animate-pulse text-[var(--danger)]" : "text-[var(--text-2)]"}`}>
      {text}
    </span>
  );
}
