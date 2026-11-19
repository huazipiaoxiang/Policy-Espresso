"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import { RELEVANCE_LABELS } from "@/components/ScopeChip";
import ReviewPanel from "@/components/ReviewPanel";
import AgentTrace from "@/components/AgentTrace";
import NoticeDialog from "@/components/NoticeDialog";
import { DIRECTION_LABELS, JURISDICTION_LABELS, POLICY_STATUS_LABELS, analysisModelLabel } from "@/lib/labels";
import { API_BASE, demoApiHeaders } from "@/lib/auth";

interface ExposureRange {
  low: number;
  high: number;
  currency: string;
  unit: string;
  basis: string;
  confidence: number;
}

interface Assessment {
  id: string;
  scores: Record<string, { score: number | null; reason: string; evidence_ids: string[] }>;
  direction: string;
  score_total: number;
  priority: string;
  transmission_chain: string[];
  affected: { business_lines?: string[]; segments?: string[]; exposure_range?: ExposureRange | null };
  recommended_actions: (string | { action: string; owner?: string; deadline?: string })[];
  case_links: { case_id: string; similarity: number; takeaway: string }[];
  confidence: number;
  model: string;
}

interface PolicyDetail {
  id: string;
  document_id: string;
  title: string;
  issuing_body: string;
  doc_number: string | null;
  published_at: string | null;
  effective_at: string | null;
  expiry_at: string | null;
  jurisdiction: string;
  policy_type: string;
  themes: string[];
  applicable_entities_text: string;
  target_entity_status: string;
  status: string;
  priority: string;
  score_total: number;
  confidence: number;
  summary_zh: string;
  impacted_domains: string[];
  url: string;
  assessments: Assessment[];
  evidence: { id: string; quote: string; field_name: string; span_start: number; span_end: number }[];
  scope_judgements: { entity_id: string; result: string; llm_reason: string; conflict: boolean }[];
  review_tasks: {
    id: string; level: number; assignee: string; status: string; created_at: string;
    decisions: { actor: string; action: string; reason_code: string | null; note: string; created_at: string }[];
  }[];
  document: { id: string; title: string; url: string; content_text: string; published_at: string | null } | null;
}

const entityLabels: Record<string, string> = {
  hsbc_hk: "香港上海汇丰银行有限公司（香港注册认可机构）",
  hsbc_cn: "汇丰银行（中国）有限公司（内地外商独资法人银行）",
};

function dateLabel(value: string | null) {
  return value ? value.slice(0, 10) : "—";
}

export default function PolicyDetailPage() {
  const params = useParams<{ id: string }>();
  const { role } = useAuth();
  const [policy, setPolicy] = useState<PolicyDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [noticeDialog, setNoticeDialog] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showFeedback, setShowFeedback] = useState(false);
  const [feedbackText, setFeedbackText] = useState("");
  const [consumerView, setConsumerView] = useState<any>(null);
  const [activeTopic, setActiveTopic] = useState<string | null>(null);
  // 三栏解读懒加载：点击重点话题时才请求，避免详情页因联网检索卡在 loading
  const [topicColumns, setTopicColumns] = useState<Record<string, any>>({});
  const [topicLoading, setTopicLoading] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetch(`${API_BASE}/policies/${params.id}`, { headers: demoApiHeaders() });
      const data = await response.json();
      if (!response.ok) throw new Error(data?.error?.message || "政策加载失败");
      setPolicy(data);
      setError("");
      if (role === "consumer") {
        const cvResp = await fetch(`${API_BASE}/policies/${params.id}/consumer-view`, { headers: demoApiHeaders() });
        if (cvResp.ok) setConsumerView(await cvResp.json());
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "政策加载失败");
    } finally {
      setLoading(false);
    }
  }, [params.id, role]);

  useEffect(() => { load(); }, [load]);

  async function operation(path: string, success: string, body?: Record<string, unknown>, dialogMessage?: string) {
    setBusy(true);
    try {
      const response = await fetch(`${API_BASE}${path}`, {
        method: "POST",
        headers: body ? { ...demoApiHeaders(), "Content-Type": "application/json" } : demoApiHeaders(),
        body: body ? JSON.stringify(body) : undefined,
      });
      if (!response.ok) {
        const text = await response.text();
        let message = "操作失败";
        try {
          const data = JSON.parse(text);
          if (data?.error?.message) message = data.error.message;
          else if (typeof data?.detail === "string") message = data.detail;
        } catch {
          if (text && text.trim()) message = text;
        }
        throw new Error(message);
      }
      await load();
      if (dialogMessage) {
        setNoticeDialog(dialogMessage);
      } else {
        setNotice(success);
      }
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "操作失败");
    } finally {
      setBusy(false);
    }
  }

  async function submitFeedback() {
    if (!feedbackText.trim()) return;
    setBusy(true);
    try {
      const response = await fetch(`${API_BASE}/policies/${policy?.id}/feedback`, {
        method: "POST",
        headers: { ...demoApiHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify({ content: feedbackText }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data?.error?.message || "反馈提交失败");
      setShowFeedback(false);
      setFeedbackText("");
      setNotice("反馈已提交，已送达审核员");
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "反馈提交失败");
    } finally {
      setBusy(false);
    }
  }

  async function sendConsumerReport() {
    setBusy(true);
    try {
      const response = await fetch(`${API_BASE}/policies/${policy?.id}/consumer-view/send-review`, {
        method: "POST",
        headers: demoApiHeaders(),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data?.error?.message || "发送失败");
      setNoticeDialog(`影响报告已发送给政策加工者 review，可到发布中心继续研究。`);
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "发送失败");
    } finally {
      setBusy(false);
    }
  }

  async function loadTopicColumns(topic: string) {
    if (topicColumns[topic] || topicLoading === topic) return;
    setTopicLoading(topic);
    try {
      const resp = await fetch(`${API_BASE}/policies/${policy?.id}/topic/${encodeURIComponent(topic)}`, {
        headers: demoApiHeaders(),
      });
      const body = await resp.json();
      if (resp.ok) setTopicColumns((cur) => ({ ...cur, [topic]: body.columns }));
    } catch {
      // 忽略，columns 保持空，前端显示占位
    } finally {
      setTopicLoading(null);
    }
  }

  if (loading) return <div className="content"><div className="panel" style={{ padding: 40, textAlign: "center" }}>加载政策详情…</div></div>;
  if (!policy) return <div className="content"><Link href="/policies" className="back">← 返回政策库</Link><div className="notice">{error || "政策不存在"}</div></div>;

  const assessment = policy.assessments[0];
  const backHref = role === "consumer" ? "/for-you" : role === "processor" ? "/publications" : "/policies";

  return (
    <div className="content">
      <Link href={backHref} className="back">← 返回</Link>
      <div className="pagehead">
        <div>
          <div className="eyebrow">POLICY DETAIL</div>
          <h1>{role === "consumer" ? "政策解读" : "政策解读与审核"}</h1>
          <p className="sub">{policy.id} · {policy.doc_number || "无文号"} · {JURISDICTION_LABELS[policy.jurisdiction] || policy.jurisdiction || "未标注市场"}</p>
        </div>
        <div className="rowflex">
          <span className={`priority-pill ${policy.priority === "P0" ? "urgent" : policy.priority === "P1" ? "high" : policy.priority === "P2" ? "medium" : "low"}`}>{policy.priority}</span>
          <span className={`badge ${policy.status === "published" ? "green" : "amber"}`}>{POLICY_STATUS_LABELS[policy.status] || policy.status}</span>
          {role === "admin" && <button className="btn" disabled={busy} onClick={() => operation(`/policies/${policy.id}/analyze`, "重新分析完成")}>重新分析</button>}
          {(role === "admin" || role === "processor") && policy.status === "ai_checked" && <button className="btn primary" disabled={busy} onClick={() => operation(`/policies/${policy.id}/submit-review`, "已提交人工审核", { level: 1, note: "" }, `政策「${policy.title}」已提交人工审核`)}>提交审核</button>}
          {role === "processor" && policy.status === "approved" && <button className="btn primary" disabled={busy} onClick={() => operation(`/policies/${policy.id}/dispatch`, "发布完成")}>发布政策</button>}
          <button className="btn" onClick={() => setShowFeedback((v) => !v)}>反馈</button>
        </div>
      </div>
      {error && <div className="notice" style={{ marginBottom: 16 }}>{error}</div>}
      {notice && <div className="info" style={{ marginBottom: 16 }}>{notice}</div>}

      {showFeedback && (
        <div className="panel" style={{ marginBottom: 16 }}>
          <div className="sectionbody">
            <small>反馈意见（将送达审核员）</small>
            <textarea
              value={feedbackText}
              onChange={(e) => setFeedbackText(e.target.value)}
              placeholder="你对这条政策有疑问或建议？请在此输入…"
              className="reviewnote"
              rows={3}
              style={{ marginTop: 8 }}
            />
            <div className="rowflex" style={{ marginTop: 8 }}>
              <button className="btn primary" disabled={busy || !feedbackText.trim()} onClick={submitFeedback}>提交反馈</button>
              <button className="btn" onClick={() => { setShowFeedback(false); setFeedbackText(""); }}>取消</button>
            </div>
          </div>
        </div>
      )}

      <div className="stack">
        <section className="panel">
          <div className="panelhead"><h2>政策信息</h2></div>
            <div className="sectionbody">
              <h3 style={{ fontSize: 18, marginTop: 0 }}>{policy.title}</h3>
              <div className="fieldgrid">
                <div className="field"><small>发文机构</small><strong>{policy.issuing_body || "—"}</strong></div>
                <div className="field"><small>文件类型</small><strong>{policy.policy_type}</strong></div>
                <div className="field"><small>发布日期</small><strong>{dateLabel(policy.published_at)}</strong></div>
                <div className="field"><small>生效日期</small><strong>{dateLabel(policy.effective_at)}</strong></div>
                <div className="field"><small>适用主体</small><strong>{policy.applicable_entities_text || "原文未明确"}</strong></div>
                <div className="field"><small>影响 Domain</small><strong>{policy.impacted_domains.join("、") || "—"}</strong></div>
              </div>
              <div className="divider" />
              <div className="rowflex">{policy.themes.map((theme) => <span className="tag" key={theme}>#{theme}</span>)}</div>
              <div className="divider" />
              <small>AI 政策摘要</small>
              <p className="textblock">{policy.summary_zh || "尚未生成摘要，请核对原文或重新分析。"}</p>
            </div>
          </section>

          <section className="panel">
            <div className="panelhead"><h2>AI 结论与业务影响</h2><small>{analysisModelLabel(assessment?.model)}</small></div>
            <div className="sectionbody">
              {assessment ? <>
                <div className="fieldgrid">
                  <div className="field"><small>影响方向</small><strong>{DIRECTION_LABELS[assessment.direction] || assessment.direction}</strong></div>
                </div>
                <div className="divider" />
                <small className="section-label">传导路径</small>
                {assessment.transmission_chain.length ? <ol className="textblock">{assessment.transmission_chain.map((item, index) => <li key={index}>{item}</li>)}</ol> : <p className="textblock">未接入 AI 分析，传导路径待人工补写。</p>}
                <small className="section-label">受影响业务线与客群</small>
                <p className="textblock">{(assessment.affected.business_lines || []).join("、") || "—"}<br />{(assessment.affected.segments || []).join("、") || "—"}</p>
                <small className="section-label">客户暴露规模（合成口径）</small>
                {assessment.affected.exposure_range ? <div className="exposure-box"><strong>{assessment.affected.exposure_range.low}–{assessment.affected.exposure_range.high}</strong> {assessment.affected.exposure_range.currency} {assessment.affected.exposure_range.unit}<br />{assessment.affected.exposure_range.basis}</div> : <p className="textblock">缺少客户暴露数据，暴露规模未评定（合成数据集未覆盖该主题，需人工补充口径）。</p>}
                <small className="section-label">建议动作</small>
                {assessment.recommended_actions.length ? <ul className="textblock">{assessment.recommended_actions.map((item, index) => <li key={index}>{typeof item === "string" ? item : <>{item.action}{item.owner ? `（负责人：${item.owner}）` : ""}{item.deadline ? ` · ${item.deadline}` : ""}</>}</li>)}</ul> : <p className="textblock">暂无建议动作，需人工评定后补写。</p>}
                {assessment.case_links.length > 0 && <>
                  <small className="section-label">相似案例</small>
                  <div className="case-links">{assessment.case_links.map((link) => <div className="case-link" key={link.case_id}><small>{link.case_id} · 相似度 {link.similarity.toFixed(2)}</small>{link.takeaway || "同类先例"}</div>)}</div>
                </>}
              </> : <p className="textblock">当前没有影响分析记录。</p>}
            </div>
          </section>
      </div>

      {role === "consumer" && consumerView && (
        <section className="panel full">
          <div className="panelhead"><h2>政策解读</h2><small>面向所管理客户的影响</small></div>
          <div className="sectionbody">
            {/* 页首第一句：本政策有无纳入外资银行 + 对汇丰影响简述 */}
            <p className="textblock" style={{ fontWeight: 600 }}>{consumerView.foreign_bank_note}</p>
            <div className="divider" />

            {/* 政策摘要：重点话题（1.2.3 可点击展开三栏解读） */}
            <small>政策摘要 · 重点话题</small>
            <ol className="textblock" style={{ paddingLeft: 20 }}>
              {(consumerView.topics || []).map((t: any, idx: number) => (
                <li key={t.topic}>
                  <button
                    type="button"
                    className="link"
                    style={{ padding: 0, textAlign: "left" }}
                    onClick={() => {
                      const next = activeTopic === t.topic ? null : t.topic;
                      setActiveTopic(next);
                      if (next) void loadTopicColumns(next);
                    }}
                  >
                    {idx + 1}. {t.topic}
                  </button>
                  {activeTopic === t.topic && (
                    <div style={{ marginTop: 8, display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
                      {topicLoading === t.topic ? (
                        <div style={{ gridColumn: "1 / -1" }}><p className="textblock">正在加载该话题解读…</p></div>
                      ) : topicColumns[t.topic] ? (
                        <>
                          <div><small>汇丰解读</small><p className="textblock">{topicColumns[t.topic].hsbc}</p></div>
                          <div><small>业界解读</small><p className="textblock">{topicColumns[t.topic].industry}</p></div>
                          <div><small>市场案例</small><p className="textblock">{topicColumns[t.topic].market}</p></div>
                        </>
                      ) : (
                        <div style={{ gridColumn: "1 / -1" }}><p className="textblock">解读加载失败，请稍后重试。</p></div>
                      )}
                    </div>
                  )}
                </li>
              ))}
            </ol>
            <div className="divider" />

            {/* 政策原文简化版 */}
            <div className="field">
              <small>政策原文简化版</small>
              <p className="textblock">{consumerView.simplified_summary}</p>
            </div>
            <div className="divider" />

            {/* 所管理用户影响概述 + 所影响的客户（有客户才展示） */}
            {consumerView.affected_customers?.length > 0 ? (
              <>
                <div className="field">
                  <small>对所管理用户的影响概述</small>
                  <p className="textblock">{consumerView.impact_overview}</p>
                </div>
                <div className="divider" />
                <small>所影响的客户</small>
                <div className="tablewrap" style={{ marginTop: 8 }}>
                  <table>
                    <thead>
                      <tr>
                        <th>客户</th>
                        <th>业务线</th>
                        <th>贷款规模(亿)</th>
                        <th>他行贷款(亿)</th>
                        <th>海外业务</th>
                        <th>具体影响</th>
                      </tr>
                    </thead>
                    <tbody>
                      {consumerView.affected_customers.map((c: any) => (
                        <tr key={c.customer_id}>
                          <td>{c.name_masked}</td>
                          <td>{c.business_line}</td>
                          <td>{c.loan_balance_cny_yi}</td>
                          <td>{c.other_bank_loans_cny_yi}</td>
                          <td>{c.overseas_business?.length ? c.overseas_business.join("、") : "—"}</td>
                          <td>
                            <details>
                              <summary style={{ cursor: "pointer" }}>查看具体影响</summary>
                              <div style={{ marginTop: 6, fontSize: 12 }}>
                                <p>{c.impact.impact_content}</p>
                                <p>业务损失 <b>{c.impact.business_loss}</b> · 业务机会 <b>{c.impact.business_opportunity}</b> · 声誉风险 <b>{c.impact.reputation_risk}</b></p>
                                <p>{c.impact.outcome}</p>
                              </div>
                            </details>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="divider" />
              </>
            ) : null}

            <div className="field">
              <small>可能产生的收益或损失</small>
              <p className="textblock">{consumerView.benefit_loss}</p>
            </div>
            <div className="divider" />
            <div className="rowflex" style={{ marginTop: 8 }}>
              <button className="btn primary" disabled={busy} onClick={sendConsumerReport}>
                {busy ? "发送中…" : "发送给政策加工者 review →"}
              </button>
            </div>
          </div>
        </section>
      )}

      <section className="panel full source-panel">
        <div className="panelhead"><h2>政策原文</h2>{role !== "consumer" && <Link href={`/documents/${policy.document_id}`} className="link">打开原文库记录 →</Link>}</div>
            <div className="sectionbody">
              <div className="source-document"><h3>{policy.document?.title || policy.title}</h3><p style={{ whiteSpace: "pre-wrap" }}>{policy.document?.content_text || "原文正文不可用"}</p></div>
              {policy.url.startsWith("http") && <a href={policy.url} target="_blank" rel="noreferrer" className="link">访问监管来源网页 →</a>}
            </div>
          </section>

      {role === "admin" && (
        <>
          <section className="panel full">
            <div className="panelhead"><h2>原文证据</h2><small>{policy.evidence.length} 条</small></div>
            <div className="sectionbody">
              {policy.evidence.length ? policy.evidence.map((evidence) => <div className="evidence" key={evidence.id} style={{ marginBottom: 12 }}><small>{evidence.field_name || "政策字段"} · {evidence.span_start}–{evidence.span_end}</small><blockquote>{evidence.quote}</blockquote></div>) : <p className="textblock">没有可定位证据，提交审核前应打回补充。</p>}
            </div>
          </section>

          <section className="panel full">
            <div className="panelhead"><h2>相关性判定</h2><small>规则与 AI 双通道</small></div>
            <div className="sectionbody">
              {policy.scope_judgements.map((judgement) => <div key={judgement.entity_id} className="scope-tip" style={{ marginBottom: 10 }}><strong>{entityLabels[judgement.entity_id] || judgement.entity_id}</strong> <span className={`badge ${judgement.conflict ? "red" : ""}`}>{RELEVANCE_LABELS[judgement.result]?.text ?? judgement.result}</span><p>{judgement.llm_reason || "未提供判定理由"}</p>{judgement.conflict && <small style={{ color: "var(--red)" }}>规则与 AI 判定冲突，需要人工复核。</small>}</div>)}
            </div>
          </section>
        </>
      )}

      {role !== "consumer" && (
        <>
          <AgentTrace policyId={policy.id} />
          <ReviewPanel policyId={policy.id} reviewTasks={policy.review_tasks} onChanged={load} />
        </>
      )}
      <p className="footnote">政策分析仅供内部研究，最终合规判断以监管机构原文和人工审核结论为准。</p>
      {noticeDialog && <NoticeDialog message={noticeDialog} onClose={() => setNoticeDialog(null)} />}
    </div>
  );
}
