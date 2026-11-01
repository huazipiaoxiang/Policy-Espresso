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
  // Ask AI 全局固定侧栏：默认展开，收起状态按用户偏好持久化
  const [chatOpen, setChatOpen] = useState(() => {
    if (typeof window === "undefined") return true;
    return window.localStorage.getItem("horizon-chat-open") !== "0";
  });
  const isLogin = pathname === "/login";

  useEffect(() => {
    window.localStorage.setItem("horizon-chat-open", chatOpen ? "1" : "0");
  }, [chatOpen]);

  useEffect(() => {
    if (!ready) return;
    if (!role && !isLogin) {
      router.replace("/login");
      return;
    }
    if (role && (isLogin || pathname === "/")) {
      router.replace(ROLE_CONFIG[role].home);
      return;
    }
    if (role && !canAccess(role, pathname)) {
      router.replace(ROLE_CONFIG[role].home);
    }
  }, [isLogin, pathname, ready, role, router]);

  if (isLogin && (!role || !ready)) return <>{children}</>;

  if (!ready || !role || pathname === "/" || !canAccess(role, pathname)) {
    return (
      <main style={{ minHeight: "100vh", display: "grid", placeItems: "center", color: "#6b7280" }}>
        正在进入工作空间…
      </main>
    );
  }

  return (
    <div className={`shell${chatOpen ? " with-chat" : ""}`}>
      <Sidebar role={role} />
      <div className="main">
        <Topbar role={role} onLogout={() => { logout(); router.replace("/login"); }} />
        <div className="content">{children}</div>
      </div>
      {chatOpen ? <ChatPanel onClose={() => setChatOpen(false)} /> : <ChatButton onClick={() => setChatOpen(true)} />}
    </div>
  );
}
