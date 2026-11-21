export type DemoRole = "admin" | "consumer" | "processor";

export const ROLE_STORAGE_KEY = "horizon-demo-role";
export const USERNAME_STORAGE_KEY = "horizon-username";
export const ONBOARDING_KEY = "horizon-onboarding";
export const PENDING_REDIRECT_KEY = "horizon-pending-redirect";

// 会话类数据统一放 sessionStorage：每个标签页独立，避免同浏览器多标签页登录时串号。
// 主题等设备级偏好仍用 localStorage（见 Topbar）。
function sessionStore(): Storage | null {
  if (typeof window === "undefined") return null;
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

export function readSession(key: string): string | null {
  return sessionStore()?.getItem(key) ?? null;
}

export function writeSession(key: string, value: string): void {
  sessionStore()?.setItem(key, value);
}

export function removeSession(key: string): void {
  sessionStore()?.removeItem(key);
}

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
      { id: "preprocess", icon: "◫", label: "政策预处理", href: "/preprocess" },
      { id: "documents", icon: "▧", label: "原文库", href: "/documents" },
      { id: "customers", icon: "▤", label: "客户信息", href: "/customers" },
      { id: "sources", icon: "▥", label: "数据源", href: "/sources" },
      { id: "rules", icon: "⌘", label: "Agent 与规则", href: "/rules" },
      { id: "audit", icon: "≡", label: "审计日志", href: "/audit" },
      { id: "users", icon: "◍", label: "用户管理", href: "/users" },
      { id: "settings", icon: "⚙", label: "系统设置", href: "/settings" },
    ],
  },
  processor: {
    label: "政策运营专员",
    shortLabel: "运营",
    description: "跟踪政策使用者反馈与 AI 自动发布结果",
    home: "/follow-up",
    avatar: "运",
    nav: [
      { id: "followup", icon: "▣", label: "政策跟进中心", href: "/follow-up" },
      { id: "library", icon: "▤", label: "政策库", href: "/policies" },
      { id: "preprocess", icon: "◫", label: "政策预处理", href: "/preprocess" },
      { id: "documents", icon: "▧", label: "原文库", href: "/documents" },
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
  const value = readSession(ROLE_STORAGE_KEY);
  return isDemoRole(value) ? value : null;
}

export function getStoredUsername(): string | null {
  const value = readSession(USERNAME_STORAGE_KEY);
  return value && value.trim() ? value.trim() : null;
}

export function canAccess(role: DemoRole, pathname: string): boolean {
  if (pathname === "/" || pathname === "/login") return true;
  if (role === "consumer" && /^\/policies\/[^/]+$/.test(pathname)) return true;
  // 「总览 Dashboard」与「发布中心」已合并为「政策跟进中心」，旧路由保留跳转
  if (role === "processor" && (pathname.startsWith("/radar") || pathname.startsWith("/publications"))) return true;
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
