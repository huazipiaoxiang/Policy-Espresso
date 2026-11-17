"use client";

import { useCallback, useEffect, useState } from "react";
import { useAuth } from "./AuthProvider";
import { API_BASE, demoApiHeaders } from "@/lib/auth";
import { DECISION_LABELS, TASK_STATUS_LABELS } from "@/lib/labels";

// 政策详情页内的审核面板：审批动作从原「审核工作台」迁移到此处（审批发生在政策详情页）。
// 依据当前角色定位可处理任务（analyst → 一级，approver → 二级），拉取该任务的「AI 质疑」，
// 提供通过 / 驳回（必填原因码）/ 退回补充 三个动作，并展示完整审核记录。

export interface ReviewDecision {
  actor: string;
  action: string;
  reason_code: string | null;
  note: string;
  created_at: string;
}

export interface ReviewTask {
  id: string;
  level: number;
  assignee: string;
  status: string;
  sla_due_at?: string | null;
  created_at?: string;
  decisions: ReviewDecision[];
}

interface ReviewDetail {
  task: {
    id: string;
    policy_id: string;
    level: number;
    status: string;
  };
  challenges: { risk: string; issue: string; suggestion: string }[];
  previous_decisions: ReviewDecision[];
  evidence_count: number;
  scope_conflict: boolean;
}

const REASON_CODES = [
  { value: "insufficient_evidence", label: "证据不足" },
  { value: "impact_misjudged", label: "影响误判" },
  { value: "scope_misjudged", label: "适用性误判" },
  { value: "bad_wording", label: "表述不当" },
  { value: "duplicate", label: "重复" },
  { value: "other", label: "其他" },
];

function dateLabel(value: string | null | undefined) {
  return value ? value.slice(0, 10) : "—";
}

export default function ReviewPanel({
  policyId,
  reviewTasks,
  onChanged,
}: {
  policyId: string;
  reviewTasks: ReviewTask[];
  onChanged: () => void;
}) {
  const { role } = useAuth();
  const [detail, setDetail] = useState<ReviewDetail | null>(null);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [reasonCode, setReasonCode] = useState("insufficient_evidence");
  const [note, setNote] = useState("");
  const [toast, setToast] = useState("");
  const [busy, setBusy] = useState(false);

  const actionableTask = reviewTasks.find((task) => task.status === "pending" || task.status === "claimed");

  const loadDetail = useCallback(async () => {
    if (!actionableTask) {
      setDetail(null);
      return;
    }
    const resp = await fetch(`${API_BASE}/review-tasks/${actionableTask.id}`, { headers: demoApiHeaders() });
    if (resp.ok) setDetail(await resp.json());
  }, [actionableTask]);

  useEffect(() => {
    loadDetail();
  }, [loadDetail]);

  const decide = async (action: string, payload: Record<string, unknown>) => {
    setBusy(true);
    try {
      const resp = await fetch(`${API_BASE}/review-tasks/${actionableTask?.id}/decision`, {
        method: "POST",
        headers: { ...demoApiHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify({ action, ...payload }),
      });
      const body = await resp.json().catch(() => ({}));
      if (resp.ok) {
        setToast("已提交，服务端已确认");
        setRejectOpen(false);
        setNote("");
        onChanged();
        setDetail(null);
      } else {
        setToast(`失败：${body?.error?.message ?? resp.status}`);
      }
    } finally {
      setBusy(false);
      setTimeout(() => setToast(""), 4000);
    }
  };

  const approve = () => decide("approve", {});
  const requestInfo = () => decide("request_info", { note: note || "需补充材料" });
  const reject = () => decide("reject", { reason_code: reasonCode, note });

  const canAct = role === "processor" && Boolean(actionableTask);

  return (
    <section className="panel full">
      <div className="panelhead">
        <h2>人工审核</h2>
        <small>{reviewTasks.length} 个任务</small>
      </div>
      <div className="sectionbody">
        {detail && detail.challenges.length > 0 && (
          <div className="finding" style={{ borderColor: "var(--border)", marginTop: 0 }}>
            <div className="top">
              <strong>AI 质疑（红队）</strong>
              {detail.scope_conflict && <span className="badge red">双通道冲突</span>}
            </div>
            {detail.challenges.map((c, i) => (
              <p key={i} style={{ marginTop: 4 }}>
                {c.risk === "high" ? "●" : c.risk === "mid" ? "◆" : "○"} {c.issue} —— {c.suggestion}
              </p>
            ))}
          </div>
        )}

        {canAct ? (
          <div className="reviewactions">
            <button className="btn primary" disabled={busy} onClick={approve}>通过</button>
            <button className="btn" disabled={busy} onClick={() => setRejectOpen(true)}>驳回</button>
            <button className="btn" disabled={busy} onClick={requestInfo}>退回补充</button>
            <span className="footnote" style={{ marginTop: 6, marginLeft: 6 }}>
              {actionableTask && `L${actionableTask.level} · ${TASK_STATUS_LABELS[actionableTask.status] ?? actionableTask.status}`}
            </span>
            {toast && <span style={{ width: "100%", fontSize: 12, color: "var(--green)" }}>{toast}</span>}
          </div>
        ) : null}

        {rejectOpen && canAct && (
          <div className="finding" style={{ marginTop: 12, borderColor: "var(--p0)" }}>
            <div className="top"><strong>驳回原因（必填）</strong></div>
            <div className="rowflex">
              {REASON_CODES.map((r) => (
                <button
                  key={r.value}
                  onClick={() => setReasonCode(r.value)}
                  className="btn"
                  style={{
                    borderColor: reasonCode === r.value ? "var(--p0)" : undefined,
                    color: reasonCode === r.value ? "var(--p0)" : undefined,
                  }}
                >
                  {r.label}
                </button>
              ))}
            </div>
            <textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="备注（可选，说明驳回依据）"
              className="reviewnote"
              rows={2}
              style={{ marginTop: 10 }}
            />
            <div className="reviewactions">
              <button className="btn danger" disabled={busy} onClick={reject}>确认驳回</button>
              <button className="btn" onClick={() => setRejectOpen(false)}>取消</button>
            </div>
          </div>
        )}

        <div className="divider" />

        {reviewTasks.length ? (
          reviewTasks.map((task) => (
            <div key={task.id} style={{ marginBottom: 18 }}>
              <strong>{task.level} 级审核 · {TASK_STATUS_LABELS[task.status] ?? task.status}</strong>
              <small style={{ display: "block" }}>{task.assignee} · {dateLabel(task.created_at)}</small>
              {task.decisions.length > 0 ? (
                <div className="history">
                  {task.decisions.map((decision, index) => (
                    <div key={index}>
                      <strong>{decision.actor}</strong> — {DECISION_LABELS[decision.action] ?? decision.action}
                      <br />
                      <small>{dateLabel(decision.created_at)}{decision.reason_code ? ` · ${decision.reason_code}` : ""}</small>
                      {decision.note && <p>{decision.note}</p>}
                    </div>
                  ))}
                </div>
              ) : (
                <p className="textblock" style={{ fontSize: 12, color: "var(--muted)" }}>尚未产生审核决定。</p>
              )}
            </div>
          ))
        ) : (
          <p className="textblock">尚未进入人工审核。</p>
        )}
      </div>
    </section>
  );
}
