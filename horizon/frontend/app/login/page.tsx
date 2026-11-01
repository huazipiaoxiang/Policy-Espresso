"use client";

import { useRouter } from "next/navigation";
import { useAuth } from "@/components/AuthProvider";
import { DEMO_ROLES, ROLE_CONFIG, DemoRole } from "@/lib/auth";

export default function LoginPage() {
  const router = useRouter();
  const { login } = useAuth();

  const chooseRole = (role: DemoRole) => {
    login(role);
    router.replace(ROLE_CONFIG[role].home);
  };

  return (
    <main className="login-shell">
      <section style={{ width: "min(980px, 100%)" }}>
        <div style={{ textAlign: "center", marginBottom: 30 }}>
          <div className="eyebrow">POLICY ESPRESSO</div>
          <h1 style={{ margin: "8px 0 10px", fontSize: 32 }}>监管政策智能分析平台</h1>
          <p className="sub">选择演示角色，一键进入对应工作空间</p>
        </div>
        <div style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))",
          gap: 14,
        }}>
          {DEMO_ROLES.map((role) => {
            const config = ROLE_CONFIG[role];
            return (
              <button
                key={role}
                className="panel login-card"
                onClick={() => chooseRole(role)}
              >
                <div className="avatar" style={{ marginBottom: 16 }}>{config.avatar}</div>
                <strong style={{ display: "block", fontSize: 17, marginBottom: 8 }}>{config.label}</strong>
                <span className="login-desc">
                  {config.description}
                </span>
                <span className="login-cta">
                  以此角色登录 →
                </span>
              </button>
            );
          })}
        </div>
        <p className="login-note">
          演示登录不连接真实 SSO；刷新后保持当前角色，退出后返回本页。
        </p>
      </section>
    </main>
  );
}
