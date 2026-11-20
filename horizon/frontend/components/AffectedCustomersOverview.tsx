"use client";

import { useCallback, useEffect, useState } from "react";
import { API_BASE, demoApiHeaders } from "@/lib/auth";

// 受影响客户概况（政策运营专员视角）：
// 由系统接入的跟进 Agent 动态分析生成结论；统计数据以客户库全量为口径，
// 与「发来影响报告的使用者名下是否有客户」无关，使用者没有客户时也能看到客户盘子。
// Agent 不可用时退回实时统计 + 本地归纳，界面不会出现「加载失败」。

interface CustomerRow {
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

interface LineBucket {
  business_line: string;
  customers: number;
  loan_balance_cny_yi: number;
}

interface SegmentBucket {
  segment: string;
  customers: number;
  loan_balance_cny_yi: number;
}

interface Stats {
  match_rule: string;
  total_customers: number;
  loan_balance_total_cny_yi: number;
  other_bank_loans_total_cny_yi: number;
  overseas_customers: number;
  by_business_line: LineBucket[];
  by_segment: SegmentBucket[];
  top_customers: CustomerRow[];
  customers: CustomerRow[];
  source: string;
}

interface AgentBrief {
  headline: string;
  summary: string;
  focus_points: string[];
  suggested_actions: string[];
  generated_by: "ai_agent" | "rules" | string;
  model: string;
  generated_at: string;
}

export default function AffectedCustomersOverview({ policyId }: { policyId: string }) {
  const [stats, setStats] = useState<Stats | null>(null);
  const [brief, setBrief] = useState<AgentBrief | null>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [notice, setNotice] = useState("");
  const [showAll, setShowAll] = useState(false);

  const load = useCallback(async () => {
    setGenerating(true);
    try {
      // 由跟进 Agent 现场分析：返回实时统计 + AI 概况结论
      const response = await fetch(`${API_BASE}/policies/${policyId}/affected-customers/analysis`, {
        method: "POST",
        headers: demoApiHeaders(),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body?.error?.message || "AI 分析暂不可用");
      setStats(body.stats);
      setBrief(body.brief);
      setNotice("");
    } catch {
      // 退回纯统计接口：仍然展示实时数据，并说明 AI 结论暂不可用
      try {
        const fallback = await fetch(`${API_BASE}/policies/${policyId}/affected-customers`, { headers: demoApiHeaders() });
        const fallbackBody = await fallback.json();
        if (!fallback.ok) throw new Error(fallbackBody?.error?.message || "统计接口不可用");
        setStats(fallbackBody);
        setBrief(null);
        setNotice("跟进 Agent 暂不可用，以下为实时统计数据，可直接用于跟进判断。");
      } catch {
        setStats(null);
        setBrief(null);
        setNotice("受影响客户统计暂不可用，请稍后点击「重新生成」重试。");
      }
    } finally {
      setLoading(false);
      setGenerating(false);
    }
  }, [policyId]);

  useEffect(() => { load(); }, [load]);

  const rows = stats ? (showAll ? stats.customers : stats.top_customers) : [];
  const maxLine = stats ? Math.max(1, ...stats.by_business_line.map((item) => item.loan_balance_cny_yi)) : 1;
  const generatedLabel = brief?.generated_by === "ai_agent" ? "AI Agent 生成" : "跟进 Agent 离线归纳";

  return (
    <section className="panel full">
      <div className="panelhead">
        <h2>受影响客户概况</h2>
        <div className="rowflex" style={{ alignItems: "center" }}>
          <small>客户库全量匹配 · Agent 动态分析</small>
          <button className="btn" type="button" disabled={generating} onClick={load}>
            {generating ? "分析中…" : "重新生成"}
          </button>
        </div>
      </div>
      <div className="sectionbody">
        {loading && <p className="textblock" style={{ color: "var(--muted)" }}>跟进 Agent 正在分析受影响客户…</p>}
        {notice && <p className="textblock" style={{ color: "var(--text-3)" }}>{notice}</p>}

        {brief && (
          <div className="agent-brief">
            <div className="agent-brief-head">
              <span className={`badge ${brief.generated_by === "ai_agent" ? "green" : ""}`}>
                {brief.generated_by === "ai_agent" ? "AI Agent" : "Agent 离线归纳"}
              </span>
              <strong>{brief.headline}</strong>
            </div>
            {brief.summary && <p className="textblock" style={{ margin: "8px 0 0" }}>{brief.summary}</p>}
            <div className="agent-brief-cols">
              <div>
                <small>重点关注</small>
                <ul>
                  {brief.focus_points.map((item, index) => <li key={index}>{item}</li>)}
                </ul>
              </div>
              <div>
                <small>建议跟进动作</small>
                <ul>
                  {brief.suggested_actions.map((item, index) => <li key={index}>{item}</li>)}
                </ul>
              </div>
            </div>
            <p className="agent-brief-meta">
              {generatedLabel} · 模型 {brief.model} · {brief.generated_at.replace("T", " ").slice(0, 19)} UTC
            </p>
          </div>
        )}

        {stats && (
          <>
            <p className="textblock" style={{ marginTop: brief ? 12 : 0 }}>
              口径：{stats.match_rule}。即使发来影响报告的政策使用者名下没有客户，也会按客户库全量统计受影响客户。
            </p>

            <div className="fieldgrid">
              <div className="field"><small>受影响客户合计</small><strong>{stats.total_customers} 户</strong></div>
              <div className="field"><small>本行贷款合计</small><strong>{stats.loan_balance_total_cny_yi} 亿元</strong></div>
              <div className="field"><small>他行贷款合计</small><strong>{stats.other_bank_loans_total_cny_yi} 亿元</strong></div>
              <div className="field"><small>含海外业务客户</small><strong>{stats.overseas_customers} 户</strong></div>
            </div>

            <div className="divider" />
            <small className="section-label">业务线分布（按贷款规模）</small>
            {stats.by_business_line.length === 0 ? (
              <p className="textblock">客户库中没有可匹配记录。</p>
            ) : (
              <div style={{ marginTop: 8 }}>
                {stats.by_business_line.map((item) => (
                  <div className="barrow" key={item.business_line}>
                    <span>{item.business_line || "未标注"}</span>
                    <div className="track"><div className="fill" style={{ width: `${item.loan_balance_cny_yi / maxLine * 100}%` }} /></div>
                    <strong>{item.customers} 户 · {item.loan_balance_cny_yi} 亿</strong>
                  </div>
                ))}
              </div>
            )}

            {stats.by_segment.length > 0 && (
              <>
                <div className="divider" />
                <small className="section-label">客群分布</small>
                <div className="rowflex" style={{ flexWrap: "wrap", gap: 8, marginTop: 8 }}>
                  {stats.by_segment.map((item) => (
                    <span className="tag" key={item.segment}>{item.segment} · {item.customers} 户 · {item.loan_balance_cny_yi} 亿</span>
                  ))}
                </div>
              </>
            )}

            <div className="divider" />
            <div className="rowflex" style={{ justifyContent: "space-between", alignItems: "center" }}>
              <small className="section-label" style={{ margin: 0 }}>
                {showAll ? `全部 ${stats.total_customers} 户客户` : `贷款规模前 ${stats.top_customers.length} 户客户`}
              </small>
              {stats.customers.length > stats.top_customers.length && (
                <button className="link" type="button" onClick={() => setShowAll((value) => !value)}>
                  {showAll ? "收起名单" : `展开全部 ${stats.total_customers} 户`}
                </button>
              )}
            </div>

            {rows.length === 0 ? (
              <p className="textblock">该政策暂未匹配到受影响客户。</p>
            ) : (
              <div className="tablewrap" style={{ marginTop: 8 }}>
                <table>
                  <thead><tr><th>客户</th><th>业务线</th><th>客群</th><th>贷款规模(亿)</th><th>他行贷款(亿)</th><th>海外业务</th><th>具体影响</th></tr></thead>
                  <tbody>
                    {rows.map((customer) => (
                      <tr key={customer.customer_id}>
                        <td>{customer.name_masked}</td>
                        <td>{customer.business_line}</td>
                        <td>{customer.segment || "—"}</td>
                        <td>{customer.loan_balance_cny_yi}</td>
                        <td>{customer.other_bank_loans_cny_yi}</td>
                        <td>{customer.overseas_business?.length ? customer.overseas_business.join("、") : "—"}</td>
                        <td style={{ minWidth: 240 }}>
                          <details>
                            <summary style={{ cursor: "pointer" }}>查看具体影响</summary>
                            <div style={{ marginTop: 6, fontSize: 12 }}>
                              <p>{customer.impact?.impact_content || "—"}</p>
                              <p>业务损失 <b>{customer.impact?.business_loss ?? 0}</b> · 业务机会 <b>{customer.impact?.business_opportunity ?? 0}</b> · 声誉风险 <b>{customer.impact?.reputation_risk ?? 0}</b></p>
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
            <p className="footnote" style={{ marginTop: 10 }}>数据来源：{stats.source}</p>
          </>
        )}
      </div>
    </section>
  );
}
