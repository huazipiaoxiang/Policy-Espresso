"use client";

import { useEffect, useState } from "react";
import { API_BASE, demoApiHeaders } from "@/lib/auth";
import { AUDIT_ACTION_LABELS, DIRECTION_LABELS, POLICY_STATUS_LABELS } from "@/lib/labels";
import { RELEVANCE_LABELS } from "./ScopeChip";

// 「AI 分析过程」时间线：五步链路（分类打标 → 结构化抽取 → 适用性判定 → 影响分析 → 预警草稿）
// → 提交人工审核 → 审核决策 → 发布。数据源：
// - GET /policies/{id}/analysis（五步结论 + 每步 LLM 调用明细）
// - GET /admin/audit（生命周期事件；ai_analyze 已由五步节点代表，数据修复类为运维噪音不展示）

interface StepItem {
  label: string;
  value: string | number | null;
  note?: string;
  conflict?: boolean;
}

interface StepLLM {
  model: string;
  provider: string;
  prompt_version: string;
  tokens_in: number;
  tokens_out: number;
  latency_ms: number;
  status: string;
  error: string | null;
  at: string;
}

interface AnalysisStep {
  key: string;
  title: string;
  description: string;
  items: StepItem[];
  body_md?: string;
  llm: StepLLM | null;
}

interface AnalysisResponse {
  policy_id: string;
  prompt_version: string;
  steps: AnalysisStep[];
}

interface AuditEvent {
  id: string;
  at: string;
  actor: string;
  action: string;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  reason: string;
}

interface AuditResponse {
  items: AuditEvent[];
  total: number;
}

const ENTITY_LABELS: Record<string, string> = {
  hsbc_hk: "汇丰香港",
  hsbc_cn: "汇丰中国",
};

// 流转事件节点颜色（按语义着色）
const EVENT_COLOR: Record<string, string> = {
  submit_review: "var(--warn)",
  claim_task: "var(--warn)",
  review_approve: "var(--ok)",
  review_reject: "var(--danger)",
  review_request_info: "var(--warn)",
  skip_review: "var(--text-3)",
  dispatch: "var(--ok)",
  delete_policy: "var(--danger)",
  refresh_scorecard: "var(--accent)",
  update_policy: "var(--text-3)",
};

const HIDDEN_EVENTS = new Set(["ai_analyze", "repair_fixture_content", "repair_fixture_content_batch"]);

function fmtTime(at: string): string {
  return at ? at.slice(0, 19).replace("T", " ") : "—";
}

function fmtLatency(ms: number): string {
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`;
}

function fmtNumber(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

function statusLabel(value: unknown): string {
  if (typeof value !== "string" || !value) return "—";
  return POLICY_STATUS_LABELS[value] ?? value;
}

function statusFlow(before: Record<string, unknown> | null, after: Record<string, unknown> | null): string {
  const b = before?.status;
  const a = after?.status;
  if (b == null && a == null) return "";
  return `${statusLabel(b)} → ${statusLabel(a)}`;
}

function fmtItemValue(stepKey: string, label: string, value: string | number | null): string {
  if (stepKey === "scope") {
    return RELEVANCE_LABELS[String(value)]?.text ?? String(value ?? "—");
  }
  if (stepKey === "impact" && label === "影响方向") {
    return DIRECTION_LABELS[String(value)] ?? String(value ?? "—");
  }
  if (value == null || value === "") return "—";
  if (typeof value === "number") return fmtNumber(value);
  return value;
}

function itemLabel(stepKey: string, label: string): string {
  return stepKey === "scope" ? (ENTITY_LABELS[label] ?? label) : label;
}

export default function AgentTrace({ policyId }: { policyId: string }) {
  const [analysis, setAnalysis] = useState<AnalysisResponse | null>(null);
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const [aResp, eResp] = await Promise.all([
          fetch(`${API_BASE}/policies/${policyId}/analysis`, { headers: demoApiHeaders() }),
          fetch(
            `${API_BASE}/admin/audit?object_type=policy&object_id=${encodeURIComponent(policyId)}&page_size=100`,
            { headers: demoApiHeaders() },
          ),
        ]);
        const aBody = (await aResp.json()) as AnalysisResponse & { error?: { message?: string } };
        if (!aResp.ok) throw new Error(aBody?.error?.message || "分析过程加载失败");
        const eBody = eResp.ok ? ((await eResp.json()) as AuditResponse) : { items: [], total: 0 };
        if (active) {
          setAnalysis(aBody);
          const items = (eBody.items ?? []).filter((event) => !HIDDEN_EVENTS.has(event.action));
          items.sort((x, y) => (x.at < y.at ? -1 : x.at > y.at ? 1 : 0));
          setEvents(items);
        }
      } catch (reason) {
        if (active) setError(reason instanceof Error ? reason.message : "分析过程加载失败");
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, [policyId]);

  const steps = analysis?.steps ?? [];
  const empty = !loading && !error && steps.length === 0 && events.length === 0;

  return (
    <section className="panel full">
      <div className="panelhead">
        <h2>Agent 执行轨迹</h2>
        <small>
          {analysis
            ? `${steps.length} 步链路 · prompt ${analysis.prompt_version || "未记录"} · 另有 ${events.length} 个流转事件`
            : "五步链路 → 提交人工审核"}
        </small>
      </div>
      <div className="sectionbody">
        {loading && <p className="textblock" style={{ color: "var(--muted)" }}>加载执行轨迹…</p>}
        {error && <p className="textblock" style={{ color: "var(--danger)" }}>{error}</p>}
        {empty && <p className="textblock" style={{ color: "var(--muted)" }}>暂无执行轨迹记录。</p>}

        {!loading && !error && (steps.length > 0 || events.length > 0) && (
          <ol className="agent-trace">
            {steps.map((step, index) => (
              <li key={step.key}>
                <span className="agent-trace-dot" style={{ background: "var(--accent)" }} />
                <div className="agent-trace-body">
                  <div className="agent-trace-head">
                    <span className="agent-trace-stage">分析</span>
                    <span className="agent-trace-action">
                      第 {index + 1} 步 · {step.title}
                    </span>
                  </div>
                  <p className="agent-trace-desc">{step.description}</p>
                  {step.llm && (
                    <p className="agent-trace-llm" title={`${step.llm.provider} · ${step.llm.prompt_version}`}>
                      {step.llm.model} · 输入 {step.llm.tokens_in} tok · 输出 {step.llm.tokens_out} tok · 耗时{" "}
                      {fmtLatency(step.llm.latency_ms)}
                      {step.llm.status !== "ok" ? ` · ${step.llm.status}` : ""}
                    </p>
                  )}
                  {step.items.length > 0 && (
                    <div className="agent-trace-items">
                      {step.items.map((item) => (
                        <div className="agent-trace-item" key={item.label}>
                          <small>{itemLabel(step.key, item.label)}</small>
                          <span>{fmtItemValue(step.key, item.label, item.value)}</span>
                          {item.conflict && <em className="agent-trace-conflict">双通道冲突</em>}
                          {item.note && <p>{item.note}</p>}
                        </div>
                      ))}
                    </div>
                  )}
                  {step.body_md ? (
                    <details className="details agent-trace-details">
                      <summary>查看预警草稿全文</summary>
                      <div className="inside" style={{ whiteSpace: "pre-wrap" }}>{step.body_md}</div>
                    </details>
                  ) : null}
                </div>
              </li>
            ))}

            {events.map((event) => {
              const flow = statusFlow(event.before, event.after);
              return (
                <li key={event.id}>
                  <span
                    className="agent-trace-dot"
                    style={{ background: EVENT_COLOR[event.action] ?? "var(--text-3)" }}
                  />
                  <div className="agent-trace-body">
                    <div className="agent-trace-head">
                      <span className="agent-trace-stage">流转</span>
                      <span className="agent-trace-action">{AUDIT_ACTION_LABELS[event.action] ?? event.action}</span>
                      <time className="agent-trace-time">{fmtTime(event.at)}</time>
                    </div>
                    <div className="agent-trace-actor">{event.actor}</div>
                    {flow && <div className="agent-trace-flow">状态：{flow}</div>}
                    {event.reason && <div className="agent-trace-reason">备注：{event.reason}</div>}
                  </div>
                </li>
              );
            })}
          </ol>
        )}
      </div>
    </section>
  );
}
