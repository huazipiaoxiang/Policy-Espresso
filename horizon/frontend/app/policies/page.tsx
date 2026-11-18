"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import ConfirmDialog from "@/components/ConfirmDialog";
import NoticeDialog from "@/components/NoticeDialog";
import { API_BASE, demoApiHeaders } from "@/lib/auth";
import { JURISDICTION_LABELS, POLICY_STATUS_LABELS, PRIORITY_LABELS, impactScoreLabel } from "@/lib/labels";

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
}

type TabKey = "all" | "today_new" | "pending_review" | "published" | "unpublished" | "high_priority" | "today_published";

const tabs: { key: TabKey; label: string }[] = [
  { key: "all", label: "全部政策" },
  { key: "today_new", label: "今日新增" },
  { key: "pending_review", label: "待审核" },
  { key: "published", label: "已发布" },
  { key: "unpublished", label: "未发布" },
  { key: "high_priority", label: "高优先级" },
  { key: "today_published", label: "今日已发布" },
];

function dateLabel(value: string | null) {
  return value ? value.slice(0, 10) : "—";
}

export default function PoliciesPage() {
  const { role } = useAuth();
  const searchParams = useSearchParams();
  const initialView = searchParams.get("view") as TabKey | null;
  // consumer 只看已发布政策；admin / processor 看全部 tab
  const isConsumer = role === "consumer";
  const visibleTabs = isConsumer ? tabs.filter((tab) => tab.key === "published") : tabs;
  const [activeTab, setActiveTab] = useState<TabKey>(isConsumer ? "published" : (visibleTabs.some((tab) => tab.key === initialView) ? initialView! : "all"));
  const [search, setSearch] = useState("");
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [noticeDialog, setNoticeDialog] = useState<string | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [counts, setCounts] = useState<Record<TabKey, number>>({ all: 0, today_new: 0, pending_review: 0, published: 0, unpublished: 0, high_priority: 0, today_published: 0 });
  const [refreshKey, setRefreshKey] = useState(0);
  const [busyId, setBusyId] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<Policy | null>(null);
  const pageSize = 20;
  const hkToday = useMemo(() => new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Hong_Kong" }), []);

  useEffect(() => {
    const view = searchParams.get("view") as TabKey | null;
    if (visibleTabs.some((tab) => tab.key === view)) setActiveTab(view!);
  }, [searchParams, visibleTabs]);

  useEffect(() => setCurrentPage(1), [activeTab, search]);

  const request = useCallback(async (path: string, init?: RequestInit) => {
    const response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { ...demoApiHeaders(), ...(init?.headers || {}) },
    });
    if (!response.ok) {
      const text = await response.text();
      let message = `请求失败（${response.status}）`;
      try {
        const body = JSON.parse(text);
        if (body?.error?.message) message = body.error.message;
        else if (typeof body?.detail === "string") message = body.detail;
        else if (body?.detail) message = JSON.stringify(body.detail);
      } catch {
        if (text && text.trim()) message = text;
      }
      throw new Error(message);
    }
    return response;
  }, []);

  useEffect(() => {
    const params = new URLSearchParams({ page: String(currentPage), page_size: String(pageSize) });
    if (activeTab === "today_new") params.set("fetched", "today");
    if (activeTab === "pending_review") {
      params.set("status", "pending_review,in_review");
    }
    if (activeTab === "published") params.set("status", "published");
    if (activeTab === "unpublished") params.set("status_not", "published");
    if (activeTab === "high_priority") params.set("priority", "P0,P1");
    if (activeTab === "today_published") { params.set("status", "published"); params.set("published_on", hkToday); }
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
  }, [activeTab, currentPage, refreshKey, request, search, hkToday, role]);

  useEffect(() => {
    const pendingFilter = "&status=pending_review,in_review";
    const urls: [TabKey, string][] = [
      ["all", ""], ["today_new", "&fetched=today"], ["pending_review", pendingFilter],
      ["published", "&status=published"], ["unpublished", "&status_not=published"],
      ["high_priority", "&priority=P0,P1"],
      ["today_published", `&status=published&published_on=${hkToday}`],
    ];
    Promise.all(urls.map(async ([key, filter]) => {
      const response = await request(`/policies?page=1&page_size=1${filter}`);
      return [key, (await response.json()).total || 0] as const;
    })).then((entries) => setCounts(Object.fromEntries(entries) as Record<TabKey, number>))
      .catch(() => undefined);
  }, [refreshKey, request, hkToday, role]);

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

  async function submitReview(policy: Policy) {
    setBusyId(policy.id);
    try {
      await request(`/policies/${policy.id}/submit-review`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ level: 1, note: "" }),
      });
      setNoticeDialog(`政策「${policy.title}」已提交人工审核`);
      setRefreshKey((key) => key + 1);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "提交审核失败");
    } finally {
      setBusyId("");
    }
  }

  const metrics = visibleTabs.filter((tab) => tab.key !== "today_published").map((tab) => ({ ...tab, value: counts[tab.key] }));

  return (
    <div className="content">
      <div className="pagehead">
        <div>
          <div className="eyebrow">POLICY REPOSITORY</div>
          <h1>{role === "admin" ? "政策数据库" : "政策库"}</h1>
          <p className="sub">{isConsumer ? "已发布政策的完整目录，可搜索查看" : "政策原文、AI 分析、人工审核和发布记录保持关联"}</p>
        </div>
        <div className="rowflex">
          {role === "admin" && <Link href="/documents?upload=1" className="btn primary">上传政策</Link>}
          {role === "processor" && <button className="btn primary" onClick={() => { setActiveTab("pending_review"); setSearch(""); }}>前往待审核政策 →</button>}
          {role === "processor" && <Link href="/publications" className="btn primary">前往发布中心 →</Link>}
        </div>
      </div>

      {!isConsumer && (
        <div className="grid4">
          {metrics.map((metric) => (
            <button className="metric" key={metric.key} onClick={() => { setActiveTab(metric.key); setSearch(""); }} style={{ textAlign: "left" }}>
              <small>{metric.label}</small><b>{metric.value}</b>
              <span>{metric.key === "high_priority" ? "P0 / P1 级别" : "点击筛选对应记录"}</span>
            </button>
          ))}
        </div>
      )}

      {notice && <div className="info" style={{ marginTop: 16 }}>{notice}</div>}
      {error && <div className="notice" style={{ marginTop: 16 }}>{error}<button className="link" onClick={() => setError("")} style={{ marginLeft: 12 }}>关闭</button></div>}

      <div className="panel full" style={{ marginTop: 18 }}>
        {!isConsumer && (
          <div className="tabs">
            {visibleTabs.map((tab) => (
              <button key={tab.key} className={`tab${activeTab === tab.key ? " active" : ""}`} onClick={() => { setActiveTab(tab.key); setSearch(""); }}>
                {tab.label} ({counts[tab.key]})
              </button>
            ))}
          </div>
        )}
        <div className="toolbar">
          <input className="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索政策名称、发文机构或摘要…" />
        </div>
        <div className="tablewrap">
          <table>
            <thead><tr><th>政策名称</th><th>来源</th><th>优先级</th><th>影响 Domain</th><th>审核状态</th><th>发布日期</th><th>操作</th></tr></thead>
            <tbody>
              {loading ? <tr><td colSpan={7} style={{ textAlign: "center", padding: 40 }}>加载中…</td></tr> : policies.length === 0 ? (
                <tr><td colSpan={7} style={{ textAlign: "center", padding: 40, color: "#949aa3" }}>无匹配记录</td></tr>
              ) : policies.map((policy) => (
                <tr key={policy.id}>
                  <td style={{ minWidth: 260 }}>
                    <div className="policytitle"><Link href={`/policies/${policy.id}`}>{policy.title}</Link><small>{policy.doc_number || policy.id} · {policy.priority} · 影响评分 {impactScoreLabel(policy.score_total, 0, false)}</small></div>
                  </td>
                  <td>{policy.issuing_body || "—"}<br /><small>{JURISDICTION_LABELS[policy.jurisdiction] || policy.jurisdiction || "—"}</small></td>
                  <td><span className="pdot" title={PRIORITY_LABELS[policy.priority] || policy.priority || ""}><i className={(policy.priority || "p3").toLowerCase()} />{policy.priority || "—"}</span></td>
                  <td><div className="rowflex">{policy.impacted_domains.length ? policy.impacted_domains.map((domain) => <span className="badge" key={domain}>{domain}</span>) : "—"}</div></td>
                  <td><span className={`badge ${policy.status === "published" || policy.status === "approved" ? "green" : policy.status.includes("review") ? "amber" : ""}`}>{POLICY_STATUS_LABELS[policy.status] || policy.status}</span></td>
                  <td style={{ whiteSpace: "nowrap" }}>{dateLabel(policy.published_at)}</td>
                  <td>
                    <div className="rowflex">
                      <Link href={`/policies/${policy.id}`} className="link">{isConsumer ? "查看" : "审核"}</Link>
                      {role === "admin" && <button className="link" disabled={busyId === policy.id} onClick={() => analyzePolicy(policy)}>重新分析</button>}
                      {(role === "admin" || role === "processor") && policy.status === "ai_checked" && <button className="link" disabled={busyId === policy.id} onClick={() => submitReview(policy)}>提交审核</button>}
                      {role === "processor" && policy.status === "approved" && <button className="link" disabled={busyId === policy.id} onClick={() => dispatchPolicy(policy)}>发布</button>}
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
      {noticeDialog && <NoticeDialog message={noticeDialog} onClose={() => setNoticeDialog(null)} />}
    </div>
  );
}
