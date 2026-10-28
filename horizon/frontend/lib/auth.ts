export type DemoRole = "admin" | "analyst" | "approver" | "publisher" | "consumer";

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
      { id: "mapping", icon: "▦", label: "业务图谱", href: "/business-map" },
      { id: "sources", icon: "▥", label: "数据源", href: "/sources" },
      { id: "rules", icon: "⌘", label: "Agent 与规则", href: "/rules" },
      { id: "audit", icon: "≡", label: "审计日志", href: "/audit" },
      { id: "settings", icon: "⚙", label: "系统设置", href: "/settings" },
    ],
  },
  analyst: {
    label: "初级审核员",
    shortLabel: "初审",
    description: "处理一级审核任务，核对政策解读和证据",
    home: "/radar",
    avatar: "初",
    nav: [],
  },
  approver: {
    label: "二级审核员",
    shortLabel: "复审",
    description: "处理二级审核任务，复核重点政策结论",
    home: "/radar",
    avatar: "复",
    nav: [],
  },
  publisher: {
    label: "发布者",
    shortLabel: "发布",
    description: "查看已审核政策并执行发布",
    home: "/radar",
    avatar: "发",
    nav: [],
  },
  consumer: {
    label: "政策使用者",
    shortLabel: "使用",
    description: "查看推荐政策、业务影响和个人订阅",
    home: "/for-you",
    avatar: "用",
    nav: [
      { id: "forYou", icon: "⌂", label: "为你推荐", href: "/for-you" },
      { id: "mapping", icon: "▦", label: "业务图谱", href: "/business-map" },
      { id: "subscriptions", icon: "☆", label: "我的订阅", href: "/subscriptions" },
    ],
  },
};

const operationsNav: NavItem[] = [
  { id: "dashboard", icon: "▦", label: "总览 Dashboard", href: "/radar" },
  { id: "queue", icon: "≡", label: "审核工作台", href: "/review" },
  { id: "mapping", icon: "▦", label: "业务图谱", href: "/business-map" },
  { id: "library", icon: "▤", label: "政策库", href: "/policies" },
  { id: "documents", icon: "▧", label: "原文库", href: "/documents" },
  { id: "publications", icon: "▣", label: "发布中心", href: "/publications" },
];

ROLE_CONFIG.analyst.nav = operationsNav;
ROLE_CONFIG.approver.nav = operationsNav;
ROLE_CONFIG.publisher.nav = operationsNav;

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
  return ROLE_CONFIG[role].nav.some((item) =>
    pathname === item.href || pathname.startsWith(`${item.href}/`)
  );
}

export function demoApiHeaders(): Record<string, string> {
  const role = getStoredRole();
  return {
    "X-API-Key": process.env.NEXT_PUBLIC_API_KEY || "dev-local-key",
    ...(role ? { "X-Demo-Role": role } : {}),
  };
}

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000/api/v1";
