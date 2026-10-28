"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { DemoRole, ROLE_CONFIG } from "@/lib/auth";

export default function Sidebar({ role }: { role: DemoRole }) {
  const pathname = usePathname();
  const config = ROLE_CONFIG[role];

  return (
    <aside className="side">
      <div className="brand">
        <div className="mark">✦</div>
        <div>
          <strong>Policy Espresso</strong>
          <small>监管政策智能分析平台</small>
        </div>
      </div>
      <div style={{ fontSize: "10px", color: "#9ca1a9", fontWeight: 700, letterSpacing: "0.09em", textTransform: "uppercase", margin: "0 10px -18px" }}>
        当前工作空间
      </div>
      <div style={{ fontSize: "12px", fontWeight: 700, color: "#4b525c", margin: "0 10px -12px" }}>
        {config.label}
      </div>
      <nav className="nav">
        {config.nav.map((item) => {
          const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
          return (
            <Link key={item.id} href={item.href} className={active ? "active" : ""}>
              <span className="ico">{item.icon}</span>
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
