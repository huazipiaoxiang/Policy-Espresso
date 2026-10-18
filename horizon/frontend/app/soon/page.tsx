import EmptyState from "@/components/EmptyState";
import Topbar from "@/components/Topbar";

// 未实现页面的统一占位
export default function SoonPage() {
  return (
    <>
      <Topbar />
      <main className="mx-auto max-w-content px-6 pt-[72px]">
        <EmptyState
          title="该页面将在后续 Phase 交付"
          hint="政策详情（Phase 2）· 审核台（Phase 3）· 案例库与 Studio（Phase 4）"
          action="返回 /radar"
        />
      </main>
    </>
  );
}
