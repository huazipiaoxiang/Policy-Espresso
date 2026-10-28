"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import { API_BASE, demoApiHeaders } from "@/lib/auth";

interface Publication {
  id: string;
  document_id: string;
  title: string;
  issuing_body: string;
  priority: string;
  status: string;
  review_completed_at: string | null;
  dispatched_at: string | null;
}

type FilterKey = "today" | "pending" | "month" | "total";

const filterKeys: FilterKey[] = ["today", "pending", "month", "total"];

function dateLabel(value: string | null) {
  return value ? new Date(value).toLocaleString("zh-CN", { hour12: false }) : "—";
}

function hkDateKey(value: string | null) {
  return value ? new Date(value).toLocaleDateString("en-CA", { timeZone: "Asia/Hong_Kong" }) : "";
}

export default function PublicationsPage() {
  const { role } = useAuth();
  const searchParams = useSearchParams();
  const initialView = searchParams.get("view") as FilterKey | null;
  const [activeFilter, setActiveFilter] = useState<FilterKey>(initialView && filterKeys.includes(initialView) ? initialView : "pending");
  const [approved, setApproved] = useState<Publication[]>([]);
  const [published, setPublished] = useState<Publication[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busyId, setBusyId] = useState("");

  const fetchAll = useCallback(async (status: string) => {
    const all: Publication[] = [];
    let page = 1;
    while (true) {
      const response = await fetch(`${API_BASE}/policies?status=${status}&page=${page}&page_size=100`, { headers: demoApiHeaders() });
      const body = await response.json();
      if (!response.ok) throw new Error(body?.error?.message || "发布数据加载失败");
      all.push(...(body.items || []));
      if (all.length >= body.total || !body.items?.length) return all;
      page += 1;
    }
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [pendingItems, publishedItems] = await Promise.all([fetchAll("approved"), fetchAll("published")]);
      setApproved(pendingItems);
      setPublished(publishedItems);
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "发布数据加载失败");
    } finally {
      setLoading(false);
    }
  }, [fetchAll]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    const view = searchParams.get("view") as FilterKey | null;
    if (view && filterKeys.includes(view)) setActiveFilter(view);
  }, [searchParams]);

  const hkToday = hkDateKey(new Date().toISOString());
  const hkMonth = hkToday.slice(0, 7);
  const todayPublished = useMemo(
    () => published.filter((policy) => hkDateKey(policy.dispatched_at) === hkToday),
    [published, hkToday],
  );
  const monthPublished = useMemo(
    () => published.filter((policy) => hkDateKey(policy.dispatched_at).startsWith(hkMonth)),
    [published, hkMonth],
  );

  const rows = activeFilter === "pending" ? approved : activeFilter === "today" ? todayPublished : activeFilter === "month" ? monthPublished : published;
  const metrics = [
    { key: "today" as const, label: "今日已发布", value: todayPublished.length },
    { key: "pending" as const, label: "待发布", value: approved.length },
    { key: "month" as const, label: "本月新增", value: monthPublished.length },
    { key: "total" as const, label: "累计发布", value: published.length },
  ];

  async function publish(policy: Publication) {
    setBusyId(policy.id);
    setNotice("");
    try {
      const response = await fetch(`${API_BASE}/policies/${policy.id}/dispatch`, { method: "POST", headers: demoApiHeaders() });
      const body = await response.json();
      if (!response.ok) throw new Error(body?.error?.message || "发布失败");
      setNotice(`「${policy.title}」已发布`);
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "发布失败");
    } finally {
      setBusyId("");
    }
  }

  function exportCsv() {
    const escape = (value: string) => `"${value.replaceAll('"', '""')}"`;
    const lines = ["政策ID,标题,发文机构,优先级,审核通过时间,发布时间", ...rows.map((policy) => [
      policy.id, policy.title, policy.issuing_body, policy.priority,
      dateLabel(policy.review_completed_at), dateLabel(policy.dispatched_at),
    ].map(escape).join(","))];
    const url = URL.createObjectURL(new Blob(["\ufeff" + lines.join("\n")], { type: "text/csv;charset=utf-8" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `horizon-publications-${activeFilter}.csv`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  return (
    <main className="content">
      <div className="pagehead">
        <div><div className="eyebrow">PUBLICATIONS</div><h1>发布中心</h1><p className="sub">仅人工审核通过的政策可以发布，发布结果实时写回政策库</p></div>
        <button className="btn" onClick={exportCsv} disabled={!rows.length}>导出当前列表 CSV</button>
      </div>
      <div className="grid4">{metrics.map((metric) => <button className="metric" key={metric.key} onClick={() => setActiveFilter(metric.key)} style={{ textAlign: "left" }}><small>{metric.label}</small><b>{metric.value}</b><span>点击查看对应记录</span></button>)}</div>
      {notice && <div className="info" style={{ marginTop: 16 }}>{notice}</div>}
      {error && <div className="notice" style={{ marginTop: 16 }}>{error}</div>}
      <section className="panel" style={{ marginTop: 18 }}>
        <div className="panelhead"><h2>{metrics.find((metric) => metric.key === activeFilter)?.label}</h2><small>{rows.length} 条</small></div>
        <div className="tablewrap"><table><thead><tr><th>优先级</th><th>政策标题</th><th>{activeFilter === "pending" ? "审核通过时间" : "发布时间"}</th><th>状态</th><th>操作</th></tr></thead><tbody>
          {loading ? <tr><td colSpan={5} style={{ padding: 40, textAlign: "center" }}>加载中…</td></tr> : rows.length === 0 ? <tr><td colSpan={5} style={{ padding: 40, textAlign: "center", color: "#949aa3" }}>当前分类没有政策</td></tr> : rows.map((policy) => <tr key={policy.id}>
            <td><span className={`badge ${["P0", "P1"].includes(policy.priority) ? "red" : "amber"}`}>{policy.priority}</span></td>
            <td style={{ minWidth: 280 }}><div className="policytitle"><Link href={`/policies/${policy.id}`}>{policy.title}</Link><small>{policy.issuing_body || "—"}</small></div></td>
            <td>{dateLabel(activeFilter === "pending" ? policy.review_completed_at : policy.dispatched_at)}</td>
            <td><span className={`badge ${policy.status === "published" ? "green" : "amber"}`}>{policy.status === "published" ? "已发布" : "待发布"}</span></td>
            <td><div className="rowflex"><Link href={`/policies/${policy.id}`} className="link">详情</Link><Link href={`/documents/${policy.document_id}`} className="link">原文</Link>{role === "publisher" && policy.status === "approved" && <button className="btn primary" style={{ padding: "6px 12px" }} disabled={busyId === policy.id} onClick={() => publish(policy)}>{busyId === policy.id ? "发布中…" : "发布"}</button>}</div></td>
          </tr>)}
        </tbody></table></div>
      </section>
      <p className="footnote">发布权限仅属于发布者；其他运营角色可查看但不能执行发布。</p>
    </main>
  );
}
