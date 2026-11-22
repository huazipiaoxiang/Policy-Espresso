"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import { RELEVANCE_LABELS } from "@/components/ScopeChip";
import ReviewPanel from "@/components/ReviewPanel";
import AgentTrace from "@/components/AgentTrace";
import PolicyTrackingEmail from "@/components/PolicyTrackingEmail";
import AffectedCustomersOverview from "@/components/AffectedCustomersOverview";
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
  differential?: {
    foreign_bank_differential: boolean;
    applies_to_hsbc: boolean | null;
    attention_level: "none" | "watch" | "focus";
    note: string;
    reason: string;
    source?: "ai" | "fallback";
  };
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

interface ResearchLink {
  summary: string; // 简述
  url: string; // 原文链接
}

/** 外部公开反应：只展示简述 + 原文链接，政策使用者不看到标题/来源等冗余字段 */
function ResearchLinkList({
  title,
  items,
  emptyText = "网上暂无公开响应",
}: {
  title: string;
  items?: ResearchLink[];
  emptyText?: string;
}) {
  const list = items ?? [];
  return (
    <div style={{ marginTop: 8 }}>
      <small style={{ display: "block", marginBottom: 4 }}>{title}</small>
      {list.length === 0 ? (
        <p className="textblock" style={{ color: "#949aa3", margin: 0 }}>{emptyText}</p>
      ) : (
        <ul style={{ margin: "0 0 0 16px", fontSize: 13 }}>
          {list.map((item) => (
            <li key={item.url} style={{ marginBottom: 4 }}>
              <span>{item.summary || "（无简述）"}</span>{" "}
              <a href={item.url} target="_blank" rel="noreferrer" className="link">原文 →</a>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function PolicyDetailPage() {
  const params = useParams<{ id: string }>();
  const { role, username } = useAuth();
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
  // 记录已初始化话题的政策 id：首次进入某政策时默认选中第一个重点话题
  const loadedPolicyRef = useRef<string | null>(null);

  const load = useCallback(async () => {
    const isNewPolicy = loadedPolicyRef.current !== params.id;
    if (isNewPolicy) {
      // 切换政策时清空上一份话题选择与三栏缓存，避免串数据
      loadedPolicyRef.current = params.id;
      setActiveTopic(null);
      setTopicColumns({});
    }
    setLoading(true);
    try {
      // 政策详情与使用者解读并行请求，避免串行等待两个含 AI 调用的接口
      const query = username ? `?username=${encodeURIComponent(username)}` : "";
      const policyReq = fetch(`${API_BASE}/policies/${params.id}`, { headers: demoApiHeaders() });
      const cvReq = role === "consumer"
        ? fetch(`${API_BASE}/policies/${params.id}/consumer-view${query}`, { headers: demoApiHeaders() })
        : Promise.resolve(null);

      const [policyResp, cvResp] = await Promise.all([policyReq, cvReq]);

      const data = await policyResp.json();
      if (!policyResp.ok) throw new Error(data?.error?.message || "政策加载失败");
      setPolicy(data);
      setError("");

      if (cvResp && cvResp.ok) {
        const view = await cvResp.json();
        setConsumerView(view);
        // 首次进入该政策：默认选中第一个重点话题，并加载其下方三栏解读
        const firstTopic = (view.topics || [])[0]?.topic;
        if (isNewPolicy && firstTopic) {
          setActiveTopic(firstTopic);
          void loadTopicColumns(firstTopic, params.id);
        }
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "政策加载失败");
    } finally {
      setLoading(false);
    }
  }, [params.id, role, username]);

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
      setNotice("反馈已提交，已送达平台管理员");
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
      const query = username ? `?username=${encodeURIComponent(username)}` : "";
      const response = await fetch(`${API_BASE}/policies/${policy?.id}/consumer-view/send-review${query}`, {
        method: "POST",
        headers: demoApiHeaders(),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data?.error?.message || "发送失败");
      setNoticeDialog(`影响报告已发送给政策运营专员，运营专员可在政策跟进中心查看该政策影响到的全部客户明细。`);
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "发送失败");
    } finally {
      setBusy(false);
    }
  }

  async function loadTopicColumns(topic: string, targetPolicyId?: string) {
    const topicPolicyId = targetPolicyId || policy?.id;
    if (!topicPolicyId) return;
    // 手动点选走缓存；自动初始化时强制请求，避免沿用上一份政策的同名话题缓存
    if (!targetPolicyId && (topicColumns[topic] || topicLoading === topic)) return;
    setTopicLoading(topic);
    try {
      const resp = await fetch(`${API_BASE}/policies/${topicPolicyId}/topic/${encodeURIComponent(topic)}`, {
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
  const backHref = role === "consumer" ? "/for-you" : role === "processor" ? "/follow-up" : "/policies";

  return (
    <div className="content">
      <Link href={backHref} className="back">← 返回</Link>
      <div className="pagehead">
        <div>
          <div className="eyebrow">POLICY DETAIL</div>
          {/* 运营专员只看政策解读；审核类入口仅管理员保留 */}
          <h1>{role === "admin" ? "政策解读与审核" : "政策解读"}</h1>
          <p className="sub">{policy.id} · {policy.doc_number || "无文号"} · {JURISDICTION_LABELS[policy.jurisdiction] || policy.jurisdiction || "未标注市场"}</p>
        </div>
        <div className="rowflex">
          <span className={`priority-pill ${policy.priority === "P0" ? "urgent" : policy.priority === "P1" ? "high" : policy.priority === "P2" ? "medium" : "low"}`}>{policy.priority}</span>
          <span className={`badge ${policy.status === "published" ? "green" : "amber"}`}>{POLICY_STATUS_LABELS[policy.status] || policy.status}</span>
          {role === "admin" && <button className="btn" disabled={busy} onClick={() => operation(`/policies/${policy.id}/analyze`, "重新分析完成")}>重新分析</button>}
          {role === "admin" && policy.status === "ai_checked" && <button className="btn primary" disabled={busy} onClick={() => operation(`/policies/${policy.id}/submit-review`, "已转入处理", { level: 1, note: "" }, `政策「${policy.title}」已转入处理`)}>转入处理</button>}
          {role === "admin" && policy.status === "approved" && <button className="btn primary" disabled={busy} onClick={() => operation(`/policies/${policy.id}/dispatch`, "发布完成")}>发布政策</button>}
          <button className="btn" onClick={() => setShowFeedback((v) => !v)}>反馈</button>
        </div>
      </div>
      {error && <div className="notice" style={{ marginBottom: 16 }}>{error}</div>}
      {notice && <div className="info" style={{ marginBottom: 16 }}>{notice}</div>}

      {showFeedback && (
        <div className="panel" style={{ marginBottom: 16 }}>
          <div className="sectionbody">
            <small>反馈意见（将送达平台管理员）</small>
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
              <small>政策摘要</small>
              <p className="textblock">{policy.summary_zh || "尚未生成摘要，请核对原文或重新分析。"}</p>
            </div>
          </section>

          <section className="panel">
            <div className="panelhead"><h2>业务影响</h2><small>{analysisModelLabel(assessment?.model)}</small></div>
            <div className="sectionbody">
              {assessment ? <>
                <div className="fieldgrid">
                  <div className="field"><small>影响方向</small><strong>{DIRECTION_LABELS[assessment.direction] || assessment.direction}</strong></div>
                  {policy.differential?.note ? (
                    <div className="field">
                      <small>{policy.differential.foreign_bank_differential ? "外资银行差异条款" : "汇丰相关影响"}</small>
                      <strong style={{ color: "var(--amber, #b08900)" }}>{policy.differential.note}</strong>
                      {policy.differential.source === "fallback" ? (
                        <span style={{ marginLeft: 8, fontSize: 11, color: "#8b929c" }}>（AI 暂不可用，以下为提示性说明）</span>
                      ) : null}
                      {policy.differential.reason ? (
                        <p className="textblock" style={{ margin: "4px 0 0", fontSize: 12 }}>{policy.differential.reason}</p>
                      ) : null}
                    </div>
                  ) : null}
                </div>
                <div className="divider" />
                <small className="section-label">传导路径</small>
                {assessment.transmission_chain.length ? <ol className="textblock">{assessment.transmission_chain.map((item, index) => <li key={index}>{item}</li>)}</ol> : <p className="textblock">暂无传导分析，传导路径待人工补写。</p>}
                <small className="section-label">受影响业务线与客群</small>
                <p className="textblock">{(assessment.affected.business_lines || []).join("、") || "—"}<br />{(assessment.affected.segments || []).join("、") || "—"}</p>
                <small className="section-label">客户暴露规模</small>
                {assessment.affected.exposure_range ? <div className="exposure-box"><strong>{assessment.affected.exposure_range.low}–{assessment.affected.exposure_range.high}</strong> {assessment.affected.exposure_range.currency} {assessment.affected.exposure_range.unit}<br />{assessment.affected.exposure_range.basis}</div> : <p className="textblock">缺少客户暴露数据，暴露规模未评定。</p>}
                <small className="section-label">建议动作</small>
                {assessment.recommended_actions.length ? <ul className="textblock">{assessment.recommended_actions.map((item, index) => <li key={index}>{typeof item === "string" ? item : <>{item.action}{item.owner ? `（负责人：${item.owner}）` : ""}{item.deadline ? ` · ${item.deadline}` : ""}</>}</li>)}</ul> : <p className="textblock">暂无建议动作，需人工评定后补写。</p>}
              </> : <p className="textblock">当前没有影响分析记录。</p>}
            </div>
          </section>
      </div>

      {/* 运营专员与管理员：客户库全量的受影响客户概况；客户名单仅管理员可见 */}
      {(role === "processor" || role === "admin") && (
        <AffectedCustomersOverview policyId={policy.id} role={role} />
      )}

      {role === "consumer" && consumerView && (
        <section className="panel full">
          <div className="panelhead"><h2>政策解读</h2><small>面向所管理客户的影响</small></div>
          <div className="sectionbody">
            {/* 政策原文简化版 */}
            <div className="field">
              <small>政策原文简化版</small>
              <p className="textblock">{consumerView.simplified_summary}</p>
            </div>
            <div className="divider" />

            {/* 政策摘要 · 重点话题：横向排列，点击后由下方三列展示该话题结果 */}
            <small>政策摘要 · 重点话题</small>
            <div className="rowflex" style={{ flexWrap: "wrap", gap: 8, marginTop: 8 }}>
              {(consumerView.topics || []).map((t: any, idx: number) => (
                <button
                  key={t.topic}
                  type="button"
                  className={`btn${activeTopic === t.topic ? " primary" : ""}`}
                  onClick={() => {
                    const next = activeTopic === t.topic ? null : t.topic;
                    setActiveTopic(next);
                    if (next) void loadTopicColumns(next);
                  }}
                >
                  {idx + 1}. {t.topic}
                </button>
              ))}
            </div>
            <div className="divider" />

            {/* 三列结果：选中重点话题时展示该话题的汇丰/他行/市场公开结果，
                未选中时展示政策整体的外部公开反应 */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12, marginTop: 8 }}>
              {activeTopic && topicLoading === activeTopic ? (
                <div className="panel" style={{ gridColumn: "1 / -1", padding: 12 }}>
                  <p className="textblock">正在加载「{activeTopic}」的公开结果…</p>
                </div>
              ) : activeTopic && !topicColumns[activeTopic] ? (
                <div className="panel" style={{ gridColumn: "1 / -1", padding: 12 }}>
                  <p className="textblock">该话题的公开结果加载失败，请稍后重试。</p>
                </div>
              ) : (
                <>
                  <div className="panel" style={{ padding: 12 }}>
                    <ResearchLinkList
                      title="汇丰对此政策/话题的反应"
                      items={activeTopic ? topicColumns[activeTopic]?.hsbc : consumerView.research?.hsbc_response}
                    />
                  </div>
                  <div className="panel" style={{ padding: 12 }}>
                    <ResearchLinkList
                      title="类似政策"
                      items={activeTopic ? topicColumns[activeTopic]?.industry : consumerView.research?.peer_bank_response}
                      emptyText="网上暂无公开解读"
                    />
                  </div>
                  <div className="panel" style={{ padding: 12 }}>
                    <ResearchLinkList
                      title="市面上实际应用"
                      items={activeTopic ? topicColumns[activeTopic]?.market : consumerView.research?.market_applications}
                      emptyText="网上暂无公开落地案例"
                    />
                  </div>
                </>
              )}
            </div>
            {activeTopic && (
              <p style={{ fontSize: 12, color: "#8b929c", marginTop: 6 }}>
                当前展示「{activeTopic}」的公开结果，再次点击该话题可回到政策整体结果。
              </p>
            )}
            <div className="divider" />

            {/* 所管理用户影响概述 + 所影响的客户（有客户才展示） */}
            {consumerView.affected_customers?.length > 0 ? (
              <>
                <div className="field">
                  <small>对所管理用户的影响概述</small>
                  <p className="textblock">{consumerView.impact_overview}</p>
                </div>
                {consumerView.followup_advice ? (
                  <div className="field">
                    <small>跟进建议</small>
                    <p className="textblock">{consumerView.followup_advice}</p>
                  </div>
                ) : null}
                <div className="divider" />
                <small>所影响的客户</small>
                {consumerView.match_basis && (
                  <p className="textblock" style={{ fontSize: 12, color: "#8b929c", marginTop: 4, marginBottom: 0 }}>
                    匹配口径：{consumerView.match_basis.rule}
                    {consumerView.match_basis.business_lines?.length ? `（${consumerView.match_basis.business_lines.join("、")}）` : ""}
                    {" · 共 "}{consumerView.match_basis.total_matched}{" 户 · 展示 "}{consumerView.match_basis.shown}{" 户 · "}
                    {consumerView.match_basis.source}
                  </p>
                )}
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
                        <th>跟进措施</th>
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
                                <p>{c.impact.outcome}</p>
                              </div>
                            </details>
                          </td>
                          <td style={{ minWidth: 200 }}>{c.followup_action || "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="divider" />
              </>
            ) : null}

            <div className="rowflex" style={{ marginTop: 8 }}>
              <button className="btn primary" disabled={busy} onClick={sendConsumerReport}>
                {busy ? "发送中…" : "发送给政策运营专员跟进"}
              </button>
            </div>
          </div>
        </section>
      )}

      <section className="panel full source-panel">
        <div className="panelhead"><h2>政策原文</h2>{role !== "consumer" && <Link href={`/documents/${policy.document_id}`} className="link">打开原文库记录 →</Link>}</div>
            <div className="sectionbody">
              {policy.url.startsWith("http") && (
                <p style={{ margin: "0 0 8px" }}>
                  <a href={policy.url} target="_blank" rel="noreferrer" className="link">访问监管来源网页 →</a>
                </p>
              )}
              <div className="source-document"><h3>{policy.document?.title || policy.title}</h3><p style={{ whiteSpace: "pre-wrap" }}>{policy.document?.content_text || "原文正文不可用"}</p></div>
            </div>
          </section>

      {role === "admin" && (
        <>
          <section className="panel full">
            <div className="panelhead"><h2>原文证据</h2><small>{policy.evidence.length} 条</small></div>
            <div className="sectionbody">
              {policy.evidence.length ? policy.evidence.map((evidence) => <div className="evidence" key={evidence.id} style={{ marginBottom: 12 }}><small>{evidence.field_name || "政策字段"} · {evidence.span_start}–{evidence.span_end}</small><blockquote>{evidence.quote}</blockquote></div>) : <p className="textblock">没有可定位证据，应补充原文证据后再使用分析结论。</p>}
            </div>
          </section>

          <section className="panel full">
            <div className="panelhead"><h2>相关性判定</h2><small>规则与模型双通道</small></div>
            <div className="sectionbody">
              {policy.scope_judgements.map((judgement) => <div key={judgement.entity_id} className="scope-tip" style={{ marginBottom: 10 }}><strong>{entityLabels[judgement.entity_id] || judgement.entity_id}</strong> <span className={`badge ${judgement.conflict ? "red" : ""}`}>{RELEVANCE_LABELS[judgement.result]?.text ?? judgement.result}</span><p>{judgement.llm_reason || "未提供判定理由"}</p>{judgement.conflict && <small style={{ color: "var(--red)" }}>规则与模型判定冲突，需要人工复核。</small>}</div>)}
            </div>
          </section>
        </>
      )}

      {/* 执行轨迹与处理面板仅管理员可见；运营专员改为生成政策跟踪报告邮件 */}
      {role === "admin" && (
        <>
          <AgentTrace policyId={policy.id} />
          <ReviewPanel policyId={policy.id} reviewTasks={policy.review_tasks} onChanged={load} />
        </>
      )}
      {role === "processor" && <PolicyTrackingEmail policy={policy} />}
      <p className="footnote">政策抓取、分析与发布均由 AI 自动完成；结论仅供内部研究，最终合规判断以监管机构原文及最新监管口径为准。</p>
      {noticeDialog && <NoticeDialog message={noticeDialog} onClose={() => setNoticeDialog(null)} />}
    </div>
  );
}
