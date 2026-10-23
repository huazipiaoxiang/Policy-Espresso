"use client";

import { useState, useEffect } from "react";
import SourceHealthDot from "./SourceHealthDot";
import SearchModal from "./SearchModal";

const ROLES = [
  { value: "operations", label: "政策运营" },
  { value: "consumer", label: "政策使用者" },
  { value: "admin", label: "系统管理员" },
];

export default function Topbar({
  sourcesTotal = 0,
  sourcesUnhealthy = 0,
  pendingReview = 0,
  role = "operations",
  onRoleChange,
}: {
  sourcesTotal?: number;
  sourcesUnhealthy?: number;
  pendingReview?: number;
  role?: string;
  onRoleChange?: (role: string) => void;
}) {
  const [showRoleMenu, setShowRoleMenu] = useState(false);
  const [showSearch, setShowSearch] = useState(false);
  const healthState =
    sourcesTotal === 0 ? "unknown" : sourcesUnhealthy === 0 ? "ok" : sourcesUnhealthy >= 3 ? "bad" : "warn";

  const currentRole = ROLES.find((r) => r.value === role) ?? ROLES[0];

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setShowSearch((prev) => !prev);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  return (
    <>
      <header className="fixed left-[232px] right-0 top-0 z-10 flex h-14 items-center gap-4 border-b border-[var(--border)] bg-[var(--surface)] px-6">
        <span className="text-[13px] text-[var(--text-2)]">Policy Espresso</span>

        <div className="ml-auto flex items-center gap-3">
          <button
            onClick={() => setShowSearch(true)}
            className="flex h-8 w-56 items-center rounded-md border border-[var(--border)] bg-[var(--surface-2)] px-3 text-[12px] text-[var(--text-3)] hover:border-[var(--accent)] hover:text-[var(--accent)]"
            title="全局搜索"
          >
            搜索政策 / 案例 …<span className="ml-auto font-mono text-[10px]">⌘K</span>
          </button>

        <SourceHealthDot state={healthState} total={sourcesTotal} unhealthy={sourcesUnhealthy} />

        {role === "operations" && pendingReview > 0 && (
          <span className="rounded-full bg-[var(--accent-weak)] px-2.5 py-0.5 text-[11px] font-semibold text-[var(--accent)]">
            待审 {pendingReview}
          </span>
        )}

        {/* Role Switcher */}
        <div className="relative">
          <button
            onClick={() => setShowRoleMenu(!showRoleMenu)}
            className="flex items-center gap-1.5 rounded-md border border-[var(--border)] bg-[var(--surface)] px-2.5 py-1.5 text-[12px] text-[var(--text-2)] hover:border-[var(--accent)] hover:text-[var(--accent)]"
          >
            <span>{currentRole.label}</span>
            <span className="text-[10px]">▼</span>
          </button>
          {showRoleMenu && (
            <div className="absolute right-0 top-full mt-1 w-36 rounded-md border border-[var(--border)] bg-[var(--surface)] py-1 shadow-lg">
              {ROLES.map((r) => (
                <button
                  key={r.value}
                  onClick={() => {
                    onRoleChange?.(r.value);
                    setShowRoleMenu(false);
                  }}
                  className={`block w-full px-3 py-1.5 text-left text-[12px] hover:bg-[var(--surface-2)] ${
                    r.value === role ? "text-[var(--accent)] font-semibold" : "text-[var(--text-2)]"
                  }`}
                >
                  {r.label}
                </button>
              ))}
            </div>
          )}
        </div>

        <span className="flex h-7 w-7 items-center justify-center rounded-full bg-[var(--surface-2)] text-[11px] text-[var(--text-2)]">
          我
        </span>
      </div>
    </header>

    {showSearch && <SearchModal onClose={() => setShowSearch(false)} />}
    </>
  );
}
