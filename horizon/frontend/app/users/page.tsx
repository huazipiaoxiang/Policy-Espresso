"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import ConfirmDialog from "@/components/ConfirmDialog";
import SortableTh from "@/components/SortableTh";
import { useAuth } from "@/components/AuthProvider";
import { API_BASE, demoApiHeaders } from "@/lib/auth";

interface AdminUser {
  id: string;
  username: string;
  role: "admin" | "processor" | "consumer";
  onboarded: boolean;
  created_at: string | null;
}

interface UserSummary {
  total: number;
  admin: number;
  processor: number;
  consumer: number;
}

const ROLE_LABELS: Record<string, string> = {
  admin: "管理员",
  processor: "政策运营专员",
  consumer: "政策使用者",
};

const ROLE_BADGE: Record<string, string> = {
  admin: "red",
  processor: "amber",
  consumer: "green",
};

const PAGE_SIZE = 20;

function dateLabel(value: string | null): string {
  return value ? new Date(value).toLocaleDateString("zh-CN") : "—";
}

export default function UsersPage() {
  const { username: actor } = useAuth();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [summary, setSummary] = useState<UserSummary | null>(null);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [roleFilter, setRoleFilter] = useState("");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  // 新建用户表单
  const [newUsername, setNewUsername] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newRole, setNewRole] = useState<"admin" | "processor" | "consumer">("consumer");

  // 重置密码与删除
  const [resetTarget, setResetTarget] = useState<AdminUser | null>(null);
  const [resetPassword, setResetPassword] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<AdminUser | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
      if (query.trim()) params.set("q", query.trim());
      if (roleFilter) params.set("role", roleFilter);
      const response = await fetch(`${API_BASE}/admin/users?${params.toString()}`, {
        headers: demoApiHeaders(),
        cache: "no-store",
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body?.error?.message || "用户列表加载失败");
      setUsers(body.items || []);
      setTotal(body.total || 0);
      setSummary(body.summary || null);
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "用户列表加载失败");
    } finally {
      setLoading(false);
    }
  }, [page, query, roleFilter]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    setPage(1);
  }, [query, roleFilter]);

  const [sortField, setSortField] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");

  function onSort(field: string) {
    if (sortField === field) {
      setSortDir((dir) => (dir === "asc" ? "desc" : "asc"));
    } else {
      setSortField(field);
      setSortDir("asc");
    }
  }

  const sortedUsers = useMemo(() => {
    if (!sortField) return users;
    return [...users].sort((a, b) => {
      const av = (a as unknown as Record<string, unknown>)[sortField] ?? "";
      const bv = (b as unknown as Record<string, unknown>)[sortField] ?? "";
      if (av < bv) return sortDir === "asc" ? -1 : 1;
      if (av > bv) return sortDir === "asc" ? 1 : -1;
      return 0;
    });
  }, [users, sortField, sortDir]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  async function createUser() {
    if (!newUsername.trim()) {
      setError("请输入用户名");
      return;
    }
    if (newPassword.length < 6) {
      setError("密码至少 6 位");
      return;
    }
    setBusy(true);
    setNotice("");
    try {
      const response = await fetch(`${API_BASE}/admin/users`, {
        method: "POST",
        headers: { ...demoApiHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify({ username: newUsername.trim(), password: newPassword, role: newRole }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body?.error?.message || "创建失败");
      setNotice(`已创建用户「${body.username}」（${ROLE_LABELS[body.role] || body.role}）`);
      setNewUsername("");
      setNewPassword("");
      setError("");
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "创建失败");
    } finally {
      setBusy(false);
    }
  }

  async function changeRole(user: AdminUser, role: string) {
    if (role === user.role) return;
    setBusy(true);
    setNotice("");
    try {
      const response = await fetch(`${API_BASE}/admin/users/${user.id}`, {
        method: "PATCH",
        headers: { ...demoApiHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify({ role }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body?.error?.message || "修改角色失败");
      setNotice(`「${user.username}」角色已改为${ROLE_LABELS[role] || role}`);
      setError("");
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "修改角色失败");
    } finally {
      setBusy(false);
    }
  }

  async function submitReset() {
    if (!resetTarget) return;
    if (resetPassword.length < 6) {
      setError("密码至少 6 位");
      return;
    }
    setBusy(true);
    setNotice("");
    try {
      const response = await fetch(`${API_BASE}/admin/users/${resetTarget.id}`, {
        method: "PATCH",
        headers: { ...demoApiHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify({ password: resetPassword }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body?.error?.message || "重置密码失败");
      setNotice(`已重置「${resetTarget.username}」的密码`);
      setResetTarget(null);
      setResetPassword("");
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "重置密码失败");
    } finally {
      setBusy(false);
    }
  }

  async function removeUser() {
    if (!deleteTarget) return;
    setBusy(true);
    setNotice("");
    try {
      const suffix = actor ? `?actor=${encodeURIComponent(actor)}` : "";
      const response = await fetch(`${API_BASE}/admin/users/${deleteTarget.id}${suffix}`, {
        method: "DELETE",
        headers: demoApiHeaders(),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body?.error?.message || "删除失败");
      }
      setNotice(`已删除用户「${deleteTarget.username}」`);
      setDeleteTarget(null);
      setError("");
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "删除失败");
    } finally {
      setBusy(false);
    }
  }

  const metrics: { key: string; label: string; value: number }[] = [
    { key: "", label: "全部账号", value: summary?.total ?? 0 },
    { key: "admin", label: "管理员", value: summary?.admin ?? 0 },
    { key: "processor", label: "政策运营专员", value: summary?.processor ?? 0 },
    { key: "consumer", label: "政策使用者", value: summary?.consumer ?? 0 },
  ];

  return (
    <main>
      <div className="pagehead">
        <div>
          <div className="eyebrow">USER MANAGEMENT</div>
          <h1>用户管理</h1>
          <p className="sub">管理系统登录账号与角色权限 · 共 {summary?.total ?? total} 个账号</p>
        </div>
        <button className="btn" onClick={() => void load()} disabled={loading}>刷新列表</button>
      </div>

      <div className="grid4">
        {metrics.map((metric) => (
          <button
            key={metric.label}
            className="metric"
            style={{ textAlign: "left" }}
            onClick={() => setRoleFilter(metric.key)}
          >
            <small>{metric.label}</small>
            <b>{metric.value}</b>
            <span>{roleFilter === metric.key ? "当前筛选" : "点击筛选对应账号"}</span>
          </button>
        ))}
      </div>

      {notice && <div className="info" style={{ marginTop: 16 }}>{notice}</div>}
      {error && (
        <div className="notice" style={{ marginTop: 16 }}>
          {error}
          <button className="link" style={{ marginLeft: 12 }} onClick={() => setError("")}>关闭</button>
        </div>
      )}

      {/* 新建账号 */}
      <section className="panel" style={{ marginTop: 18 }}>
        <div className="panelhead"><h2>新建账号</h2><small>角色决定登录后的工作空间</small></div>
        <div className="sectionbody">
          <div className="rowflex" style={{ gap: 10, flexWrap: "wrap", alignItems: "center" }}>
            <input
              className="search"
              value={newUsername}
              onChange={(event) => setNewUsername(event.target.value)}
              placeholder="用户名"
              style={{ width: 180 }}
            />
            <input
              className="search"
              type="password"
              value={newPassword}
              onChange={(event) => setNewPassword(event.target.value)}
              placeholder="密码（至少 6 位）"
              style={{ width: 200 }}
            />
            <select
              className="filter"
              value={newRole}
              onChange={(event) => setNewRole(event.target.value as "admin" | "processor" | "consumer")}
            >
              <option value="consumer">政策使用者</option>
              <option value="processor">政策运营专员</option>
              <option value="admin">管理员</option>
            </select>
            <button className="btn primary" onClick={() => void createUser()} disabled={busy}>
              {busy ? "处理中…" : "创建账号"}
            </button>
          </div>
        </div>
      </section>

      {resetTarget && (
        <div className="confirm-backdrop" role="presentation" onClick={busy ? undefined : () => { setResetTarget(null); setResetPassword(""); }}>
          <div className="confirm-modal" role="dialog" aria-modal="true" aria-label="重置密码" onClick={(event) => event.stopPropagation()}>
            <h2>重置密码</h2>
            <div className="confirm-body">
              <p>为 <b>{resetTarget.username}</b> 设置新密码（至少 6 位），保存后立即生效。</p>
              <input
                className="search"
                type="password"
                value={resetPassword}
                onChange={(event) => setResetPassword(event.target.value)}
                placeholder="请输入新密码"
                style={{ width: "100%", marginTop: 8 }}
              />
            </div>
            <div className="confirm-actions">
              <button className="btn" type="button" disabled={busy} onClick={() => { setResetTarget(null); setResetPassword(""); }}>取消</button>
              <button className="btn danger" type="button" disabled={busy} onClick={() => void submitReset()}>{busy ? "处理中…" : "保存"}</button>
            </div>
          </div>
        </div>
      )}

      <section className="panel" style={{ marginTop: 18 }}>
        <div className="panelhead">
          <h2>{roleFilter ? ROLE_LABELS[roleFilter] : "全部账号"}</h2>
          <small>{total} 个</small>
        </div>
        <div className="toolbar" style={{ gap: 10 }}>
          <input
            className="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="搜索用户名…"
          />
          <select className="filter" value={roleFilter} onChange={(event) => setRoleFilter(event.target.value)}>
            <option value="">全部角色</option>
            <option value="admin">管理员</option>
            <option value="processor">政策运营专员</option>
            <option value="consumer">政策使用者</option>
          </select>
        </div>
        <div className="tablewrap">
          <table>
            <thead>
              <tr>
                <SortableTh label="用户名" field="username" sortField={sortField} sortDir={sortDir} onSort={onSort} />
                <SortableTh label="角色" field="role" sortField={sortField} sortDir={sortDir} onSort={onSort} />
                <th>引导状态</th>
                <SortableTh label="创建时间" field="created_at" sortField={sortField} sortDir={sortDir} onSort={onSort} />
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={5} style={{ textAlign: "center", padding: 36 }}>加载中…</td></tr>
              ) : sortedUsers.length === 0 ? (
                <tr><td colSpan={5} style={{ textAlign: "center", padding: 36, color: "#949aa3" }}>没有匹配的账号</td></tr>
              ) : sortedUsers.map((user) => (
                <tr key={user.id}>
                  <td>
                    <b>{user.username}</b>
                    {user.username === actor && <span className="badge" style={{ marginLeft: 6 }}>当前登录</span>}
                  </td>
                  <td><span className={`badge ${ROLE_BADGE[user.role] || ""}`}>{ROLE_LABELS[user.role] || user.role}</span></td>
                  <td>{user.role === "consumer" ? (user.onboarded ? "已完成主题引导" : "待完成引导") : "—"}</td>
                  <td style={{ whiteSpace: "nowrap" }}>{dateLabel(user.created_at)}</td>
                  <td>
                    <div className="rowflex" style={{ gap: 8, alignItems: "center" }}>
                      <select
                        className="filter"
                        value={user.role}
                        disabled={busy}
                        onChange={(event) => void changeRole(user, event.target.value)}
                        title="调整角色"
                      >
                        <option value="consumer">政策使用者</option>
                        <option value="processor">政策运营专员</option>
                        <option value="admin">管理员</option>
                      </select>
                      <button className="btn" disabled={busy} onClick={() => { setResetTarget(user); setResetPassword(""); }}>
                        重置密码
                      </button>
                      <button className="btn danger" disabled={busy || user.username === actor} onClick={() => setDeleteTarget(user)}>
                        删除
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {total > PAGE_SIZE && (
          <div className="rowflex" style={{ justifyContent: "center", gap: 12, alignItems: "center", padding: 12 }}>
            <button className="btn" disabled={page <= 1} onClick={() => setPage((value) => Math.max(1, value - 1))}>← 上一页</button>
            <span style={{ fontSize: 12, color: "#8b929c" }}>第 {page} / {totalPages} 页 · 共 {total} 条</span>
            <button className="btn" disabled={page >= totalPages} onClick={() => setPage((value) => Math.min(totalPages, value + 1))}>下一页 →</button>
          </div>
        )}
      </section>

      {deleteTarget && (
        <ConfirmDialog
          title={`删除账号 ${deleteTarget.username}`}
          description={<p>删除后该账号将无法登录，且不可恢复。历史操作记录仍保留在审计日志中。</p>}
          acknowledgeLabel="我已确认要删除该账号"
          confirmLabel="删除账号"
          busy={busy}
          onCancel={() => setDeleteTarget(null)}
          onConfirm={() => void removeUser()}
        />
      )}
    </main>
  );
}
