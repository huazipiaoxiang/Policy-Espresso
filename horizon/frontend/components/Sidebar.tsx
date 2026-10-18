"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

// 导航结构与 docs/08 §2 一致；未实现页面统一指向 /soon
const NAV_MAIN = [
  { label: "雷达", href: "/radar", icon: "◉", ready: true },
  { label: "政策", href: "/policies", icon: "▤", ready: true },
  { label: "文档", href: "/documents", icon: "▥", ready: true },
  { label: "审核台", href: "/review", icon: "✓", ready: true, badge: 0 },
  { label: "预警", href: "/alerts", icon: "!", ready: true },
  { label: "案例库", href: "/cases", icon: "▦", ready: true },
  { label: "业务图谱", href: "/business-map", icon: "▧", ready: true },
  { label: "Studio", href: "/studio", icon: "✎", ready: true },
];

const NAV_ADMIN = [
  { label: "数据源", href: "/sources", icon: "⌁", ready: true },
  { label: "审计", href: "/audit", icon: "≡", ready: true },
  { label: "设置", href: "/settings", icon: "⚙", ready: true },
];

function NavItem({ item }: { item: (typeof NAV_MAIN)[number] }) {
  const pathname = usePathname();
  const active = pathname === item.href;
  return (
    <Link
      href={item.href}
      className={`relative flex h-9 items-center gap-2.5 rounded-md px-3 text-[13px] transition-colors ${
        active
          ? "bg-[var(--surface-2)] text-[var(--text)]"
          : "text-[var(--text-2)] hover:bg-[var(--surface-2)] hover:text-[var(--text)]"
      }`}
    >
      {active && <span className="absolute left-0 top-1.5 h-6 w-0.5 rounded bg-[var(--accent)]" />}
      <span className="w-4 text-center text-[var(--text-3)]">{item.icon}</span>
      <span>{item.label}</span>
      {!item.ready && <span className="ml-auto text-[10px] text-[var(--text-3)]">Phase+</span>}
      {"badge" in item && typeof item.badge === "number" && item.badge > 0 && (
        <span className="ml-auto rounded-full bg-[var(--accent-weak)] px-1.5 text-[11px] text-[var(--accent)]">
          {item.badge}
        </span>
      )}
    </Link>
  );
}

export default function Sidebar() {
  return (
    <aside className="fixed left-0 top-0 flex h-full w-[232px] flex-col border-r border-[var(--border)] bg-[var(--surface)]">
      <div className="flex h-14 items-center gap-2 border-b border-[var(--border)] px-4">
        <span className="text-[15px] font-semibold tracking-wide">
          HORIZON <span className="text-[var(--accent)]">·</span> 政策雷达
        </span>
      </div>
      <nav className="flex-1 space-y-0.5 overflow-y-auto px-2 py-3">
        {NAV_MAIN.map((item) => (
          <NavItem key={item.label} item={item} />
        ))}
        <div className="my-3 border-t border-[var(--border)]" />
        {NAV_ADMIN.map((item) => (
          <NavItem key={item.label} item={item} />
        ))}
      </nav>
      <div className="border-t border-[var(--border)] px-4 py-3 text-[11px] text-[var(--text-3)]">
        v0.1.0 · Phase 5 阿里云部署
      </div>
    </aside>
  );
}
