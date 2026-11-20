"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import Sidebar from "@/components/Sidebar";
import Topbar from "@/components/Topbar";
import ChatButton from "@/components/ChatButton";
import ChatPanel from "@/components/ChatPanel";
import { useAuth } from "@/components/AuthProvider";
import { ROLE_CONFIG, canAccess } from "@/lib/auth";

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { role, ready, logout } = useAuth();
  // Ask AI 浮窗：默认关闭，由右下角按钮打开（不记忆开关，避免「打开过一次就永远默认开」）
  const [chatOpen, setChatOpen] = useState(false);
  const isLogin = pathname === "/login";

  useEffect(() => {
    if (!ready) return;
    if (!role && !isLogin) {
      router.replace("/login");
      return;
    }
    if (role && (isLogin || pathname === "/")) {
      // 登录/注册后：优先按 login 页写入的目标跳转（如首次引导），否则回落到角色首页。
      // 旧会话可能残留别的角色/旧版本的目标路径，必须校验可访问性，否则会跳到
      // 本角色无权访问的页面并卡在占位页。
      const pending = window.localStorage.getItem("horizon-pending-redirect");
      window.localStorage.removeItem("horizon-pending-redirect");
      const target = pending && canAccess(role, pending) ? pending : ROLE_CONFIG[role].home;
      router.replace(target);
      return;
    }
    if (role && !canAccess(role, pathname)) {
      router.replace(ROLE_CONFIG[role].home);
    }
  }, [isLogin, pathname, ready, role, router]);

  // 兜底：开发服务器重启后旧标签页里的 chunk 可能失效，router.replace 会静默失败，
  // 页面永久停在「正在进入工作空间」。2.5 秒后改用整页导航重新加载最新资源。
  useEffect(() => {
    if (!ready) return;
    const needsRedirect = role
      ? isLogin || pathname === "/" || !canAccess(role, pathname)
      : !isLogin;
    if (!needsRedirect) return;
    const target = role ? ROLE_CONFIG[role].home : "/login";
    const timer = window.setTimeout(() => {
      window.localStorage.removeItem("horizon-pending-redirect");
      if (window.location.pathname === target) window.location.reload();
      else window.location.replace(target);
    }, 2500);
    return () => window.clearTimeout(timer);
  }, [ready, role, isLogin, pathname]);

  // 兜底：登录态读取（AuthProvider 的 ready）若因旧 chunk 失效一直为 false，
  // 页面会永远停在登录页且登录按钮无响应，3 秒后整页重载一次。
  useEffect(() => {
    if (ready) return;
    const timer = window.setTimeout(() => window.location.reload(), 3000);
    return () => window.clearTimeout(timer);
  }, [ready]);

  if (isLogin && (!role || !ready)) return <>{children}</>;

  if (!ready || !role || pathname === "/" || !canAccess(role, pathname)) {
    const target = role ? ROLE_CONFIG[role].home : "/login";
    return (
      <main style={{ minHeight: "100vh", display: "grid", placeItems: "center", color: "#6b7280" }}>
        <div style={{ textAlign: "center" }}>
          <p>正在进入工作空间…</p>
          <button
            className="btn"
            onClick={() => {
              window.localStorage.removeItem("horizon-pending-redirect");
              window.location.replace(target);
            }}
          >
            重新进入
          </button>
        </div>
      </main>
    );
  }

  return (
    <div className="shell">
      {/* key 绑定路径：路由切换时重建侧边栏，避免「当前政策」高亮等状态残留 */}
      <Sidebar key={pathname} role={role} />
      <div className="main">
        <Topbar role={role} onLogout={() => { logout(); router.replace("/login"); }} />
        <div className="content">{children}</div>
      </div>
      {chatOpen ? <ChatPanel onClose={() => setChatOpen(false)} /> : <ChatButton onClick={() => setChatOpen(true)} />}
    </div>
  );
}
