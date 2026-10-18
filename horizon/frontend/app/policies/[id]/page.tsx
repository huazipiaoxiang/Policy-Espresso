import Link from "next/link";
import EmptyState from "@/components/EmptyState";
import EvidenceQuote from "@/components/EvidenceQuote";
import OriginalText from "@/components/OriginalText";
import PriorityBadge from "@/components/PriorityBadge";
import ScoreRadar from "@/components/ScoreRadar";
import ScopeChip from "@/components/ScopeChip";
import Topbar from "@/components/Topbar";
import TransmissionChain from "@/components/TransmissionChain";
import { getPolicy } from "@/lib/api";

export const dynamic = "force-dynamic";

const DIRECTION_LABEL: Record<string, { text: string; color: string }> = {
  positive: { text: "利好", color: "var(--ok)" },
  negative: { text: "利空", color: "var(--p0)" },
  mixed: { text: "双刃", color: "var(--warn)" },
  neutral: { text: "中性", color: "var(--text-2)" },
};

function hk(dateStr: string | null): string {
  if (!dateStr) return "—";
  const d = new Date(dateStr);
  if (Number.isNaN(d.getTime())) return dateStr;
  return new Intl.DateTimeFormat("zh-HK", { timeZone: "Asia/Hong_Kong", dateStyle: "medium" }).format(d);
}

// 政策详情（08 §3.2）：左原文 / 中结构化 / 右影响
export default async function PolicyDetailPage({ params }: { params: { id: string } }) {
  const policy = await getPolicy(params.id);
  if (!policy) {
    return (
      <>
        <Topbar />
        <main className="mx-auto max-w-content px-6 pt-[72px]">
          <EmptyState title="政策不存在或 API 未连接" hint="请确认后端已启动且该政策卡片存在" action="返回政策库" />
        </main>
      </>
    );
  }

  const assessment = policy.assessments[0];
  const judgement = policy.scope_judgements.find((j) => j.entity_id === "hsbc_cn") ?? policy.scope_judgements[0];
  const direction = DIRECTION_LABEL[assessment?.direction ?? "neutral"] ?? DIRECTION_LABEL.neutral;
  const spans = policy.evidence.map((e) => ({
    span_start: e.span_start,
    span_end: e.span_end,
    quote: e.quote,
    field_name: e.field_name,
    id: e.id,
  }));

  return (
    <>
      <Topbar />
      <main className="mx-auto max-w-content px-6 pb-16 pt-[72px]">
        <div className="mb-3 flex items-center gap-2 text-[12px] text-[var(--text-3)]">
          <Link href="/policies" className="hover:text-[var(--text-2)]">
            政策库
          </Link>
          <span>/</span>
          <span className="text-[var(--text-2)]">{policy.title}</span>
        </div>

        <div className="grid grid-cols-12 gap-4">
          {/* 左：原文 */}
          <section className="card col-span-12 p-4 xl:col-span-4">
            <div className="mb-2 flex items-center justify-between">
              <span className="section-label">原文</span>
              <a href={policy.url ?? "#"} target="_blank" rel="noreferrer" className="text-[11px] text-[var(--accent)] hover:underline">
                原文链接 ↗
              </a>
            </div>
            <h2 className="mb-1 font-serif text-[16px] font-semibold leading-6">{policy.title}</h2>
            <div className="mb-3 text-[11px] text-[var(--text-3)]">
              {policy.issuing_body || "发文机关未知"}
              {policy.doc_number ? ` · ${policy.doc_number}` : ""} · 发布 {hk(policy.published_at)} · 生效{" "}
              {hk(policy.effective_at)} · 截止 {hk(policy.expiry_at)}
            </div>
            <OriginalText text={policy.document?.content_text ?? "（原文未入库）"} spans={spans} />
          </section>

          {/* 中：结构化 */}
          <section className="card col-span-12 p-4 xl:col-span-4">
            <div className="mb-2 section-label">结构化抽取</div>
            <div className="mb-2 flex items-center gap-2">
              <span className="text-[12px] text-[var(--text-2)]">适用范围</span>
              <ScopeChip status={policy.target_entity_status} />
              {policy.foreign_bank_differential && (
                <span className="rounded-full border border-[var(--p0)] px-1.5 text-[10px] text-[var(--p0)]">
                  ⚠ 外资行差异
                </span>
              )}
              {judgement?.conflict && (
                <span className="rounded-full border border-[var(--warn)] px-1.5 text-[10px] text-[var(--warn)]" title="规则与 LLM 判定不一致，需人工复核">
                  ⚠ 双通道冲突
                </span>
              )}
            </div>
            {judgement?.llm_reason && (
              <p className="mb-3 rounded-md bg-[var(--surface-2)] px-2.5 py-1.5 text-[12px] leading-5 text-[var(--text-2)]">
                {judgement.llm_reason}
              </p>
            )}

            <div className="space-y-2 text-[12px]">
              <div>
                <div className="section-label">适用主体原文</div>
                <p className="font-serif text-[13px] text-[var(--text-2)]">
                  {policy.applicable_entities_text || "（未抽取到）"}
                </p>
              </div>
              <div>
                <div className="section-label">主题</div>
                <div className="mt-0.5 flex flex-wrap gap-1">
                  {policy.themes.map((t) => (
                    <span key={t} className="rounded-full bg-[var(--surface-2)] px-1.5 py-0.5 text-[10px] text-[var(--text-2)]">
                      #{t}
                    </span>
                  ))}
                  {policy.themes.length === 0 && <span className="text-[var(--text-3)]">—</span>}
                </div>
              </div>
              <div>
                <div className="section-label">金额</div>
                <ul className="mt-0.5 space-y-0.5">
                  {policy.amounts.map((a, i) => (
                    <li key={i} className="font-mono text-[12px] text-[var(--text-2)]">
                      {a.value} {a.unit} · {a.description}
                    </li>
                  ))}
                  {policy.amounts.length === 0 && <li className="text-[var(--text-3)]">—</li>}
                </ul>
              </div>
              <div>
                <div className="section-label">义务 / 激励</div>
                <ul className="mt-0.5 space-y-1">
                  {policy.obligations.map((o, i) => (
                    <li key={`o${i}`} className="text-[12px] text-[var(--text-2)]">
                      {o.actor}：{o.action}
                    </li>
                  ))}
                  {policy.incentives.map((n, i) => (
                    <li key={`i${i}`} className="text-[12px] text-[var(--ok)]">
                      {n.beneficiary} 可享：{n.benefit}
                    </li>
                  ))}
                  {policy.obligations.length + policy.incentives.length === 0 && (
                    <li className="text-[var(--text-3)]">—</li>
                  )}
                </ul>
              </div>
              <div className="text-[11px] text-[var(--text-3)]">置信度 {policy.confidence.toFixed(2)}</div>
            </div>

            <div className="mt-3">
              <div className="section-label">证据（{policy.evidence.length}）</div>
              <div className="mt-1 max-h-[280px] space-y-1 overflow-y-auto">
                {policy.evidence.map((e) => (
                  <EvidenceQuote
                    key={e.id}
                    id={e.id}
                    quote={e.quote}
                    spanStart={e.span_start}
                    spanEnd={e.span_end}
                    field={e.field_name}
                  />
                ))}
                {policy.evidence.length === 0 && (
                  <div className="text-[12px] text-[var(--text-3)]">暂无可定位证据（无证据不出结论）</div>
                )}
              </div>
            </div>
          </section>

          {/* 右：影响 */}
          <section className="card col-span-12 p-4 xl:col-span-4">
            <div className="mb-2 flex items-center gap-2">
              <span className="section-label">影响评估</span>
              <PriorityBadge level={policy.priority} score={policy.score_total} />
            </div>
            <div className="mb-2 flex items-baseline gap-3">
              <span className="font-mono text-[32px] font-semibold leading-9">{policy.score_total.toFixed(1)}</span>
              <span className="text-[12px]" style={{ color: direction.color }}>
                {direction.text}
              </span>
              <span className="text-[11px] text-[var(--text-3)]">置信度 {assessment?.confidence.toFixed(2) ?? "—"}</span>
            </div>
            {assessment ? (
              <>
                <ScoreRadar scores={assessment.scores} />
                <div className="mt-3">
                  <div className="section-label">传导链</div>
                  <TransmissionChain steps={assessment.transmission_chain} />
                </div>
                <div className="mt-3">
                  <div className="section-label">影响对象</div>
                  <div className="mt-1 text-[12px] text-[var(--text-2)]">
                    业务线：{assessment.affected.business_lines.join(" / ") || "—"}
                  </div>
                  <div className="text-[12px] text-[var(--text-2)]">
                    客群：{assessment.affected.segments.join("；") || "—"}
                  </div>
                  {assessment.affected.exposure_range && (
                    <div className="mt-1 font-mono text-[12px] text-[var(--accent)]">
                      暴露区间（估算）：{assessment.affected.exposure_range.low}–{assessment.affected.exposure_range.high}{" "}
                      {assessment.affected.exposure_range.unit}
                    </div>
                  )}
                </div>
                <div className="mt-3">
                  <div className="section-label">建议动作</div>
                  <ul className="mt-1 space-y-1">
                    {assessment.recommended_actions.map((a, i) => (
                      <li key={i} className="text-[12px] leading-5 text-[var(--text-2)]">
                        <span className="text-[var(--text-3)]">[{a.owner} · {a.deadline}]</span> {a.action}
                      </li>
                    ))}
                  </ul>
                </div>
                {assessment.case_links.length > 0 && (
                  <div className="mt-3">
                    <div className="section-label">相似案例</div>
                    <ul className="mt-1 space-y-1">
                      {assessment.case_links.map((c, i) => (
                        <li key={i} className="text-[12px] text-[var(--text-2)]">
                          <Link href="/cases" className="text-[var(--accent)] hover:underline">
                            {c.case_id}
                          </Link>{" "}
                          相似度 {c.similarity.toFixed(2)}
                          {c.takeaway ? ` — ${c.takeaway}` : ""}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                <div className="mt-3 text-[10px] text-[var(--text-3)]">
                  model: {assessment.model} · prompt: {assessment.prompt_version}
                </div>
              </>
            ) : (
              <div className="text-[12px] text-[var(--text-3)]">暂无评估（未触发分析或低置信被拦截）</div>
            )}
          </section>
        </div>
      </main>
    </>
  );
}
