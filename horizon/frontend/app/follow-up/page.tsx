"use client";

import Link from "next/link";
import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import { API_BASE, demoApiHeaders } from "@/lib/auth";

// 政策跟进中心：合并原「总览 Dashboard」与「发布中心」。
// 核心是政策使用者发来的影响报告（含政策影响到的全部客户），下方跟进已跟进政策与 AI 自动发布记录。

interface AffectedCustomer {
  customer_id: string;
  name_masked: string;
  business_line: string;
  segment?: string;
  loan_balance_cny_yi: number;
  other_bank_loans_cny_yi: number;
  overseas_business?: string[];
  impact?: {
    impact_content?: string;
    business_loss?: number;
    business_opportunity?: number;
    reputation_risk?: number;
    outcome?: string;
  };
}

interface ConsumerReport {
  id: string;
  policy_id: string;
  policy_title: string;
  policy_priority?: string;
  actor: string;
  report: {
    impact_overview?: string;
    benefit_loss?: string;
    dimensions?: Record<string, number>;
    affected_customers?: { customer_id: string; name_masked: string; business_line: string }[];
  };
  status: string;
  created_at: string;
  affected_customers?: AffectedCustomer[];
  affected_customer_count?: number;
  affected_scope_note?: string;
}

interface Publication {
  id: string;
  document_id: string;
  title: string;
  issuing_body: string;
  jurisdiction: string;
  priority: string;
  status: string;
  published_at: string | null;
  dispatched_at: string | null;
}

interface FlaggedPolicy {
  id: string;
  title: string;
  issuing_body: string;
  jurisdiction: string;
  priority: string;
  published_at: string | null;
  irrelevant_flagged?: boolean;
}

type ReportFilter = "all" | "pending" | "processed";
type PublishRange = "today" | "month" | "total";

const REPORT_FILTERS: { key: ReportFilter; label: string }[] = [
  { key: "all", label: "全部报告" },
  { key: "pending", label: "待跟进" },
  { key: "processed", label: "已跟进" },
];

const PUBLISH_RANGES: { key: PublishRange; label: string }[] = [
  { key: "today", label: "今日" },
  { key: "month", label: "本月" },
  { key: "total", label: "累计" },
];

interface AgentBrief {
  headline: string;
  summary: string;
  focus_points: string[];
  suggested_actions: string[];
  generated_by: string;
  model: string;
  generated_at: string;
}

function dateLabel(value: string | null | undefined) {
  return value ? value.slice(0, 10) : "—";
}

function dateKey(value: string | null) {
  // dispatched_at 是 UTC ISO 串，换算到香港时区再取日期，避免跨日/跨月统计错位
  if (!value) return "";
  return new Date(value).toLocaleDateString("en-CA", { timeZone: "Asia/Hong_Kong" });
}

export default function FollowUpPage() {
  const [reports, setReports] = useState<ConsumerReport[]>([]);
  const [published, setPublished] = useState<Publication[]>([]);
  const [flagged, setFlagged] = useState<FlaggedPolicy[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busyId, setBusyId] = useState("");
  const [reportFilter, setReportFilter] = useState<ReportFilter>("all");
  const [expandedReport, setExpandedReport] = useState<string | null>(null);
  const [publishRange, setPublishRange] = useState<PublishRange>("total");
  // 展开报告时由跟进 Agent 现场分析受影响客户，结论按政策缓存
  const [briefs, setBriefs] = useState<Record<string, AgentBrief>>({});
  const [briefLoading, setBriefLoading] = useState("");

  const loadBrief = useCallback(async (policyId: string) => {
    if (briefs[policyId] || briefLoading === policyId) return;
    setBriefLoading(policyId);
    try {
      const response = await fetch(`${API_BASE}/policies/${policyId}/affected-customers/analysis`, {
        method: "POST",
        headers: demoApiHeaders(),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body?.error?.message || "Agent 分析暂不可用");
      setBriefs((current) => ({ ...current, [policyId]: body.brief }));
    } catch {
      // Agent 不可用时不阻塞：继续展示报告中的客户名单
    } finally {
      setBriefLoading("");
    }
  }, [briefs, briefLoading]);

  const fetchPublished = useCallback(async () => {
    const all: Publication[] = [];
    let page = 1;
    while (true) {
      const response = await fetch(`${API_BASE}/policies?status=published&page=${page}&page_size=100`, { headers: demoApiHeaders() });
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
      const [reportsResp, publishedItems, flaggedResp] = await Promise.all([
        fetch(`${API_BASE}/consumer-reports`, { headers: demoApiHeaders() }),
        fetchPublished(),
        fetch(`${API_BASE}/policies?irrelevant=true&page=1&page_size=100`, { headers: demoApiHeaders() }),
      ]);
      if (reportsResp.ok) {
        const body = await reportsResp.json();
        setReports(body.items || []);
      }
      setPublished(publishedItems);
      if (flaggedResp.ok) {
        const body = await flaggedResp.json();
        setFlagged(body.items || []);
      }
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "政策跟进数据加载失败");
    } finally {
      setLoading(false);
    }
  }, [fetchPublished]);

  useEffect(() => { load(); }, [load]);

  async function markProcessed(report: ConsumerReport) {
    setBusyId(report.id);
    setNotice("");
    try {
      const response = await fetch(`${API_BASE}/consumer-reports/${report.id}/process`, {
        method: "POST",
        headers: demoApiHeaders(),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body?.error?.message || "标记失败");
      setNotice(`「${report.policy_title || report.policy_id}」的影响报告已标记为已跟进`);
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "标记失败");
    } finally {
      setBusyId("");
    }
  }

  async function decideFlagged(policy: FlaggedPolicy, action: "keep" | "delete") {
    setBusyId(policy.id);
    setNotice("");
    try {
      const response = await fetch(`${API_BASE}/policies/${policy.id}/followup-decide`, {
        method: "POST",
        headers: { ...demoApiHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify({ action }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body?.error?.message || "操作失败");
      setNotice(action === "keep"
        ? `「${policy.title}」已标记为永久保留`
        : `「${policy.title}」已删除`);
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "操作失败");
    } finally {
      setBusyId("");
    }
  }

  const hkToday = new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Hong_Kong" });
  const hkMonth = hkToday.slice(0, 7);

  const pendingReports = useMemo(() => reports.filter((report) => report.status !== "processed"), [reports]);

  // 已跟进的政策：按政策聚合已跟进的影响报告
  const followedPolicies = useMemo(() => {
    const map = new Map<string, { policyId: string; title: string; reports: number; customerIds: Set<string>; lastAt: string }>();
    for (const report of reports) {
      if (report.status !== "processed") continue;
      const entry = map.get(report.policy_id) || {
        policyId: report.policy_id,
        title: report.policy_title || report.policy_id,
        reports: 0,
        customerIds: new Set<string>(),
        lastAt: report.created_at,
      };
      entry.reports += 1;
      for (const customer of report.affected_customers || []) entry.customerIds.add(customer.customer_id);
      if (report.created_at > entry.lastAt) entry.lastAt = report.created_at;
      map.set(report.policy_id, entry);
    }
    return [...map.values()].sort((a, b) => (a.lastAt < b.lastAt ? 1 : a.lastAt > b.lastAt ? -1 : 0));
  }, [reports]);

  const visibleReports = reportFilter === "all"
    ? reports
    : reports.filter((report) => (reportFilter === "processed" ? report.status === "processed" : report.status !== "processed"));

  const publishedRows = useMemo(() => {
    if (publishRange === "today") return published.filter((policy) => dateKey(policy.dispatched_at) === hkToday);
    if (publishRange === "month") return published.filter((policy) => dateKey(policy.dispatched_at).startsWith(hkMonth));
    return published;
  }, [published, publishRange, hkToday, hkMonth]);

  const todayPublished = useMemo(
    () => published.filter((policy) => dateKey(policy.dispatched_at) === hkToday),
    [published, hkToday],
  );

  const metrics = [
    { label: "影响报告", value: reports.length, note: "政策使用者发来的影响报告" },
    { label: "待跟进", value: pendingReports.length, note: "尚未标记跟进的影响报告" },
    { label: "已跟进政策", value: followedPolicies.length, note: "已完成跟进的 AI 发布政策" },
    { label: "今日 AI 发布", value: todayPublished.length, note: "按 AI 发布时间统计" },
  ];

  function exportCsv() {
    const escape = (value: string) => `"${value.replaceAll('"', '""')}"`;
    const lines = ["政策ID,标题,发文机构,优先级,发布时间", ...publishedRows.map((policy) => [
      policy.id, policy.title, policy.issuing_body, policy.priority,
      dateLabel(policy.dispatched_at || policy.published_at),
    ].map(escape).join(","))];
    const url = URL.createObjectURL(new Blob(["\ufeff" + lines.join("\n")], { type: "text/csv;charset=utf-8" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `horizon-follow-up-${publishRange}.csv`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  return (
    <main className="content">
      <div className="pagehead">
        <div>
          <div className="eyebrow">POLICY FOLLOW-UP</div>
          <h1>政策跟进中心</h1>
          <p className="sub">以政策使用者发来的影响报告为核心，跟踪 AI 已发布政策的影响与跟进进展</p>
        </div>
        <button className="btn" onClick={load}>刷新数据</button>
      </div>

      <div className="grid4">
        {metrics.map((metric) => (
          <div className="metric" key={metric.label} style={{ textAlign: "left" }}>
            <small>{metric.label}</small><b>{metric.value}</b><span>{metric.note}</span>
          </div>
        ))}
      </div>

      {notice && <div className="info" style={{ marginTop: 16 }}>{notice}</div>}
      {error && <div className="notice" style={{ marginTop: 16 }}>{error}<button className="link" onClick={() => setError("")} style={{ marginLeft: 12 }}>关闭</button></div>}

      {/* 核心模块：政策使用者发来的影响报告 */}
      <section className="panel full" style={{ marginTop: 18 }}>
        <div className="panelhead">
          <h2>政策使用者发来的影响报告</h2>
          <small>{visibleReports.length} 条 · 展开可查看该政策影响到的全部客户</small>
        </div>
        <div className="tabs">
          {REPORT_FILTERS.map((filter) => {
            const count = filter.key === "all" ? reports.length : filter.key === "pending" ? pendingReports.length : reports.length - pendingReports.length;
            return (
              <button key={filter.key} className={`tab${reportFilter === filter.key ? " active" : ""}`} onClick={() => setReportFilter(filter.key)}>
                {filter.label} ({count})
              </button>
            );
          })}
        </div>
        <div className="tablewrap">
          <table>
            <thead>
              <tr><th>政策</th><th>发送人</th><th>影响概述</th><th>受影响客户</th><th>跟进状态</th><th>操作</th></tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={6} style={{ padding: 40, textAlign: "center" }}>加载中…</td></tr>
              ) : visibleReports.length === 0 ? (
                <tr><td colSpan={6} style={{ padding: 40, textAlign: "center", color: "#949aa3" }}>
                  {reportFilter === "all" ? "暂无政策使用者发来的影响报告。" : "当前分类没有影响报告。"}
                </td></tr>
              ) : visibleReports.map((report) => {
                const customers = report.affected_customers ?? [];
                const expanded = expandedReport === report.id;
                const processed = report.status === "processed";
                return (
                  <Fragment key={report.id}>
                    <tr>
                      <td style={{ minWidth: 220 }}>
                        <div className="policytitle">
                          <Link href={`/policies/${report.policy_id}`}>{report.policy_title || report.policy_id}</Link>
                          <small>{report.policy_priority || "—"} · 报告时间 {dateLabel(report.created_at)}</small>
                        </div>
                      </td>
                      <td>{report.actor === "consumer" ? "政策使用者" : report.actor}</td>
                      <td style={{ maxWidth: 320 }}><span style={{ fontSize: 12 }}>{report.report?.impact_overview || "—"}</span></td>
                      <td style={{ whiteSpace: "nowrap" }}>
                        <button
                          className="link"
                          type="button"
                          onClick={() => {
                            const next = expanded ? null : report.id;
                            setExpandedReport(next);
                            if (next) void loadBrief(report.policy_id);
                          }}
                        >
                          {customers.length} 户 {expanded ? "收起 ▲" : "展开 ▼"}
                        </button>
                      </td>
                      <td><span className={`badge ${processed ? "green" : "amber"}`}>{processed ? "已跟进" : "待跟进"}</span></td>
                      <td>
                        <div className="rowflex">
                          <Link href={`/policies/${report.policy_id}`} className="link">政策解读 →</Link>
                          {!processed && (
                            <button className="btn primary" style={{ padding: "6px 12px" }} disabled={busyId === report.id} onClick={() => markProcessed(report)}>
                              {busyId === report.id ? "处理中…" : "标记已跟进"}
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                    {expanded && (
                      <tr>
                        <td colSpan={6} style={{ background: "var(--surface-2)" }}>
                          {briefLoading === report.policy_id ? (
                            <p className="textblock" style={{ margin: "0 0 8px", color: "var(--text-3)" }}>
                              跟进 Agent 正在分析该政策影响到的客户…
                            </p>
                          ) : briefs[report.policy_id] ? (
                            <div className="agent-brief" style={{ marginBottom: 10 }}>
                              <div className="agent-brief-head">
                                <span className={`badge ${briefs[report.policy_id].generated_by === "ai_agent" ? "green" : ""}`}>
                                  {briefs[report.policy_id].generated_by === "ai_agent" ? "AI Agent" : "Agent 离线归纳"}
                                </span>
                                <strong>{briefs[report.policy_id].headline}</strong>
                              </div>
                              <p className="textblock" style={{ margin: "8px 0 0" }}>{briefs[report.policy_id].summary}</p>
                              <div className="agent-brief-cols">
                                <div>
                                  <small>重点关注</small>
                                  <ul>
                                    {briefs[report.policy_id].focus_points.slice(0, 3).map((item, index) => <li key={index}>{item}</li>)}
                                  </ul>
                                </div>
                                <div>
                                  <small>建议跟进动作</small>
                                  <ul>
                                    {briefs[report.policy_id].suggested_actions.slice(0, 3).map((item, index) => <li key={index}>{item}</li>)}
                                  </ul>
                                </div>
                              </div>
                            </div>
                          ) : null}
                          <p style={{ fontSize: 12, color: "var(--text-3)", margin: "0 0 8px" }}>
                            影响范围口径：{report.affected_scope_note || "按政策业务线匹配"} · 共 {customers.length} 户 · 数据来源：合成客户数据集（非真实客户）
                          </p>
                          {customers.length === 0 ? (
                            <p className="textblock" style={{ margin: 0 }}>该政策暂未匹配到受影响客户，可到政策解读页查看客户库整体影响概况。</p>
                          ) : (
                            <div className="tablewrap">
                              <table>
                                <thead><tr><th>客户</th><th>业务线</th><th>客群</th><th>贷款规模(亿)</th><th>他行贷款(亿)</th><th>海外业务</th><th>具体影响</th></tr></thead>
                                <tbody>
                                  {customers.map((customer) => (
                                    <tr key={customer.customer_id}>
                                      <td>{customer.name_masked}</td>
                                      <td>{customer.business_line}</td>
                                      <td>{customer.segment || "—"}</td>
                                      <td>{customer.loan_balance_cny_yi}</td>
                                      <td>{customer.other_bank_loans_cny_yi}</td>
                                      <td>{customer.overseas_business?.length ? customer.overseas_business.join("、") : "—"}</td>
                                      <td style={{ minWidth: 260 }}>
                                        <details>
                                          <summary style={{ cursor: "pointer" }}>查看具体影响</summary>
                                          <div style={{ marginTop: 6, fontSize: 12 }}>
                                            <p>{customer.impact?.impact_content || "—"}</p>
                                            <p>{customer.impact?.outcome || ""}</p>
                                          </div>
                                        </details>
                                      </td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          )}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      {/* AI 判定疑似完全无影响，待跟进专员复核 */}
      <section className="panel full" style={{ marginTop: 18 }}>
        <div className="panelhead">
          <h2>被标记跟进的政策</h2>
          <small>{flagged.length} 条 · AI 判定对汇丰完全无影响，请决定保留或删除</small>
        </div>
        <div className="tablewrap">
          <table>
            <thead><tr><th>政策</th><th>来源</th><th>优先级</th><th>发布日期</th><th>操作</th></tr></thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={5} style={{ padding: 40, textAlign: "center" }}>加载中…</td></tr>
              ) : flagged.length === 0 ? (
                <tr><td colSpan={5} style={{ padding: 40, textAlign: "center", color: "#949aa3" }}>暂无待复核的无关政策。</td></tr>
              ) : flagged.map((policy) => (
                <tr key={policy.id}>
                  <td style={{ minWidth: 260 }}><div className="policytitle"><Link href={`/policies/${policy.id}`}>{policy.title}</Link><small>{policy.id}</small></div></td>
                  <td>{policy.issuing_body || "—"}</td>
                  <td><span className={`badge ${["P0", "P1"].includes(policy.priority) ? "red" : "amber"}`}>{policy.priority}</span></td>
                  <td style={{ whiteSpace: "nowrap" }}>{dateLabel(policy.published_at)}</td>
                  <td>
                    <div className="rowflex">
                      <button className="btn primary" disabled={busyId === policy.id} onClick={() => decideFlagged(policy, "keep")}>保留</button>
                      <button className="btn danger" disabled={busyId === policy.id} onClick={() => decideFlagged(policy, "delete")}>删除</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* 已跟进的政策 */}
      <section className="panel full" style={{ marginTop: 18 }}>
        <div className="panelhead">
          <h2>已跟进的政策</h2>
          <small>{followedPolicies.length} 条</small>
        </div>
        <div className="tablewrap">
          <table>
            <thead><tr><th>政策</th><th>影响报告</th><th>受影响客户</th><th>最近跟进</th><th>操作</th></tr></thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={5} style={{ padding: 40, textAlign: "center" }}>加载中…</td></tr>
              ) : followedPolicies.length === 0 ? (
                <tr><td colSpan={5} style={{ padding: 40, textAlign: "center", color: "#949aa3" }}>
                  暂无已跟进的政策，先在上方影响报告中点击「标记已跟进」。
                </td></tr>
              ) : followedPolicies.map((policy) => (
                <tr key={policy.policyId}>
                  <td style={{ minWidth: 260 }}><div className="policytitle"><Link href={`/policies/${policy.policyId}`}>{policy.title}</Link><small>{policy.policyId}</small></div></td>
                  <td>{policy.reports} 份</td>
                  <td>{policy.customerIds.size} 户</td>
                  <td>{dateLabel(policy.lastAt)}</td>
                  <td><div className="rowflex"><Link href={`/policies/${policy.policyId}`} className="link">政策解读 →</Link><Link href={`/audit?object_type=policy&object_id=${policy.policyId}`} className="link">审计</Link></div></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* AI 自动发布记录（原发布中心内容） */}
      <section className="panel full" style={{ marginTop: 18 }}>
        <div className="panelhead">
          <h2>AI 自动发布记录</h2>
          <div className="rowflex" style={{ alignItems: "center" }}>
            <small>政策抓取、分析与发布均由 AI 自动完成</small>
            <button className="btn" onClick={exportCsv} disabled={!publishedRows.length}>导出 CSV</button>
          </div>
        </div>
        <div className="tabs">
          {PUBLISH_RANGES.map((range) => (
            <button key={range.key} className={`tab${publishRange === range.key ? " active" : ""}`} onClick={() => setPublishRange(range.key)}>
              {range.label} ({range.key === "today" ? todayPublished.length : range.key === "month" ? published.filter((policy) => dateKey(policy.dispatched_at).startsWith(hkMonth)).length : published.length})
            </button>
          ))}
        </div>
        <div className="tablewrap">
          <table>
            <thead><tr><th>优先级</th><th>政策标题</th><th>发布时间</th><th>状态</th><th>操作</th></tr></thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={5} style={{ padding: 40, textAlign: "center" }}>加载中…</td></tr>
              ) : publishedRows.length === 0 ? (
                <tr><td colSpan={5} style={{ padding: 40, textAlign: "center", color: "#949aa3" }}>当前分类没有政策</td></tr>
              ) : publishedRows.slice(0, 30).map((policy) => (
                <tr key={policy.id}>
                  <td><span className={`badge ${["P0", "P1"].includes(policy.priority) ? "red" : "amber"}`}>{policy.priority}</span></td>
                  <td style={{ minWidth: 280 }}><div className="policytitle"><Link href={`/policies/${policy.id}`}>{policy.title}</Link><small>{policy.issuing_body || "—"}</small></div></td>
                  <td>{dateLabel(policy.dispatched_at || policy.published_at)}</td>
                  <td><span className="badge green">已发布</span></td>
                  <td><div className="rowflex"><Link href={`/policies/${policy.id}`} className="link">详情</Link><Link href={`/documents/${policy.document_id}`} className="link">原文</Link><Link href={`/audit?object_type=policy&object_id=${policy.id}`} className="link">审计</Link></div></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {publishedRows.length > 30 && (
          <p className="footnote">仅展示最近 30 条，共 {publishedRows.length} 条；可导出 CSV 查看完整列表。</p>
        )}
      </section>

      <p className="footnote">政策抓取、分析与发布均由 AI 自动完成；运营专员在此跟进使用者反馈，并查看影响到的全部客户。</p>
    </main>
  );
}
