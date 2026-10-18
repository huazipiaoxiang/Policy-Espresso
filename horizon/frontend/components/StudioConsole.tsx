"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import type { CorpusDocItem, ProposalDetail } from "@/lib/api";

const STATUS_STYLE: Record<string, { label: string; color: string }> = {
  pass: { label: "PASS", color: "var(--ok)" },
  warn: { label: "WARN · 需立法/审批程序", color: "var(--warn)" },
  fail: { label: "FAIL · 与现行规定冲突，禁止外发", color: "var(--danger)" },
};

// 政策 2.0 工作台（08 §3.6）：主题树 + 时间轴 + 建议书编辑区
export default function StudioConsole({
  projects,
  corpus,
  proposal,
}: {
  projects: { id: string; name: string; theme: string; status: string; created_at: string }[];
  corpus: CorpusDocItem[];
  proposal: ProposalDetail | null;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [projectId, setProjectId] = useState(projects[0]?.id ?? "");
  const [proposalId, setProposalId] = useState(proposal?.id ?? "");

  const call = async (url: string, body?: unknown) => {
    setBusy(true);
    try {
      const resp = await fetch(`/api/proxy${url}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: body ? JSON.stringify(body) : undefined,
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        setMessage(`失败：${data?.error?.message ?? resp.status}`);
      } else if (data.proposal_id) {
        setProposalId(data.proposal_id);
        setMessage(`已生成 v${data.version}，共 ${data.proposals} 条建议`);
      } else {
        setMessage(`${data.role ?? ""} ${data.approve ? "通过" : "驳回"}已记录`);
      }
      router.refresh();
    } finally {
      setBusy(false);
    }
  };

  const boundaryOf = (pid: string) =>
    proposal?.boundary_check?.items?.find((b) => b.proposal_id === pid);

  return (
    <div className="space-y-4">
      {/* 免责声明常驻条 */}
      <div className="rounded-card border border-[var(--warn)] bg-[var(--warn)]/10 px-4 py-2 text-[12px] text-[var(--warn)]">
        ⚠ AI 辅助生成，仅供内部研讨，未经政策与合规审核不得对外。
      </div>

      <div className="grid grid-cols-12 gap-4">
        {/* 左：主题树 + 项目 */}
        <section className="card col-span-3 p-3">
          <div className="section-label">Studio 项目</div>
          <ul className="mt-1 space-y-1">
            {projects.map((p) => (
              <li key={p.id}>
                <button
                  onClick={() => setProjectId(p.id)}
                  className={`w-full rounded-md px-2 py-1.5 text-left text-[12px] ${
                    projectId === p.id ? "bg-[var(--surface-2)] text-[var(--text)]" : "text-[var(--text-2)]"
                  }`}
                >
                  {p.name}
                  <span className="ml-1 text-[10px] text-[var(--text-3)]">{p.status}</span>
                </button>
              </li>
            ))}
          </ul>
          <button
            disabled={busy || !projectId}
            onClick={() => call(`/studio/projects/${projectId}/generate`)}
            className="mt-3 w-full rounded-btn bg-[var(--accent)] px-3 py-1.5 text-[12px] font-medium text-[var(--bg)] disabled:opacity-50"
          >
            {busy ? "生成中…" : "生成建议书（P6）"}
          </button>
          {message && <div className="mt-2 text-[11px] text-[var(--accent)]">{message}</div>}

          <div className="mt-4">
            <div className="section-label">主题（语料覆盖）</div>
            <div className="mt-1 flex flex-wrap gap-1">
              {[...new Set(corpus.flatMap((d) => d.themes))].map((t) => (
                <span key={t} className="rounded-full bg-[var(--surface-2)] px-1.5 py-0.5 text-[10px] text-[var(--text-2)]">#{t}</span>
              ))}
            </div>
          </div>
        </section>

        {/* 中：条款演化时间轴 */}
        <section className="card col-span-3 p-3">
          <div className="section-label">条款演化时间轴</div>
          <ol className="mt-2 space-y-2">
            {corpus.map((d) => (
              <li key={d.doc_id} className="border-l-2 border-[var(--border-strong)] pl-2">
                <div className="font-mono text-[10px] text-[var(--text-3)]">{d.published_at}</div>
                <div className="text-[12px] leading-4 text-[var(--text)]">{d.title}</div>
                <div className="text-[10px] text-[var(--text-3)]">
                  {d.issuing_bodies.join("、")} · {d.doc_number}
                </div>
                <span className={`text-[10px] ${d.effective ? "text-[var(--ok)]" : "text-[var(--danger)]"}`}>
                  {d.validity}
                </span>
              </li>
            ))}
          </ol>
        </section>

        {/* 右：建议书 */}
        <section className="col-span-6 space-y-3">
          {proposal ? (
            <>
              <div className="card p-4">
                <div className="mb-1 flex items-center gap-2">
                  <span className="text-[14px] font-semibold">{proposal.sections.title}</span>
                  <span className="ml-auto font-mono text-[11px] text-[var(--text-3)]">v{proposal.version}</span>
                </div>
                <div className="mb-3 space-y-1">
                  {proposal.sections.baseline.map((b, i) => (
                    <div key={i} className="text-[12px] text-[var(--text-2)]">
                      <span className="text-[var(--text-3)]">[{b.theme}]</span> {b.current_state}
                    </div>
                  ))}
                </div>
                {proposalId && (
                  <div className="flex gap-2">
                    <button
                      onClick={() => call(`/studio/proposals/${proposalId}/review`, { role: "expert", approve: true })}
                      className="rounded-btn border border-[var(--ok)] px-3 py-1 text-[12px] text-[var(--ok)]"
                    >
                      政策专家通过
                    </button>
                    <button
                      onClick={() => call(`/studio/proposals/${proposalId}/review`, { role: "compliance", approve: true })}
                      className="rounded-btn border border-[var(--ok)] px-3 py-1 text-[12px] text-[var(--ok)]"
                    >
                      合规通过
                    </button>
                    <span className="self-center text-[11px] text-[var(--text-3)]">双签后才可导出对外版本</span>
                  </div>
                )}
              </div>

              {proposal.sections.proposals.map((p) => {
                const bc = boundaryOf(p.id);
                const style = STATUS_STYLE[bc?.status ?? "pass"] ?? STATUS_STYLE.pass;
                return (
                  <article key={p.id} className="card p-4">
                    <div className="mb-1 flex flex-wrap items-center gap-2">
                      <span className="font-mono text-[12px] text-[var(--accent)]">{p.id}</span>
                      <span className="text-[13px] font-semibold">#{p.theme}</span>
                      <span className="rounded-full bg-[var(--surface-2)] px-1.5 py-0.5 text-[10px] text-[var(--text-2)]">{p.tier}</span>
                      <span className="ml-auto text-[10px]" style={{ color: style.color }}>
                        {bc?.status ? `${style.label}${bc.issue ? ` · ${bc.issue}` : ""}` : ""}
                      </span>
                    </div>
                    <div className="space-y-1.5 text-[12px] leading-5">
                      <div>
                        <span className="section-label">现行依据：</span>
                        {p.current_basis.map((b, i) => (
                          <div key={i} className="font-serif text-[12px] text-[var(--text-2)]">
                            《{b.doc}》{b.clause}：“{b.quote}”
                          </div>
                        ))}
                      </div>
                      <div><span className="section-label">不冲突论证：</span><span className="text-[var(--text-2)]">{p.non_conflict_argument}</span></div>
                      <div><span className="section-label">拟条文：</span><span className="font-serif text-[var(--text)]">{p.draft_clause}</span></div>
                      <div>
                        <span className="section-label">影响：</span>
                        <span className="text-[var(--text-2)]">对港：{p.impact.on_hk}；对汇丰：{p.impact.on_hsbc}；对行业：{p.impact.on_industry}</span>
                      </div>
                      <div>
                        <span className="section-label">风险与缓释：</span>
                        <span className="text-[var(--text-2)]">
                          {p.risks.map((r) => `${r.risk}（${r.likelihood}）→ ${r.mitigation}`).join("；")}
                        </span>
                      </div>
                      <div><span className="section-label">KPI：</span><span className="text-[var(--text-2)]">{p.kpis.join("；")}</span></div>
                    </div>
                  </article>
                );
              })}

              {proposal.reviewer_notes && (
                <div className="card p-3 text-[11px] leading-5 text-[var(--text-3)]">
                  <div className="section-label">审核记录</div>
                  <pre className="whitespace-pre-wrap font-sans">{proposal.reviewer_notes}</pre>
                </div>
              )}
            </>
          ) : (
            <div className="card p-8 text-center text-[12px] text-[var(--text-3)]">
              选择项目后点击“生成建议书”（基于 CEPA/大湾区语料，P6 链路）
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
