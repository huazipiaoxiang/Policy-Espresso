"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";
import {
  DemoRole, ROLE_STORAGE_KEY, USERNAME_STORAGE_KEY,
  getStoredRole, getStoredUsername, writeSession, removeSession,
} from "@/lib/auth";

interface AuthValue {
  role: DemoRole | null;
  username: string | null;
  ready: boolean;
  login: (role: DemoRole) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthValue | null>(null);

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}

export default function AuthProvider({ children }: { children: React.ReactNode }) {
  const [role, setRole] = useState<DemoRole | null>(null);
  const [username, setUsername] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    setRole(getStoredRole());
    setUsername(getStoredUsername());
    setReady(true);
    // 会话数据在 sessionStorage：每个标签页独立，不再监听 storage 事件，
    // 避免同浏览器多标签页登录时被其它标签页同步覆盖。
  }, []);

  const value = useMemo<AuthValue>(() => ({
    role,
    username,
    ready,
    login: (nextRole) => {
      writeSession(ROLE_STORAGE_KEY, nextRole);
      setRole(nextRole);
      // 用户名由登录页写入（登录/注册成功后的真实账号），这里同步到 context，
      // 「为你推荐」据此与客户经理 relationship_manager 匹配。
      setUsername(getStoredUsername());
    },
    logout: () => {
      removeSession(ROLE_STORAGE_KEY);
      removeSession(USERNAME_STORAGE_KEY);
      setRole(null);
      setUsername(null);
    },
  }), [role, username, ready]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
