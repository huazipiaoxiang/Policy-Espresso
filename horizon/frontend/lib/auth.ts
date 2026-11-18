export type DemoRole = "admin" | "consumer" | "processor";

export const ROLE_STORAGE_KEY = "horizon-demo-role";

export interface NavItem {
  id: string;
  icon: string;
  label: string;
  href: string;
}

export const ROLE_CONFIG: Record<DemoRole, {
  label: string;
  shortLabel: string;
  description: string;
  home: string;
  avatar: string;
  nav: NavItem[];
}> = {
  admin: {
    label: "管理员",
    shortLabel: "管理",
    description: "管理政策数据、数据源、规则和系统运行",
    home: "/health",
    avatar: "管",
    nav: [
      { id: "health", icon: "◷", label: "系统概览", href: "/health" },
      { id: "library", icon: "▤", label: "政策数据库", href: "/policies" },
      { id: "documents", icon: "▧", label: "原文库", href: "/documents" },
      { id: "customers", icon: "▤", label: "客户信息", href: "/customers" },
      { id: "mapping", icon: "▦", label: "业务图谱", href: "/business-map" },
      { id: "sources", icon: "▥", label: "数据源", href: "/sources" },
      { id: "rules", icon: "⌘", label: "Agent 与规则", href: "/rules" },
      { id: "audit", icon: "≡", label: "审计日志", href: "/audit" },
      { id: "settings", icon: "⚙", label: "系统设置", href: "/settings" },
    ],
  },
  processor: {
    label: "政策加工人员",
    shortLabel: "加工",
    description: "负责政策加工、审核与发布全流程",
    home: "/radar",
    avatar: "加",
    nav: [
      { id: "dashboard", icon: "▦", label: "总览 Dashboard", href: "/radar" },
      { id: "mapping", icon: "▦", label: "业务图谱", href: "/business-map" },
      { id: "library", icon: "▤", label: "政策库", href: "/policies" },
      { id: "documents", icon: "▧", label: "原文库", href: "/documents" },
      { id: "publications", icon: "▣", label: "发布中心", href: "/publications" },
    ],
  },
  consumer: {
    label: "政策使用者",
    shortLabel: "使用",
    description: "查看推荐政策、业务影响和个人订阅",
    home: "/for-you",
    avatar: "用",
    nav: [
      { id: "forYou", icon: "⌂", label: "为你推荐", href: "/for-you" },
      { id: "library", icon: "▤", label: "政策库", href: "/policies" },
      { id: "subscriptions", icon: "☆", label: "我的订阅", href: "/subscriptions" },
    ],
  },
};

export const DEMO_ROLES = Object.keys(ROLE_CONFIG) as DemoRole[];

export function isDemoRole(value: string | null): value is DemoRole {
  return Boolean(value && DEMO_ROLES.includes(value as DemoRole));
}

export function getStoredRole(): DemoRole | null {
  if (typeof window === "undefined") return null;
  const value = window.localStorage.getItem(ROLE_STORAGE_KEY);
  return isDemoRole(value) ? value : null;
}

export function canAccess(role: DemoRole, pathname: string): boolean {
  if (pathname === "/" || pathname === "/login") return true;
  if (role === "consumer" && /^\/policies\/[^/]+$/.test(pathname)) return true;
  // 业务图谱已嵌入「为你推荐」首页，不再作为独立导航项，但保留路由直达
  if (pathname.startsWith("/business-map")) return true;
  // 审计日志对运营角色只读共享
  if (role !== "consumer" && pathname.startsWith("/audit")) return true;
  return ROLE_CONFIG[role].nav.some((item) =>
    pathname === item.href || pathname.startsWith(`${item.href}/`)
  );
}

export function demoApiHeaders(): Record<string, string> {
  // 客户端统一走同源 BFF 代理（/api/proxy），X-API-Key 由服务端注入，这里只透传角色。
  const role = getStoredRole();
  return {
    ...(role ? { "X-Demo-Role": role } : {}),
  };
}

export const API_BASE = "/api/proxy";
