"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

// 导航结构 — 基于 Policy Espresso V8.4 原型
const NAV_OPERATIONS = [
  { label: "总览", href: "/radar", icon: "▦" },
  { label: "审核工作台", href: "/review", icon: "≡" },
  { label: "政策库", href: "/policies", icon: "▤" },
  { label: "文档库", href: "/documents", icon: "▧" },
  { label: "业务图谱", href: "/business-map", icon: "▦" },
  { label: "发布中心", href: "/publications", icon: "▣" },
];

const NAV_CONSUMER = [
  { label: "为你推荐", href: "/for-you", icon: "⌂" },
  { label: "政策库", href: "/policies", icon: "▤" },
  { label: "文档库", href: "/documents", icon: "▧" },
  { label: "业务图谱", href: "/business-map", icon: "▦" },
  { label: "我的订阅", href: "/subscriptions", icon: "☆" },
];

const NAV_ADMIN = [
  { label: "系统概览", href: "/health", icon: "◷" },
  { label: "数据源", href: "/sources", icon: "▥" },
  { label: "Agent 与规则", href: "/rules", icon: "⌘" },
  { label: "审计日志", href: "/audit", icon: "≡" },
  { label: "系统设置", href: "/settings", icon: "⚙" },
];

const NAV_MAP: Record<string, typeof NAV_OPERATIONS> = {
  operations: NAV_OPERATIONS,
  consumer: NAV_CONSUMER,
  admin: NAV_ADMIN,
};

function NavItem({ item }: { item: (typeof NAV_OPERATIONS)[number] }) {
  const pathname = usePathname();
  const active = pathname === item.href;
  return (
    <Link
      href={item.href}
      className={`relative flex h-9 items-center gap-2.5 rounded-md px-3 text-[13px] transition-colors ${
        active
          ? "bg-[var(--accent-weak)] text-[var(--accent)] font-semibold"
          : "text-[var(--text-2)] hover:bg-[var(--surface-2)] hover:text-[var(--text)]"
      }`}
    >
      {active && <span className="absolute left-0 top-1.5 h-6 w-0.5 rounded bg-[var(--accent)]" />}
      <span className="w-4 text-center">{item.icon}</span>
      <span>{item.label}</span>
    </Link>
  );
}

export default function Sidebar({ role = "operations" }: { role?: string }) {
  const navItems = NAV_MAP[role] ?? NAV_OPERATIONS;

  return (
    <aside className="fixed left-0 top-0 flex h-full w-[232px] flex-col border-r border-[var(--border)] bg-[var(--surface)]">
      <div className="flex h-14 items-center gap-2.5 border-b border-[var(--border)] px-4">
        <div className="flex h-8 w-8 items-center justify-center rounded bg-[var(--accent)] text-white font-bold text-sm clip-diamond">
          PE
        </div>
        <div>
          <div className="text-[15px] font-semibold tracking-tight">Policy Espresso</div>
          <div className="text-[10px] text-[var(--text-3)]">政策智能平台</div>
        </div>
      </div>
      <nav className="flex-1 space-y-0.5 overflow-y-auto px-2 py-3">
        {navItems.map((item) => (
          <NavItem key={item.label} item={item} />
        ))}
      </nav>
      <div className="border-t border-[var(--border)] px-4 py-3 text-[11px] text-[var(--text-3)]">
        v8.4 · 演示原型
      </div>
    </aside>
  );
}
