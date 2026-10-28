"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { DemoRole, ROLE_STORAGE_KEY, getStoredRole } from "@/lib/auth";

interface AuthValue {
  role: DemoRole | null;
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
  const [ready, setReady] = useState(false);

  useEffect(() => {
    setRole(getStoredRole());
    setReady(true);
    const syncRole = () => setRole(getStoredRole());
    window.addEventListener("storage", syncRole);
    return () => window.removeEventListener("storage", syncRole);
  }, []);

  const value = useMemo<AuthValue>(() => ({
    role,
    ready,
    login: (nextRole) => {
      window.localStorage.setItem(ROLE_STORAGE_KEY, nextRole);
      setRole(nextRole);
    },
    logout: () => {
      window.localStorage.removeItem(ROLE_STORAGE_KEY);
      setRole(null);
    },
  }), [role, ready]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
