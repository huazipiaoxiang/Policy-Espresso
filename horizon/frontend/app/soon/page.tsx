import EmptyState from "@/components/EmptyState";

// 未实现页面的统一占位
export default function SoonPage() {
  return (
    <main className="mx-auto max-w-content px-6 py-6">
      <EmptyState
        title="该页面将在后续 Phase 交付"
        hint="政策详情（Phase 2）· 审核台（Phase 3）· 案例库与 Studio（Phase 4）"
        action="返回 /radar"
      />
    </main>
  );
}
