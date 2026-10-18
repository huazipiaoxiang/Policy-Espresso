import Link from "next/link";
import EmptyState from "@/components/EmptyState";
import Topbar from "@/components/Topbar";
import { getCase } from "@/lib/api";

export const dynamic = "force-dynamic";

// 案例详情（08 §3.4）：时间轴 + 启示引用块
export default async function CaseDetailPage({ params }: { params: { id: string } }) {
  const item = await getCase(params.id);
  if (!item) {
    return (
      <>
        <Topbar />
        <main className="mx-auto max-w-content px-6 pt-[72px]">
          <EmptyState title="案例不存在或 API 未连接" hint="请确认后端已启动" action="返回案例库" />
        </main>
      </>
    );
  }

  const steps = [
    { label: "政策出台", text: item.policy_summary },
    { label: "影响", text: item.impact },
    { label: "我方应对", text: item.hsbc_response },
  ];

  return (
    <>
      <Topbar />
      <main className="mx-auto max-w-content px-6 pb-10 pt-[72px]">
        <div className="mb-3 flex items-center gap-2 text-[12px] text-[var(--text-3)]">
          <Link href="/cases" className="hover:text-[var(--text-2)]">案例库</Link>
          <span>/</span>
          <span className="text-[var(--text-2)]">{item.title}</span>
        </div>

        <article className="card p-5">
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <h1 className="text-[16px] font-semibold">{item.title}</h1>
            <span className="font-mono text-[12px] text-[var(--text-3)]">{item.year}</span>
            {(item.themes ?? []).map((t) => (
              <span key={t} className="rounded-full bg-[var(--surface-2)] px-1.5 py-0.5 text-[10px] text-[var(--text-2)]">#{t}</span>
            ))}
          </div>

          <ol className="space-y-3">
            {steps.map((s, i) => (
              <li key={i} className="flex gap-3">
                <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-[var(--accent)] font-mono text-[10px] text-[var(--accent)]">
                  {i + 1}
                </span>
                <div>
                  <div className="section-label">{s.label}</div>
                  <p className="font-serif text-[13px] leading-6 text-[var(--text-2)]">{s.text || "—"}</p>
                </div>
              </li>
            ))}
          </ol>

          <div className="mt-4">
            <div className="section-label">启示</div>
            <ul className="mt-1 space-y-1">
              {(item.lessons ?? []).map((l, i) => (
                <li key={i} className="border-l-2 border-[var(--accent)] pl-2 font-serif text-[13px] leading-6 text-[var(--text)]">
                  {l}
                </li>
              ))}
              {(item.lessons ?? []).length === 0 && <li className="text-[12px] text-[var(--text-3)]">—</li>}
            </ul>
          </div>

          {(item.source_refs ?? []).length > 0 && (
            <div className="mt-4 text-[11px] text-[var(--text-3)]">
              来源：{JSON.stringify(item.source_refs)}
            </div>
          )}
        </article>
      </main>
    </>
  );
}
