import Link from "next/link";
import { getCases, getOverview } from "@/lib/api";

export const dynamic = "force-dynamic";

const OUTCOME_LABEL: Record<string, { text: string; color: string }> = {
  win: { text: "我赢了", color: "var(--ok)" },
  lose: { text: "我输了", color: "var(--p0)" },
  partial: { text: "部分改善", color: "var(--warn)" },
};

// 案例库（08 §3.4）
export default async function CasesPage({ searchParams }: { searchParams: { q?: string; business_line?: string } }) {
  const [overview, cases] = await Promise.all([
    getOverview(),
    getCases(
      `${searchParams.q ? `&q=${encodeURIComponent(searchParams.q)}` : ""}${
        searchParams.business_line ? `&business_line=${searchParams.business_line}` : ""
      }`,
    ),
  ]);
  const items = cases?.items ?? [];

  return (
    <main className="mx-auto max-w-content px-6 pb-10 py-6">
        <form className="mb-4 flex items-center gap-2" action="/cases">
          <input
            name="q"
            defaultValue={searchParams.q ?? ""}
            placeholder="语义 + 关键词混合搜索，如：外资行被排除的贴息政策"
            className="h-9 w-[420px] rounded-btn border border-[var(--border)] bg-[var(--surface-2)] px-3 text-[12px] text-[var(--text)] placeholder:text-[var(--text-3)]"
          />
          <button type="submit" className="rounded-btn bg-[var(--accent)] px-4 py-1.5 text-[12px] font-medium text-[var(--bg)]">
            搜索
          </button>
          <span className="text-[11px] text-[var(--text-3)]">支持按业务线过滤：CMB / GBM / WPB / GTB / Insurance</span>
        </form>

        <div className="grid grid-cols-2 gap-4 xl:grid-cols-3">
          {items.map((c) => {
            const outcome = OUTCOME_LABEL[c.outcome] ?? { text: c.outcome, color: "var(--text-3)" };
            return (
              <Link key={c.id} href={`/cases/${c.id}`} className="card block p-4 hover:border-[var(--border-strong)]">
                <div className="mb-1 flex items-center gap-2">
                  <span className="text-[13px] font-semibold leading-5">{c.title}</span>
                  <span className="ml-auto shrink-0 font-mono text-[11px] text-[var(--text-3)]">{c.year}</span>
                </div>
                <div className="mb-1 flex flex-wrap gap-1">
                  {(c.themes ?? []).map((t) => (
                    <span key={t} className="rounded-full bg-[var(--surface-2)] px-1.5 py-0.5 text-[10px] text-[var(--text-2)]">
                      #{t}
                    </span>
                  ))}
                </div>
                <p className="line-clamp-2 text-[12px] leading-5 text-[var(--text-2)]">{c.impact}</p>
                <div className="mt-2 flex items-center gap-2 text-[11px]">
                  <span style={{ color: outcome.color }}>{outcome.text}</span>
                  <span className="ml-auto text-[var(--text-3)]">相似度 {c.similarity.toFixed(2)}</span>
                </div>
              </Link>
            );
          })}
          {items.length === 0 && (
            <div className="card col-span-full p-8 text-center text-[12px] text-[var(--text-3)]">
              暂无案例（make seed 导入；分析命中的历史案例会显示相似度）
            </div>
          )}
        </div>
      </main>
  );
}
