"use client";

import { useState, useEffect } from "react";
import SearchModal from "./SearchModal";
import { DemoRole, ROLE_CONFIG } from "@/lib/auth";

export default function Topbar({ role, onLogout }: { role: DemoRole; onLogout: () => void }) {
  const [showSearch, setShowSearch] = useState(false);
  const config = ROLE_CONFIG[role];

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (role !== "consumer" && (e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setShowSearch((prev) => !prev);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [role]);

  return (
    <>
      <header className="topbar">
        <div className="breadcrumb">Policy Espresso / {config.label}</div>
        <div className="top-right">
          <span className="demo">演示环境 · DEMO</span>
          <span style={{ fontSize: "12px", color: "#4b525c", fontWeight: 700 }}>{config.label}</span>
          <button className="btn" style={{ padding: "6px 10px", fontSize: "11px" }} onClick={onLogout}>
            退出登录
          </button>
          <div className="avatar">{config.avatar}</div>
        </div>
      </header>
      {showSearch && role !== "consumer" && <SearchModal onClose={() => setShowSearch(false)} />}
    </>
  );
}
