import StudioConsole from "@/components/StudioConsole";
import StudioCreateForm from "@/components/StudioCreateForm";
import Topbar from "@/components/Topbar";
import { getCorpus, getOverview, getProposal, getStudioProjects, getStudioProposals } from "@/lib/api";

export const dynamic = "force-dynamic";

// 政策 2.0 工作台（08 §3.6）
export default async function StudioPage() {
  const [overview, projects, corpus] = await Promise.all([
    getOverview(),
    getStudioProjects(),
    getCorpus(),
  ]);
  const projectList = projects?.items ?? [];
  const docs = corpus?.docs ?? [];

  // 默认展示第一个项目的最新一版建议书
  let proposal = null;
  if (projectList.length > 0) {
    const versions = await getStudioProposals(projectList[0].id);
    if (versions?.items.length) {
      proposal = await getProposal(versions.items[0].id);
    }
  }

  return (
    <>
      <Topbar
        sourcesTotal={overview?.sources_total ?? 0}
        sourcesUnhealthy={overview?.sources_unhealthy ?? 0}
        pendingReview={overview?.pending_review ?? 0}
      />
      <main className="mx-auto max-w-content px-6 pb-10 pt-[72px]">
        <div className="mb-3 flex items-center gap-2">
          <h1 className="text-[16px] font-semibold">政策 2.0 工作台</h1>
          <span className="text-[12px] text-[var(--text-3)]">CEPA 主题语料 → 条款演化 → 建议书生成 → 边界校验 → 双审</span>
        </div>
        <StudioCreateForm themes={corpus?.themes ?? []} />
        <div className="mt-4">
          {projectList.length === 0 ? (
            <div className="card p-8 text-center">
              <div className="text-[13px] text-[var(--text-2)]">还没有 Studio 项目，先创建一个</div>
              <div className="mt-1 text-[12px] text-[var(--text-3)]">
                语料已就绪：{docs.length} 份文件 · {corpus?.themes.length ?? 0} 个主题（已废止文件自动排除）
              </div>
            </div>
          ) : (
            <StudioConsole projects={projectList} corpus={docs} proposal={proposal} />
          )}
        </div>
      </main>
    </>
  );
}
