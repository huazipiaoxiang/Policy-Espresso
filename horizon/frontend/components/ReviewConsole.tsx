"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import Countdown from "./Countdown";
import PriorityBadge from "./PriorityBadge";
import ScopeChip from "./ScopeChip";

export interface ReviewTaskItem {
  id: string;
  policy_id: string;
  policy_title: string;
  priority: string;
  score_total: number;
  level: number;
  assignee: string;
  status: string;
  sla_due_at: string | null;
  target_entity_status: string;
  foreign_bank_differential: boolean;
}

export interface ReviewTaskDetail {
  task: ReviewTaskItem;
  policy: {
    id: string;
    title: string;
    summary_zh: string;
    priority: string;
    status: string;
    target_entity_status: string;
    foreign_bank_differential: boolean;
    applicable_entities_text: string;
    effective_at: string | null;
  };
  assessment: {
    scores: Record<string, { score: number | null; reason: string }>;
    direction: string;
    score_total: number;
    priority: string;
    transmission_chain: string[];
    affected: { business_lines: string[]; segments: string[]; exposure_range: unknown };
    recommended_actions: { owner: string; action: string; deadline: string }[];
    case_links: { case_id: string; similarity: number; takeaway: string }[];
    confidence: number;
  } | null;
  evidence_count: number;
  scope_conflict: boolean;
  challenges: { risk: string; issue: string; suggestion: string }[];
  previous_decisions: { actor: string; action: string; reason_code: string | null; note: string; created_at: string }[];
}

const REASON_CODES = [
  { value: "insufficient_evidence", label: "证据不足" },
  { value: "impact_misjudged", label: "影响误判" },
  { value: "scope_misjudged", label: "适用性误判" },
  { value: "bad_wording", label: "表述不当" },
  { value: "duplicate", label: "重复" },
  { value: "other", label: "其他" },
];

// 审核台（08 §3.3）：左列表 + 右详情；J/K 移动，Enter 打开，a 通过，x 驳回
const TABS = [
  { value: "my", label: "我的任务" },
  { value: "all", label: "全部记录" },
  { value: "second", label: "待复审" },
  { value: "supervisor", label: "待主管签批" },
  { value: "completed", label: "已完成" },
];

export default function ReviewConsole({ initialTasks }: { initialTasks: ReviewTaskItem[] }) {
  const router = useRouter();
  const [activeTab, setActiveTab] = useState("my");
  const [tasks, setTasks] = useState(initialTasks);
  const [activeId, setActiveId] = useState(initialTasks[0]?.id ?? "");
  const [detail, setDetail] = useState<ReviewTaskDetail | null>(null);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [reasonCode, setReasonCode] = useState("insufficient_e_evidence");
  const [note, setNote] = useState("");
  const [toast, setToast] = useState("");

  const loadDetail = useCallback(async (taskId: string) => {
    const resp = await fetch(`/api/proxy/review-tasks/${taskId}`);
    if (resp.ok) setDetail(await resp.json());
  }, []);

  useEffect(() => {
    if (activeId) loadDetail(activeId);
  }, [activeId, loadDetail]);

  const act = async (fn: () => Promise<Response>) => {
    const resp = await fn();
    if (resp.ok) {
      setToast("已提交，服务端已确认");
      router.refresh();
      setTimeout(() => setToast(""), 2500);
    } else {
      const body = await resp.json().catch(() => ({}));
      setToast(`失败：${body?.error?.message ?? resp.status}`);
      setTimeout(() => setToast(""), 4000);
    }
  };

  const approve = (taskId: string) =>
    act(() => fetch(`/api/proxy/review-tasks/${taskId}/decision`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "approve" }),
    }));

  const requestInfo = (taskId: string) =>
    act(() => fetch(`/api/proxy/review-tasks/${taskId}/decision`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "request_info", note: note || "需补充材料" }),
    }));

  const reject = (taskId: string) =>
    act(() => fetch(`/api/proxy/review-tasks/${taskId}/decision`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "reject", reason_code: reasonCode, note }),
    })).then(() => setRejectOpen(false));

  // 键盘：j/k 移动，Enter 打开，a 通过，x 驳回
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      const idx = tasks.findIndex((t) => t.id === activeId);
      if (e.key === "j" || e.key === "ArrowDown") {
        e.preventDefault();
        setActiveId(tasks[Math.min(idx + 1, tasks.length - 1)]?.id ?? activeId);
      } else if (e.key === "k" || e.key === "ArrowUp") {
        e.preventDefault();
        setActiveId(tasks[Math.max(idx - 1, 0)]?.id ?? activeId);
      } else if (e.key === "Enter" && activeId) {
        router.push(`/policies/${tasks[idx]?.policy_id}`);
      } else if (e.key === "a" && activeId) {
        approve(activeId);
      } else if (e.key === "x" && activeId) {
        setRejectOpen(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  if (tasks.length === 0) {
    return (
      <div className="card p-8 text-center">
        <div className="text-[13px] text-[var(--text-2)]">待审队列已清空</div>
        <div className="mt-1 text-[12px] text-[var(--text-3)]">新政策分析完成后将自动进入队列（SLA：P0 4h / P1 24h）</div>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-12 gap-4">
      {/* 左：任务列表 */}
      <section className="card col-span-3 overflow-hidden">
        <div className="flex h-10 items-center border-b border-[var(--border)] px-3">
          <span className="section-label">待审（{tasks.length}）</span>
          <span className="ml-auto text-[10px] text-[var(--text-3)]">J/K 切换</span>
        </div>
        <div className="flex border-b border-[var(--border)]">
          {TABS.map((tab) => (
            <button
              key={tab.value}
              onClick={() => setActiveTab(tab.value)}
              className={`flex-1 px-2 py-2 text-[11px] transition ${
                activeTab === tab.value
                  ? "border-b-2 border-[var(--accent)] text-[var(--accent)]"
                  : "text-[var(--text-3)] hover:text-[var(--text-2)]"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
        <ul className="max-h-[560px] overflow-y-auto">
          {tasks.map((t) => (
            <li key={t.id}>
              <button
                onClick={() => setActiveId(t.id)}
                className={`flex w-full flex-col items-start gap-0.5 border-b border-[var(--border)] px-3 py-2 text-left ${
                  t.id === activeId ? "bg-[var(--surface-2)]" : "hover:bg-[var(--surface-2)]"
                }`}
              >
                <span className="flex w-full items-center gap-1.5">
                  <PriorityBadge level={t.priority} score={t.score_total} />
                  <span className="ml-auto"><Countdown dueAt={t.sla_due_at} /></span>
                </span>
                <span className="line-clamp-2 text-[12px] leading-4">{t.policy_title}</span>
                <span className="text-[10px] text-[var(--text-3)]">
                  L{t.level} · {t.status} · {t.target_entity_status}
                  {t.foreign_bank_differential ? " · ⚠外资行差异" : ""}
                </span>
              </button>
            </li>
          ))}
        </ul>
      </section>

      {/* 右：详情 */}
      <section className="col-span-9 space-y-3">
        {detail ? (
          <>
            <div className="card p-4">
              <div className="mb-2 flex items-center gap-2">
                <span className="text-[14px] font-semibold">{detail.policy.title}</span>
                <ScopeChip status={detail.policy.target_entity_status} />
                {detail.policy.foreign_bank_differential && (
                  <span className="rounded-full border border-[var(--p0)] px-1.5 text-[10px] text-[var(--p0)]">⚠ 外资行差异</span>
                )}
                {detail.scope_conflict && (
                  <span className="rounded-full border border-[var(--warn)] px-1.5 text-[10px] text-[var(--warn)]">⚠ 双通道冲突</span>
                )}
                <span className="ml-auto text-[11px] text-[var(--text-3)]">
                  状态 {detail.policy.status} · L{detail.task.level} · 证据 {detail.evidence_count} 条
                </span>
              </div>
              <p className="font-serif text-[13px] leading-6 text-[var(--text-2)]">{detail.policy.summary_zh}</p>
              {detail.assessment && (
                <div className="mt-2 grid grid-cols-2 gap-2 text-[12px] text-[var(--text-2)]">
                  <div>方向：{detail.assessment.direction} · 综合分 {detail.assessment.score_total} · 置信度 {detail.assessment.confidence}</div>
                  <div>业务线：{detail.assessment.affected.business_lines.join(" / ")}</div>
                </div>
              )}
              {detail.previous_decisions.length > 0 && (
                <div className="mt-2 rounded-md bg-[var(--surface-2)] px-2.5 py-1.5 text-[11px] text-[var(--text-3)]">
                  上一审核意见：{detail.previous_decisions.at(-1)?.actor} ·{" "}
                  {detail.previous_decisions.at(-1)?.action} · {detail.previous_decisions.at(-1)?.note || "无备注"}
                </div>
              )}
            </div>

            {/* AI 质疑面板（防橡皮图章） */}
            <div className="card p-4">
              <div className="section-label">AI 质疑（红队）</div>
              <ul className="mt-1 space-y-1">
                {detail.challenges.map((c, i) => (
                  <li key={i} className="flex gap-2 text-[12px] leading-5">
                    <span className={c.risk === "high" ? "text-[var(--p0)]" : c.risk === "mid" ? "text-[var(--warn)]" : "text-[var(--ok)]"}>
                      {c.risk === "high" ? "●" : c.risk === "mid" ? "◆" : "○"}
                    </span>
                    <span className="text-[var(--text-2)]">{c.issue} —— <span className="text-[var(--text-3)]">{c.suggestion}</span></span>
                  </li>
                ))}
              </ul>
            </div>

            {/* 动作栏 */}
            <div className="card flex flex-wrap items-center gap-2 p-3">
              <button
                onClick={() => approve(detail.task.id)}
                className="rounded-btn bg-[var(--accent)] px-4 py-1.5 text-[13px] font-medium text-[var(--bg)]"
              >
                通过（a）
              </button>
              <button
                onClick={() => setRejectOpen(true)}
                className="rounded-btn border border-[var(--border-strong)] px-4 py-1.5 text-[13px] text-[var(--text-2)]"
              >
                驳回（x）
              </button>
              <button
                onClick={() => requestInfo(detail.task.id)}
                className="rounded-btn border border-[var(--border)] px-4 py-1.5 text-[13px] text-[var(--text-2)]"
              >
                退回补充
              </button>
              <span className="ml-auto text-[11px] text-[var(--text-3)]">快捷键：j/k 移动 · Enter 打开政策 · a 通过 · x 驳回</span>
              {toast && <span className="w-full text-[12px] text-[var(--accent)]">{toast}</span>}
            </div>

            {rejectOpen && (
              <div className="card space-y-2 p-4">
                <div className="section-label">驳回原因（必填）</div>
                <div className="flex flex-wrap gap-2">
                  {REASON_CODES.map((r) => (
                    <button
                      key={r.value}
                      onClick={() => setReasonCode(r.value)}
                      className={`rounded-btn border px-2.5 py-1 text-[12px] ${
                        reasonCode === r.value
                          ? "border-[var(--p0)] text-[var(--p0)]"
                          : "border-[var(--border)] text-[var(--text-2)]"
                      }`}
                    >
                      {r.label}
                    </button>
                  ))}
                </div>
                <textarea
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  placeholder="备注（可选，说明驳回依据）"
                  className="w-full rounded-btn border border-[var(--border)] bg-[var(--surface-2)] p-2 text-[12px]"
                  rows={2}
                />
                <div className="flex gap-2">
                  <button onClick={() => reject(detail.task.id)} className="rounded-btn bg-[var(--p0)] px-4 py-1.5 text-[13px] text-white">
                    确认驳回
                  </button>
                  <button onClick={() => setRejectOpen(false)} className="rounded-btn border border-[var(--border)] px-4 py-1.5 text-[13px] text-[var(--text-2)]">
                    取消
                  </button>
                </div>
              </div>
            )}
          </>
        ) : (
          <div className="card p-8 text-center text-[12px] text-[var(--text-3)]">加载中…</div>
        )}
      </section>
    </div>
  );
}
