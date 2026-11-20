"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { API_BASE, DemoRole, ROLE_CONFIG, demoApiHeaders } from "@/lib/auth";

export default function Sidebar({ role }: { role: DemoRole }) {
  const pathname = usePathname();
  const router = useRouter();
  const config = ROLE_CONFIG[role];
  const segments = pathname.split("/").filter(Boolean);
  // 详情页（政策解读 /documents/{id}、/policies/{id}、/cases/{id}）在侧边栏给出返回入口
  const isDetailPage = segments.length > 1;
  // 政策解读页：侧边栏直接展示当前政策标题并高亮，而不是高亮「政策库」
  // 仅匹配 /policies/{id} 这一层详情路由，离开即不显示卡片
  const isPolicyDetail = segments.length === 2 && segments[0] === "policies";
  const policyId = isPolicyDetail ? segments[1] : null;
  const [policyTitle, setPolicyTitle] = useState<string | null>(null);

  useEffect(() => {
    if (!policyId) {
      setPolicyTitle(null);
      return;
    }
    setPolicyTitle(null);
    let active = true;
    fetch(`${API_BASE}/policies/${policyId}`, { headers: demoApiHeaders(), cache: "no-store" })
      .then((resp) => (resp.ok ? resp.json() : null))
      .then((body) => {
        if (active) setPolicyTitle(body?.title || null);
      })
      .catch(() => {
        if (active) setPolicyTitle(null);
      });
    return () => {
      active = false;
    };
  }, [policyId]);

  function goBack() {
    if (typeof window !== "undefined" && window.history.length > 1) {
      router.back();
      return;
    }
    // 直接打开详情链接（无浏览历史）时回落到上级列表
    router.push(`/${segments[0] || ""}`);
  }

  return (
    <aside className="side">
      <div className="brand">
        <div className="mark">✦</div>
        <div>
          <strong>Policy Espresso</strong>
          <small>政策智能速递及分析平台</small>
        </div>
      </div>
      {isDetailPage && (
        <button type="button" className="side-back" onClick={goBack}>
          ← 返回
        </button>
      )}
      <div style={{ fontSize: "10px", color: "#9ca1a9", fontWeight: 700, letterSpacing: "0.09em", textTransform: "uppercase", margin: "0 10px -18px" }}>
        当前工作空间
      </div>
      <div style={{ fontSize: "12px", fontWeight: 700, color: "#4b525c", margin: "0 10px -12px" }}>
        {config.label}
      </div>
      <nav className="nav">
        {policyId && (
          <div className="nav-current" title={policyTitle || "政策解读"}>
            <small>政策解读</small>
            <strong>{policyTitle || "加载中…"}</strong>
          </div>
        )}
        {config.nav.map((item) => {
          // 政策解读页由「当前政策」卡片承担高亮，导航项不再重复高亮「政策库」
          const active = !policyId && (pathname === item.href || pathname.startsWith(`${item.href}/`));
          return (
            <Link key={item.id} href={item.href} className={active ? "active" : ""}>
              {item.label}
            </Link>
          );
        })}
      </nav>
      <div className="sidebar-foot">
        演示范围：香港 · 中国内地 · 大湾区
        <br />
        当前角色仅显示已授权的功能和操作。
      </div>
    </aside>
  );
}
