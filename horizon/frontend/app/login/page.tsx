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
    <main style={{
      minHeight: "100vh",
      display: "grid",
      placeItems: "center",
      padding: 24,
      background: "linear-gradient(135deg, #f7f7f8 0%, #ffffff 55%, #fff1f2 100%)",
    }}>
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
                className="panel"
                onClick={() => chooseRole(role)}
                style={{
                  padding: 22,
                  textAlign: "left",
                  cursor: "pointer",
                  border: "1px solid #e5e7eb",
                  background: "#fff",
                  minHeight: 178,
                }}
              >
                <div className="avatar" style={{ marginBottom: 16 }}>{config.avatar}</div>
                <strong style={{ display: "block", fontSize: 17, marginBottom: 8 }}>{config.label}</strong>
                <span style={{ display: "block", color: "#6b7280", fontSize: 12, lineHeight: 1.7, minHeight: 42 }}>
                  {config.description}
                </span>
                <span style={{ display: "block", color: "#db0011", fontSize: 12, fontWeight: 700, marginTop: 14 }}>
                  以此角色登录 →
                </span>
              </button>
            );
          })}
        </div>
        <p style={{ textAlign: "center", color: "#8b929c", fontSize: 12, marginTop: 24 }}>
          演示登录不连接真实 SSO；刷新后保持当前角色，退出后返回本页。
        </p>
      </section>
    </main>
  );
}
