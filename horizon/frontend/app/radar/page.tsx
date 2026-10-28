"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import { ReviewTaskItem } from "@/components/ReviewConsole";
import { API_BASE, demoApiHeaders } from "@/lib/auth";
import { RELEVANCE_LABELS } from "@/components/ScopeChip";
import { JURISDICTION_LABELS, POLICY_STATUS_LABELS, impactScoreLabel } from "@/lib/labels";

interface Policy {
  id: string;
  title: string;
  issuing_body: string;
  jurisdiction: string;
  target_entity_status: string;
  status: string;
  priority: string;
  score_total: number;
  dispatched_at: string | null;
}

export default function RadarPage() {
  const { role } = useAuth();
  const [counts, setCounts] = useState({ all: 0, pending: 0, highPriority: 0, todayPublished: 0, high: 0, medium: 0, low: 0, unscreened: 0 });
  const [recent, setRecent] = useState<Policy[]>([]);
  const [tasks, setTasks] = useState<ReviewTaskItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const get = useCallback(async (path: string) => {
    const response = await fetch(`${API_BASE}${path}`, { headers: demoApiHeaders() });
    const body = await response.json();
    if (!response.ok) throw new Error(body?.error?.message || "Dashboard 数据加载失败");
    return body;
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [all, pending, highPriority, high, medium, low, unscreened, recentData, taskData] = await Promise.all([
        get("/policies?page=1&page_size=1"), get("/policies?page=1&page_size=1&status=pending_review,in_review"),
        get("/policies?page=1&page_size=1&priority=P0,P1"), get("/policies?page=1&page_size=1&scope=high"),
        get("/policies?page=1&page_size=1&scope=medium"), get("/policies?page=1&page_size=1&scope=low"),
        get("/policies?page=1&page_size=1&scope=not_mentioned"), get("/policies?page=1&page_size=5"),
        get("/review-tasks"),
      ]);
      let todayPublished = 0;
      let page = 1;
      let fetched = 0;
      const hkToday = new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Hong_Kong" });
      do {
        const data = await get(`/policies?page=${page}&page_size=100&status=published`);
        const items = data.items || [];
        todayPublished += items.filter((policy: Policy) => policy.dispatched_at && new Date(policy.dispatched_at).toLocaleDateString("en-CA", { timeZone: "Asia/Hong_Kong" }) === hkToday).length;
        fetched += items.length;
        if (fetched >= data.total || !items.length) break;
        page += 1;
      } while (true);
      setCounts({ all: all.total, pending: pending.total, highPriority: highPriority.total, todayPublished, high: high.total, medium: medium.total, low: low.total, unscreened: unscreened.total });
      setRecent(recentData.items || []);
      setTasks((taskData.items || []).slice(0, 5));
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Dashboard 数据加载失败");
    } finally {
      setLoading(false);
    }
  }, [get]);

  useEffect(() => { load(); }, [load]);

  const metrics = [
    { label: "全部政策", value: counts.all, note: "与政策库全部记录一致", href: "/policies" },
    { label: "待审核", value: counts.pending, note: "等待一级或二级处理", href: "/policies?view=pending_review" },
    { label: "高优先级", value: counts.highPriority, note: "P0 / P1 政策", href: "/policies?view=high_priority" },
    { label: "今日已发布", value: counts.todayPublished, note: "按香港时区统计", href: "/publications?view=today" },
  ];
  const relevance = [
    { label: "高相关", value: counts.high, color: "green" }, { label: "中相关", value: counts.medium, color: "green" },
    { label: "低相关", value: counts.low, color: "" }, { label: "未提及 / 待筛选", value: counts.unscreened, color: "amber" },
  ];
  const maxRelevance = Math.max(1, ...relevance.map((item) => item.value));

  return (
    <main className="content">
      <div className="pagehead"><div><div className="eyebrow">DASHBOARD · 总览</div><h1>总览 Dashboard</h1><p className="sub">政策采集、相关性筛选、人工审核与发布的实时处理情况</p></div><button className="btn" onClick={load}>刷新数据</button></div>
      {error && <div className="notice" style={{ marginBottom: 16 }}>{error}</div>}
      <div className="grid4">{metrics.map((metric) => <Link href={metric.href} className="metric" key={metric.label} style={{ textDecoration: "none", color: "inherit" }}><small>{metric.label}</small><b>{metric.value}</b><span>{metric.note}</span></Link>)}</div>

      <div className="twocol" style={{ marginTop: 18 }}>
        <section className="panel"><div className="panelhead"><h2>{role === "publisher" ? "审核任务概览" : "我的审核任务"}</h2><small>{tasks.length} 条待办</small></div><div className="panelbody">
          {loading ? <p className="sub">加载中…</p> : tasks.length === 0 ? <p className="sub">当前没有待办审核任务</p> : tasks.map((task, index) => <div className="task" key={task.id}><div className="number">{String(index + 1).padStart(2, "0")}</div><div className="taskinfo"><strong>{task.policy_title}</strong><small>{task.level} 级审核 · {task.status} · {task.priority}</small></div><Link href={`/policies/${task.policy_id}`} className="link">查看 →</Link></div>)}
          <Link href="/review" className="btn" style={{ marginTop: 12 }}>进入审核工作台 →</Link>
        </div></section>
        <section className="panel"><div className="panelhead"><h2>相关性筛选概览</h2><small>真实政策记录</small></div><div className="panelbody">
          {relevance.map((item) => <div className="barrow" key={item.label}><span>{item.label}</span><div className="track"><div className={`fill ${item.color}`} style={{ width: `${item.value / maxRelevance * 100}%` }} /></div><strong>{item.value}</strong></div>)}
          <div className="divider" /><p className="sub">分类数量直接来自政策库的相关性字段，不使用演示数字。</p>
        </div></section>
      </div>

      <section className="panel full"><div className="panelhead"><h2>近期政策</h2><Link href="/policies" className="link">查看全部 →</Link></div><div className="tablewrap"><table><thead><tr><th>政策名称</th><th>发文机构 / 辖区</th><th>相关性</th><th>优先级</th><th>审核 / 发布状态</th></tr></thead><tbody>
        {recent.length === 0 ? <tr><td colSpan={5} style={{ textAlign: "center", padding: 32 }}>{loading ? "加载中…" : "暂无政策"}</td></tr> : recent.map((policy) => <tr key={policy.id}><td><div className="policytitle"><Link href={`/policies/${policy.id}`}>{policy.title}</Link><small>{policy.id}</small></div></td><td>{policy.issuing_body || "—"}<br /><small>{JURISDICTION_LABELS[policy.jurisdiction] || policy.jurisdiction || "—"}</small></td><td><span className="badge">{RELEVANCE_LABELS[policy.target_entity_status]?.text ?? policy.target_entity_status}</span></td><td>{policy.priority} · {impactScoreLabel(policy.score_total)}</td><td><span className={`badge ${policy.status === "published" ? "green" : "amber"}`}>{POLICY_STATUS_LABELS[policy.status] || policy.status}</span></td></tr>)}
      </tbody></table></div></section>
      <p className="footnote">Dashboard 指标、政策库和业务图谱均基于当前政策数据库实时计算。</p>
    </main>
  );
}
