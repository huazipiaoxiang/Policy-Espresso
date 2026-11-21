"use client";

import { useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import {
  DEMO_ROLES, ROLE_CONFIG, DemoRole,
  USERNAME_STORAGE_KEY, ONBOARDING_KEY, PENDING_REDIRECT_KEY,
  writeSession, removeSession,
} from "@/lib/auth";

export default function LoginPage() {
  const { login } = useAuth();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<DemoRole>("consumer");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!username.trim() || !password) {
      setError("请输入用户名和密码");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const payload: Record<string, string> = { username: username.trim(), password };
      if (mode === "register") payload.role = role;
      const resp = await fetch(`/api/proxy/auth/${mode}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const body = await resp.json();
      if (!resp.ok) throw new Error(body?.error?.message || "操作失败");
      // 登录/注册成功：以返回（或所选）角色进入系统
      const finalRole = (body.role || role) as DemoRole;
      writeSession(USERNAME_STORAGE_KEY, body.username || username.trim());
      // 政策使用者首次登录：先引导选择关注主题；跳转目标交给 AppShell 统一执行，避免与 /login 重定向竞态
      const isFirstConsumer = finalRole === "consumer" && body.onboarded === false;
      if (isFirstConsumer) {
        writeSession(ONBOARDING_KEY, "1");
      } else {
        removeSession(ONBOARDING_KEY);
      }
      const target = isFirstConsumer ? "/subscriptions" : ROLE_CONFIG[finalRole].home;
      writeSession(PENDING_REDIRECT_KEY, target);
      login(finalRole);
      // 登录成功后整页跳转（不用客户端 router.replace）：开发服务器重启后旧标签页的
      // JS chunk 可能失效，客户端路由会静默失败，页面停在登录页/占位页。
      window.location.assign(target);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "操作失败");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="login-shell">
      <section style={{ width: "min(980px, 100%)" }}>
        <div style={{ textAlign: "center", marginBottom: 30 }}>
          <div className="eyebrow">POLICY ESPRESSO</div>
          <h1 style={{ margin: "8px 0 10px", fontSize: 32 }}>政策智能速递及分析平台</h1>
          <p className="sub">登录进入对应工作空间</p>
        </div>

        <div className="panel" style={{ maxWidth: 420, margin: "0 auto", padding: 24 }}>
          <div className="tabs" style={{ marginBottom: 16 }}>
            <button
              type="button"
              className={`tab${mode === "login" ? " active" : ""}`}
              onClick={() => { setMode("login"); setError(""); }}
            >
              登录
            </button>
            <button
              type="button"
              className={`tab${mode === "register" ? " active" : ""}`}
              onClick={() => { setMode("register"); setError(""); }}
            >
              注册
            </button>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <small>用户名</small>
              <input
                className="search"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="请输入用户名"
                autoComplete="username"
              />
            </label>
            <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <small>密码</small>
              <input
                className="search"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="请输入密码"
                autoComplete={mode === "login" ? "current-password" : "new-password"}
              />
            </label>
            {mode === "register" && (
              <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                <small>用户角色</small>
                <select
                  className="filter"
                  value={role}
                  onChange={(e) => setRole(e.target.value as DemoRole)}
                >
                  {DEMO_ROLES.map((r) => (
                    <option key={r} value={r}>{ROLE_CONFIG[r].label}</option>
                  ))}
                </select>
              </label>
            )}
            {error && <div className="notice" style={{ margin: 0 }}>{error}</div>}
            <button className="btn primary" disabled={busy} onClick={submit}>
              {busy ? "处理中…" : mode === "login" ? "登录" : "注册"}
            </button>
          </div>
        </div>
        <p className="login-note">
          演示登录不连接真实 SSO；刷新后保持当前角色，退出后返回本页。
        </p>
      </section>
    </main>
  );
}
