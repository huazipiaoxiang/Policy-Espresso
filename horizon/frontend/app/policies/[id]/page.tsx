"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import ScopeChip, { RELEVANCE_LABELS } from "@/components/ScopeChip";
import { DECISION_LABELS, DIRECTION_LABELS, JURISDICTION_LABELS, POLICY_STATUS_LABELS, SCORE_DIMENSION_LABELS, SCORE_DIMENSION_ORDER, SCORE_DIMENSION_WEIGHTS, TASK_STATUS_LABELS, analysisModelLabel } from "@/lib/labels";
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
  review_completed_at: string | null;
  dispatched_at: string | null;
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
  return value ? new Date(value).toLocaleString("zh-CN", { hour12: false }) : "—";
}

export default function PolicyDetailPage() {
  const params = useParams<{ id: string }>();
  const { role } = useAuth();
  const [policy, setPolicy] = useState<PolicyDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetch(`${API_BASE}/policies/${params.id}`, { headers: demoApiHeaders() });
      const data = await response.json();
      if (!response.ok) throw new Error(data?.error?.message || "政策加载失败");
      setPolicy(data);
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "政策加载失败");
    } finally {
      setLoading(false);
    }
  }, [params.id]);

  useEffect(() => { load(); }, [load]);

  async function operation(path: string, success: string) {
    setBusy(true);
    try {
      const response = await fetch(`${API_BASE}${path}`, { method: "POST", headers: demoApiHeaders() });
      const data = await response.json();
      if (!response.ok) throw new Error(data?.error?.message || "操作失败");
      await load();
      setNotice(success);
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "操作失败");
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <div className="content"><div className="panel" style={{ padding: 40, textAlign: "center" }}>加载政策详情…</div></div>;
  if (!policy) return <div className="content"><Link href="/policies" className="back">← 返回政策库</Link><div className="notice">{error || "政策不存在"}</div></div>;

  const assessment = policy.assessments[0];
  const backHref = role === "consumer" ? "/for-you" : role === "publisher" ? "/publications" : "/policies";

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
          {role === "publisher" && policy.status === "approved" && <button className="btn primary" disabled={busy} onClick={() => operation(`/policies/${policy.id}/dispatch`, "发布完成")}>发布政策</button>}
        </div>
      </div>
      {error && <div className="notice" style={{ marginBottom: 16 }}>{error}</div>}
      {notice && <div className="info" style={{ marginBottom: 16 }}>{notice}</div>}

      <div className="status-four">
        <div><small>相关性筛选</small><span style={{ display: "block", marginTop: 8 }}><ScopeChip status={policy.target_entity_status} /></span></div>
        <div><small>AI 深度分析</small><span className={`badge ${assessment ? "green" : ""}`}>{assessment ? "已完成" : "未生成"}</span></div>
        <div><small>人工审核</small><span className={`badge ${["approved", "published"].includes(policy.status) ? "green" : "amber"}`}>{POLICY_STATUS_LABELS[policy.status] || policy.status}</span></div>
        <div><small>发布时间</small><strong style={{ display: "block", marginTop: 8, fontSize: 12 }}>{dateLabel(policy.dispatched_at)}</strong></div>
      </div>

      <div className="details-grid">
        <div className="stack">
          <section className="panel">
            <div className="panelhead"><h2>政策信息</h2><small>Policy Information</small></div>
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
              <div className="ai-confidence-overview">
                <div><div className="label">分析可靠程度</div><div className="confidence-inline"><span className="value">{policy.confidence > 0 ? `${Math.round(policy.confidence * 100)}%` : "未评定"}</span></div></div>
                <p className="explain">该数值来自当前分析结果，仅用于安排人工复核优先级，不替代合规判断。</p>
              </div>
            </div>
          </section>

          <section className="panel">
            <div className="panelhead"><h2>AI 结论与业务影响</h2><small>{analysisModelLabel(assessment?.model)}</small></div>
            <div className="sectionbody">
              {assessment ? <>
                <div className="fieldgrid">
                  <div className="field"><small>影响评分（0–100 加权）</small><strong style={{ color: "var(--red)" }}>{assessment.score_total > 0 ? assessment.score_total.toFixed(1) : "未评定"}</strong></div>
                  <div className="field"><small>影响方向</small><strong>{DIRECTION_LABELS[assessment.direction] || assessment.direction} <span style={{ fontSize: 10, color: "#8b929c", fontWeight: 400 }}>（单独呈现，不参与加权）</span></strong></div>
                  <div className="field"><small>影响分析置信度</small><strong>{assessment.confidence > 0 ? `${Math.round(assessment.confidence * 100)}%` : "未评定"}</strong></div>
                </div>
                <p className="score-priority-note">综合分 = Σ(维度分 ÷ 5 × 权重)：P0 ≥ 80（当日处理）· P1 60–79（24 小时内）· P2 40–59（本周内）· P3 &lt; 40（归档观察）。每个维度必须给出评分理由；无证据的维度保持“未评定”并说明缺什么。</p>
                <div className="divider" />
                <small>八维评分卡（0–5 分）</small>
                <div className="scorecard">
                  {SCORE_DIMENSION_ORDER.map((dim) => {
                    const entry = assessment.scores[dim];
                    const missing = !entry || entry.score == null;
                    return (
                      <div className={`scorecard-row${missing ? " missing" : ""}`} key={dim}>
                        <div className="dim-head">
                          <span className="dim-name">{SCORE_DIMENSION_LABELS[dim] || dim}</span>
                          <span className="dim-weight">权重 {SCORE_DIMENSION_WEIGHTS[dim]}</span>
                          <span className="dim-score">
                            {missing
                              ? <span className="badge amber">未评定</span>
                              : <><strong>{entry?.score ?? "—"}</strong><small>/ 5</small></>}
                          </span>
                        </div>
                        <p className="dim-reason">{entry?.reason || "未提供理由"}</p>
                      </div>
                    );
                  })}
                </div>
                <div className="divider" />
                <small>传导路径</small>
                {assessment.transmission_chain.length ? <ol>{assessment.transmission_chain.map((item, index) => <li key={index}>{item}</li>)}</ol> : <p className="textblock">未接入 AI 分析，传导路径待人工补写。</p>}
                <small>受影响业务线与客群</small>
                <p className="textblock">{(assessment.affected.business_lines || []).join("、") || "—"}<br />{(assessment.affected.segments || []).join("、") || "—"}</p>
                <small>客户暴露规模（合成口径）</small>
                {assessment.affected.exposure_range ? <div className="exposure-box"><strong>{assessment.affected.exposure_range.low}–{assessment.affected.exposure_range.high}</strong> {assessment.affected.exposure_range.currency} {assessment.affected.exposure_range.unit}<br />{assessment.affected.exposure_range.basis}</div> : <p className="textblock">缺少客户暴露数据，暴露规模未评定（合成数据集未覆盖该主题，需人工补充口径）。</p>}
                <small>建议动作</small>
                {assessment.recommended_actions.length ? <ul>{assessment.recommended_actions.map((item, index) => <li key={index}>{typeof item === "string" ? item : <>{item.action}{item.owner ? `（负责人：${item.owner}）` : ""}{item.deadline ? ` · ${item.deadline}` : ""}</>}</li>)}</ul> : <p className="textblock">暂无建议动作，需人工评定后补写。</p>}
                {assessment.case_links.length > 0 && <>
                  <small>相似案例</small>
                  <div className="case-links">{assessment.case_links.map((link) => <div className="case-link" key={link.case_id}><small>{link.case_id} · 相似度 {link.similarity.toFixed(2)}</small>{link.takeaway || "同类先例"}</div>)}</div>
                </>}
              </> : <p className="textblock">当前没有影响分析记录。</p>}
            </div>
          </section>

          <section className="panel source-panel">
            <div className="panelhead"><h2>政策原文</h2>{role !== "consumer" && <Link href={`/documents/${policy.document_id}`} className="link">打开原文库记录 →</Link>}</div>
            <div className="sectionbody">
              <div className="source-document"><h3>{policy.document?.title || policy.title}</h3><p style={{ whiteSpace: "pre-wrap" }}>{policy.document?.content_text || "原文正文不可用"}</p></div>
              {policy.url.startsWith("http") && <a href={policy.url} target="_blank" rel="noreferrer" className="link">访问监管来源网页 →</a>}
            </div>
          </section>
        </div>

        <div className="stack">
          <section className="panel">
            <div className="panelhead"><h2>原文证据</h2><small>{policy.evidence.length} 条</small></div>
            <div className="sectionbody">
              {policy.evidence.length ? policy.evidence.map((evidence) => <div className="evidence" key={evidence.id} style={{ marginBottom: 12 }}><small>{evidence.field_name || "政策字段"} · {evidence.span_start}–{evidence.span_end}</small><blockquote>{evidence.quote}</blockquote></div>) : <p className="textblock">没有可定位证据，提交审核前应打回补充。</p>}
            </div>
          </section>

          <section className="panel">
            <div className="panelhead"><h2>相关性判定</h2><small>规则与 AI 双通道</small></div>
            <div className="sectionbody">
              {policy.scope_judgements.map((judgement) => <div key={judgement.entity_id} className="scope-tip" style={{ marginBottom: 10 }}><strong>{entityLabels[judgement.entity_id] || judgement.entity_id}</strong> <span className={`badge ${judgement.conflict ? "red" : ""}`}>{RELEVANCE_LABELS[judgement.result]?.text ?? judgement.result}</span><p>{judgement.llm_reason || "未提供判定理由"}</p>{judgement.conflict && <small style={{ color: "var(--red)" }}>规则与 AI 判定冲突，需要人工复核。</small>}</div>)}
            </div>
          </section>

          {role !== "consumer" && <section className="panel">
            <div className="panelhead"><h2>审核记录</h2><small>{policy.review_tasks.length} 个任务</small></div>
            <div className="sectionbody">
              {policy.review_tasks.length ? policy.review_tasks.map((task) => <div key={task.id} style={{ marginBottom: 18 }}><strong>{task.level} 级审核 · {TASK_STATUS_LABELS[task.status] || task.status}</strong><small style={{ display: "block" }}>{task.assignee} · {dateLabel(task.created_at)}</small><div className="history">{task.decisions.map((decision, index) => <div key={index}><strong>{decision.actor}</strong> — {DECISION_LABELS[decision.action] || decision.action}<br /><small>{dateLabel(decision.created_at)}{decision.reason_code ? ` · ${decision.reason_code}` : ""}</small>{decision.note && <p>{decision.note}</p>}</div>)}</div></div>) : <p className="textblock">尚未进入人工审核。</p>}
              {(role === "analyst" || role === "approver") && <Link href="/review" className="btn primary">前往审核工作台</Link>}
            </div>
          </section>}
        </div>
      </div>
      <p className="footnote">政策分析仅供内部研究，最终合规判断以监管机构原文和人工审核结论为准。</p>
    </div>
  );
}
