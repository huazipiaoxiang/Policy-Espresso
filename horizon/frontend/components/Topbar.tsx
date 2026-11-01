"use client";

import { useState, useEffect } from "react";
import SearchModal from "./SearchModal";
import { DemoRole, ROLE_CONFIG } from "@/lib/auth";

const THEME_KEY = "horizon-theme";

function applyTheme(dark: boolean) {
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  window.localStorage.setItem(THEME_KEY, dark ? "dark" : "light");
}

export default function Topbar({ role, onLogout }: { role: DemoRole; onLogout: () => void }) {
  const [showSearch, setShowSearch] = useState(false);
  const [dark, setDark] = useState(false);
  const config = ROLE_CONFIG[role];

  useEffect(() => {
    setDark(document.documentElement.dataset.theme === "dark");
  }, []);

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

  const toggleTheme = () => {
    setDark((current) => {
      applyTheme(!current);
      return !current;
    });
  };

  return (
    <>
      <header className="topbar">
        <div className="breadcrumb">Policy Espresso / {config.label}</div>
        <div className="top-right">
          <span className="demo">演示环境 · DEMO</span>
          <span style={{ fontSize: "12px", color: "#4b525c", fontWeight: 700 }}>{config.label}</span>
          <button
            className="btn"
            style={{ padding: "6px 10px", fontSize: "11px" }}
            onClick={toggleTheme}
            aria-label={dark ? "切换到浅色模式" : "切换到深色模式"}
            title={dark ? "浅色模式" : "深色模式"}
          >
            {dark ? (
              <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
              </svg>
            ) : (
              <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
              </svg>
            )}
          </button>
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
