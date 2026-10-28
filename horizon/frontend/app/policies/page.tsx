"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import ConfirmDialog from "@/components/ConfirmDialog";
import { API_BASE, demoApiHeaders } from "@/lib/auth";
import { JURISDICTION_LABELS, POLICY_STATUS_LABELS, impactScoreLabel } from "@/lib/labels";

interface Policy {
  id: string;
  document_id: string;
  title: string;
  issuing_body: string;
  doc_number: string | null;
  published_at: string | null;
  jurisdiction: string;
  themes: string[];
  impacted_domains: string[];
  status: string;
  priority: string;
  score_total: number;
  review_completed_at: string | null;
  dispatched_at: string | null;
}

type TabKey = "all" | "today_new" | "pending_review" | "published" | "high_priority";

const tabs: { key: TabKey; label: string }[] = [
  { key: "all", label: "全部政策" },
  { key: "today_new", label: "今日新增" },
  { key: "pending_review", label: "待审核" },
  { key: "published", label: "已发布" },
  { key: "high_priority", label: "高优先级" },
];

function dateLabel(value: string | null) {
  return value ? new Date(value).toLocaleString("zh-CN", { hour12: false }) : "—";
}

export default function PoliciesPage() {
  const { role } = useAuth();
  const searchParams = useSearchParams();
  const initialView = searchParams.get("view") as TabKey | null;
  const [activeTab, setActiveTab] = useState<TabKey>(tabs.some((tab) => tab.key === initialView) ? initialView! : "all");
  const [search, setSearch] = useState("");
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [currentPage, setCurrentPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [counts, setCounts] = useState<Record<TabKey, number>>({ all: 0, today_new: 0, pending_review: 0, published: 0, high_priority: 0 });
  const [refreshKey, setRefreshKey] = useState(0);
  const [busyId, setBusyId] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<Policy | null>(null);
  const pageSize = 20;

  useEffect(() => {
    const view = searchParams.get("view") as TabKey | null;
    if (tabs.some((tab) => tab.key === view)) setActiveTab(view!);
  }, [searchParams]);

  useEffect(() => setCurrentPage(1), [activeTab, search]);

  const request = useCallback(async (path: string, init?: RequestInit) => {
    const response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { ...demoApiHeaders(), ...(init?.headers || {}) },
    });
    if (!response.ok) {
      const body = await response.json().catch(() => null);
      throw new Error(body?.error?.message || `请求失败（${response.status}）`);
    }
    return response;
  }, []);

  useEffect(() => {
    const params = new URLSearchParams({ page: String(currentPage), page_size: String(pageSize) });
    if (activeTab === "today_new") params.set("fetched", "today");
    if (activeTab === "pending_review") params.set("status", "pending_review,in_review");
    if (activeTab === "published") params.set("status", "published");
    if (activeTab === "high_priority") params.set("priority", "P0,P1");
    if (search.trim()) params.set("q", search.trim());
    setLoading(true);
    request(`/policies?${params}`)
      .then((response) => response.json())
      .then((data) => {
        setPolicies(data.items || []);
        setTotal(data.total || 0);
        setError("");
      })
      .catch((reason: Error) => setError(reason.message))
      .finally(() => setLoading(false));
  }, [activeTab, currentPage, refreshKey, request, search]);

  useEffect(() => {
    const urls: [TabKey, string][] = [
      ["all", ""], ["today_new", "&fetched=today"], ["pending_review", "&status=pending_review,in_review"],
      ["published", "&status=published"], ["high_priority", "&priority=P0,P1"],
    ];
    Promise.all(urls.map(async ([key, filter]) => {
      const response = await request(`/policies?page=1&page_size=1${filter}`);
      return [key, (await response.json()).total || 0] as const;
    })).then((entries) => setCounts(Object.fromEntries(entries) as Record<TabKey, number>))
      .catch(() => undefined);
  }, [refreshKey, request]);

  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const visiblePages = useMemo(() => {
    const pages: number[] = [];
    for (let page = Math.max(1, currentPage - 2); page <= Math.min(totalPages, currentPage + 2); page += 1) pages.push(page);
    return pages;
  }, [currentPage, totalPages]);

  async function removePolicy() {
    const policy = deleteTarget;
    if (!policy) return;
    setBusyId(policy.id);
    setNotice("");
    try {
      await request(`/policies/${policy.id}`, { method: "DELETE" });
      setDeleteTarget(null);
      setNotice(`政策「${policy.title}」已删除，原始文档已保留`);
      setRefreshKey((key) => key + 1);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "删除失败");
    } finally {
      setBusyId("");
    }
  }

  async function analyzePolicy(policy: Policy) {
    setBusyId(policy.id);
    try {
      await request(`/policies/${policy.id}/analyze`, { method: "POST" });
      setNotice("重新分析完成");
      setRefreshKey((key) => key + 1);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "重新分析失败");
    } finally {
      setBusyId("");
    }
  }

  async function dispatchPolicy(policy: Policy) {
    setBusyId(policy.id);
    try {
      await request(`/policies/${policy.id}/dispatch`, { method: "POST" });
      setNotice("政策已发布");
      setRefreshKey((key) => key + 1);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "发布失败");
    } finally {
      setBusyId("");
    }
  }

  const metrics = tabs.map((tab) => ({ ...tab, value: counts[tab.key] }));

  return (
    <div className="content">
      <div className="pagehead">
        <div>
          <div className="eyebrow">POLICY REPOSITORY</div>
          <h1>{role === "admin" ? "政策数据库" : "政策库"}</h1>
          <p className="sub">政策原文、AI 分析、人工审核和发布记录保持关联</p>
        </div>
        <div className="rowflex">
          {role === "admin" && <Link href="/documents?upload=1" className="btn primary">上传政策</Link>}
          {(role === "analyst" || role === "approver") && <Link href="/review" className="btn primary">前往审核工作台 →</Link>}
          {role === "publisher" && <Link href="/publications" className="btn primary">前往发布中心 →</Link>}
        </div>
      </div>

      <div className="grid4">
        {metrics.map((metric) => (
          <button className="metric" key={metric.key} onClick={() => { setActiveTab(metric.key); setSearch(""); }} style={{ textAlign: "left" }}>
            <small>{metric.label}</small><b>{metric.value}</b>
            <span>{metric.key === "high_priority" ? "P0 / P1 级别" : "点击筛选对应记录"}</span>
          </button>
        ))}
      </div>

      {notice && <div className="info" style={{ marginTop: 16 }}>{notice}</div>}
      {error && <div className="notice" style={{ marginTop: 16 }}>{error}<button className="link" onClick={() => setError("")} style={{ marginLeft: 12 }}>关闭</button></div>}

      <div className="panel full" style={{ marginTop: 18 }}>
        <div className="tabs">
          {tabs.map((tab) => (
            <button key={tab.key} className={`tab${activeTab === tab.key ? " active" : ""}`} onClick={() => { setActiveTab(tab.key); setSearch(""); }}>
              {tab.label} ({counts[tab.key]})
            </button>
          ))}
        </div>
        <div className="toolbar">
          <input className="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索政策名称、发文机构或摘要…" />
        </div>
        <div className="tablewrap">
          <table>
            <thead><tr><th>政策名称</th><th>来源</th><th>影响 Domain</th><th>审核状态</th><th>发布日期</th><th>发布时间</th><th>操作</th></tr></thead>
            <tbody>
              {loading ? <tr><td colSpan={7} style={{ textAlign: "center", padding: 40 }}>加载中…</td></tr> : policies.length === 0 ? (
                <tr><td colSpan={7} style={{ textAlign: "center", padding: 40, color: "#949aa3" }}>无匹配记录</td></tr>
              ) : policies.map((policy) => (
                <tr key={policy.id}>
                  <td style={{ minWidth: 260 }}>
                    <div className="policytitle"><Link href={`/policies/${policy.id}`}>{policy.title}</Link><small>{policy.doc_number || policy.id} · {policy.priority} · 影响评分 {impactScoreLabel(policy.score_total, 0, false)}</small></div>
                  </td>
                  <td>{policy.issuing_body || "—"}<br /><small>{JURISDICTION_LABELS[policy.jurisdiction] || policy.jurisdiction || "—"}</small></td>
                  <td><div className="rowflex">{policy.impacted_domains.length ? policy.impacted_domains.map((domain) => <span className="badge" key={domain}>{domain}</span>) : "—"}</div></td>
                  <td><span className={`badge ${policy.status === "published" || policy.status === "approved" ? "green" : policy.status.includes("review") ? "amber" : ""}`}>{POLICY_STATUS_LABELS[policy.status] || policy.status}</span><br /><small>审核：{dateLabel(policy.review_completed_at)}</small></td>
                  <td style={{ whiteSpace: "nowrap" }}>{dateLabel(policy.published_at)}</td>
                  <td style={{ whiteSpace: "nowrap" }}>{dateLabel(policy.dispatched_at)}</td>
                  <td>
                    <div className="rowflex">
                      <Link href={`/policies/${policy.id}`} className="link">详情</Link>
                      {role === "admin" && <button className="link" disabled={busyId === policy.id} onClick={() => analyzePolicy(policy)}>重新分析</button>}
                      {role === "publisher" && policy.status === "approved" && <button className="link" disabled={busyId === policy.id} onClick={() => dispatchPolicy(policy)}>发布</button>}
                      {role === "admin" && <button className="link" disabled={busyId === policy.id} onClick={() => setDeleteTarget(policy)} style={{ color: "var(--red)" }}>删除</button>}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {totalPages > 1 && <div style={{ display: "flex", justifyContent: "center", gap: 6, marginTop: 20, flexWrap: "wrap" }}>
        <button className="btn" disabled={currentPage === 1} onClick={() => setCurrentPage((page) => page - 1)}>← 上一页</button>
        {visiblePages[0] > 1 && <button className="btn" onClick={() => setCurrentPage(1)}>1</button>}
        {visiblePages.map((page) => <button key={page} className={`btn ${page === currentPage ? "primary" : ""}`} onClick={() => setCurrentPage(page)}>{page}</button>)}
        {visiblePages[visiblePages.length - 1] < totalPages && <button className="btn" onClick={() => setCurrentPage(totalPages)}>{totalPages}</button>}
        <button className="btn" disabled={currentPage === totalPages} onClick={() => setCurrentPage((page) => page + 1)}>下一页 →</button>
      </div>}
      <p className="footnote">第 {currentPage}/{totalPages} 页，共 {total.toLocaleString()} 条政策记录。</p>

      {deleteTarget && (
        <ConfirmDialog
          title="删除政策"
          confirmLabel="确认删除"
          busy={busyId === deleteTarget.id}
          onCancel={() => setDeleteTarget(null)}
          onConfirm={removePolicy}
          acknowledgeLabel={`我已确认删除「${deleteTarget.title}」及其分析、审核与预警记录`}
          description={<>
            <p>政策编号：{deleteTarget.id}（{deleteTarget.priority} · {POLICY_STATUS_LABELS[deleteTarget.status] || deleteTarget.status}）</p>
            <p>删除后这条政策的 AI 分析结论、审核任务、预警和图谱关联都会一并清除；原始文档保留在原文库，可重新分析。</p>
            <p>此操作不可撤销，删除记录会写入审计日志。</p>
          </>}
        />
      )}
    </div>
  );
}
