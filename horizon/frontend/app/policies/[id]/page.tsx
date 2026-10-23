import Link from "next/link";
import EmptyState from "@/components/EmptyState";
import PolicyDetailClient from "@/components/PolicyDetailClient";
import { getPolicy } from "@/lib/api";

export const dynamic = "force-dynamic";

function hk(dateStr: string | null): string {
  if (!dateStr) return "—";
  const d = new Date(dateStr);
  if (Number.isNaN(d.getTime())) return dateStr;
  return new Intl.DateTimeFormat("zh-HK", { timeZone: "Asia/Hong_Kong", dateStyle: "medium" }).format(d);
}

function getRelevanceBadgeClass(relevance: string | undefined): string {
  if (!relevance) return "bg-[var(--surface-2)] text-[var(--text-3)]";
  if (relevance === "high") return "bg-[var(--ok)]/10 text-[var(--ok)]";
  if (relevance === "medium") return "bg-[var(--warn)]/10 text-[var(--warn)]";
  if (relevance === "low") return "bg-[var(--surface-2)] text-[var(--text-3)]";
  return "bg-[var(--surface-2)] text-[var(--text-3)]";
}

function getRelevanceLabel(relevance: string | undefined): string {
  if (relevance === "high") return "高相关";
  if (relevance === "medium") return "中相关";
  if (relevance === "low") return "低相关";
  if (relevance === "not_mentioned") return "未提及";
  if (relevance === "na") return "不适用";
  return relevance || "未评估";
}

function getStatusBadgeClass(status: string | undefined): string {
  if (!status) return "bg-[var(--surface-2)] text-[var(--text-3)]";
  if (/已批准|已完成|已发布/.test(status)) return "bg-[var(--ok)]/10 text-[var(--ok)]";
  if (/待|处理中|初审|复核|审核中/.test(status)) return "bg-[var(--warn)]/10 text-[var(--warn)]";
  if (/失败|拒绝|退回/.test(status)) return "bg-[var(--danger)]/10 text-[var(--danger)]";
  return "bg-[var(--surface-2)] text-[var(--text-2)]";
}

export default async function PolicyDetailPage({ params }: { params: { id: string } }) {
  const policy = await getPolicy(params.id);
  if (!policy) {
    return (
      <main className="mx-auto max-w-content px-6 py-6">
        <EmptyState title="政策不存在或 API 未连接" hint="请确认后端已启动且该政策卡片存在" action="返回政策库" />
      </main>
    );
  }

  const assessment = policy.assessments[0];
  const judgement = policy.scope_judgements.find((j) => j.entity_id === "hsbc_cn") ?? policy.scope_judgements[0];

  return (
    <main className="mx-auto max-w-content px-6 pb-16 py-6">
      <div className="mb-3 flex items-center gap-2 text-[12px] text-[var(--text-3)]">
        <Link href="/policies" className="hover:text-[var(--text-2)]">
          政策库
        </Link>
        <span>/</span>
        <span className="text-[var(--text-2)]">{policy.title}</span>
      </div>

      <h1 className="mb-4 text-[20px] font-semibold">{policy.title}</h1>

      <div className="mb-4 grid grid-cols-4 gap-3 rounded-lg border border-[var(--border)] bg-[var(--surface)] p-3">
        <div>
          <div className="mb-1 text-[10px] uppercase tracking-wide text-[var(--text-3)]">相关性</div>
          <span className={`inline-block rounded-full px-2 py-0.5 text-[11px] ${getRelevanceBadgeClass(policy.target_entity_status)}`}>
            {getRelevanceLabel(policy.target_entity_status)}
          </span>
        </div>
        <div>
          <div className="mb-1 text-[10px] uppercase tracking-wide text-[var(--text-3)]">AI 分析</div>
          <span className={`inline-block rounded-full px-2 py-0.5 text-[11px] ${assessment ? "bg-[var(--ok)]/10 text-[var(--ok)]" : "bg-[var(--surface-2)] text-[var(--text-3)]"}`}>
            {assessment ? "已完成" : "未开始"}
          </span>
        </div>
        <div>
          <div className="mb-1 text-[10px] uppercase tracking-wide text-[var(--text-3)]">人工审核</div>
          <span className={`inline-block rounded-full px-2 py-0.5 text-[11px] ${getStatusBadgeClass(policy.status)}`}>
            {policy.status || "待审核"}
          </span>
        </div>
        <div>
          <div className="mb-1 text-[10px] uppercase tracking-wide text-[var(--text-3)]">发布状态</div>
          <span className="inline-block rounded-full bg-[var(--surface-2)] px-2 py-0.5 text-[11px] text-[var(--text-3)]">
            未发布
          </span>
        </div>
      </div>

      <div className="grid grid-cols-12 gap-4">
        <div className="col-span-12 space-y-4 xl:col-span-7">
          <section className="card p-4">
            <div className="mb-3 section-label">Policy Information</div>
            <div className="grid grid-cols-3 gap-3 text-[12px]">
              <div>
                <div className="text-[var(--text-3)]">发文机关</div>
                <div className="mt-0.5 text-[var(--text)]">{policy.issuing_body || "—"}</div>
              </div>
              <div>
                <div className="text-[var(--text-3)]">市场</div>
                <div className="mt-0.5 text-[var(--text)]">{policy.jurisdiction || "—"}</div>
              </div>
              <div>
                <div className="text-[var(--text-3)]">文号</div>
                <div className="mt-0.5 font-mono text-[var(--text)]">{policy.doc_number || "—"}</div>
              </div>
              <div>
                <div className="text-[var(--text-3)]">发布时间</div>
                <div className="mt-0.5 text-[var(--text)]">{hk(policy.published_at)}</div>
              </div>
              <div>
                <div className="text-[var(--text-3)]">生效时间</div>
                <div className="mt-0.5 text-[var(--text)]">{hk(policy.effective_at)}</div>
              </div>
              <div>
                <div className="text-[var(--text-3)]">优先级</div>
                <div className="mt-0.5">
                  <span className={`inline-block rounded-full px-2 py-0.5 text-[11px] ${
                    policy.priority === "P0" || policy.priority === "P1"
                      ? "bg-[var(--danger)]/10 text-[var(--danger)]"
                      : policy.priority === "P2"
                        ? "bg-[var(--warn)]/10 text-[var(--warn)]"
                        : "bg-[var(--ok)]/10 text-[var(--ok)]"
                  }`}>
                    {policy.priority}
                  </span>
                </div>
              </div>
            </div>

            <div className="my-3 border-t border-[var(--border)]" />

            <div className="mb-2 text-[12px]">
              <div className="mb-1 text-[var(--text-3)]">主题标签</div>
              <div className="flex flex-wrap gap-1">
                {policy.themes.map((t) => (
                  <span key={t} className="rounded-full bg-[var(--surface-2)] px-2 py-0.5 text-[11px] text-[var(--text-2)]">
                    #{t}
                  </span>
                ))}
                {policy.themes.length === 0 && <span className="text-[var(--text-3)]">—</span>}
              </div>
            </div>

            <div className="my-3 border-t border-[var(--border)]" />

            <div className="mb-2">
              <div className="mb-1 text-[12px] text-[var(--text-3)]">AI 政策摘要</div>
              <p className="text-[13px] leading-6 text-[var(--text-2)]">
                {policy.summary_zh || "（未生成摘要）"}
              </p>
            </div>

            {assessment && (
              <>
                <div className="my-3 border-t border-[var(--border)]" />
                <div className="mb-2">
                  <div className="mb-1 text-[12px] text-[var(--text-3)]">AI 置信度</div>
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-[20px] font-semibold">{(assessment.confidence * 100).toFixed(0)}%</span>
                    <span className={`rounded-full px-2 py-0.5 text-[11px] ${
                      assessment.confidence >= 0.85
                        ? "bg-[var(--ok)]/10 text-[var(--ok)]"
                        : assessment.confidence >= 0.6
                          ? "bg-[var(--warn)]/10 text-[var(--warn)]"
                          : "bg-[var(--danger)]/10 text-[var(--danger)]"
                    }`}>
                      {assessment.confidence >= 0.85 ? "High" : assessment.confidence >= 0.6 ? "Medium" : "Low"}
                    </span>
                  </div>
                  <p className="mt-1 text-[11px] text-[var(--text-3)]">
                    置信度反映 AI 对抽取结论的把握程度，高置信度不等于已验证或可自动批准
                  </p>
                </div>
              </>
            )}
          </section>

          <section className="card p-4">
            <div className="mb-3 flex items-center justify-between">
              <span className="section-label">原文</span>
              <a href={policy.url ?? "#"} target="_blank" rel="noreferrer" className="text-[11px] text-[var(--accent)] hover:underline">
                原文链接 ↗
              </a>
            </div>
            <div className="max-h-[400px] overflow-y-auto rounded-md bg-[var(--surface-2)] p-3 text-[12px] leading-5 text-[var(--text-2)]">
              {policy.document?.content_text || "（原文未入库）"}
            </div>
          </section>

          {assessment && (
            <section className="card p-4">
              <div className="mb-3">
                <div className="section-label">AI Conclusions and Arguments</div>
                <div className="mt-1 text-[11px] text-[var(--text-3)]">逐条验证，证据优先</div>
              </div>

              <div className="mb-3">
                <div className="mb-2 text-[12px] text-[var(--text-3)]">影响评估</div>
                <div className="flex items-baseline gap-3">
                  <span className="font-mono text-[28px] font-semibold">{policy.score_total.toFixed(1)}</span>
                  <span className="text-[12px] text-[var(--text-2)]">
                    {assessment.direction === "positive" ? "利好" : assessment.direction === "negative" ? "利空" : assessment.direction === "mixed" ? "双刃" : "中性"}
                  </span>
                </div>
              </div>

              <div className="mb-3">
                <div className="mb-2 text-[12px] text-[var(--text-3)]">影响对象</div>
                <div className="text-[12px] text-[var(--text-2)]">
                  业务线：{assessment.affected.business_lines.join(" / ") || "—"}
                </div>
                <div className="text-[12px] text-[var(--text-2)]">
                  客群：{assessment.affected.segments.join("；") || "—"}
                </div>
              </div>

              {policy.evidence.length > 0 && (
                <div>
                  <div className="mb-2 text-[12px] text-[var(--text-3)]">证据（{policy.evidence.length}）</div>
                  <div className="space-y-2">
                    {policy.evidence.map((e) => (
                      <div key={e.id} className="rounded-md border border-[var(--border)] bg-[var(--surface-2)] p-2">
                        <div className="mb-1 text-[10px] uppercase tracking-wide text-[var(--text-3)]">{e.field_name}</div>
                        <blockquote className="border-l-2 border-[var(--accent)] pl-2 text-[12px] italic text-[var(--text-2)]">
                          {e.quote}
                        </blockquote>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </section>
          )}
        </div>

        <div className="col-span-12 space-y-4 xl:col-span-5">
          <PolicyDetailClient policyId={policy.id} priority={policy.priority} status={policy.status} />

          <section className="card p-4">
            <div className="mb-3 section-label">Source & Version</div>
            <div className="space-y-2 text-[12px]">
              <div>
                <div className="text-[var(--text-3)]">来源</div>
                <div className="mt-0.5 text-[var(--text)]">{policy.issuing_body || "—"}</div>
              </div>
              <div>
                <div className="text-[var(--text-3)]">文档类型</div>
                <div className="mt-0.5 text-[var(--text)]">Regulatory Policy</div>
              </div>
              <div>
                <div className="text-[var(--text-3)]">版本</div>
                <div className="mt-0.5 font-mono text-[var(--text)]">V1.0</div>
              </div>
            </div>
          </section>

          {judgement && (
            <section className="card p-4">
              <div className="mb-3 section-label">相关性判定</div>
              <div className="mb-2 flex items-center gap-2">
                <span className={`rounded-full px-2 py-0.5 text-[11px] ${getRelevanceBadgeClass(policy.target_entity_status)}`}>
                  {getRelevanceLabel(policy.target_entity_status)}
                </span>
                {judgement.conflict && (
                  <span className="rounded-full border border-[var(--warn)] px-1.5 text-[10px] text-[var(--warn)]">
                    ⚠ 双通道冲突
                  </span>
                )}
              </div>
              {judgement.llm_reason && (
                <p className="rounded-md bg-[var(--surface-2)] px-2.5 py-1.5 text-[12px] leading-5 text-[var(--text-2)]">
                  {judgement.llm_reason}
                </p>
              )}
            </section>
          )}
        </div>
      </div>
    </main>
  );
}
