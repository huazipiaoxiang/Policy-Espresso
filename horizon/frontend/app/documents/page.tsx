import DocumentList from "@/components/DocumentList";

// 文档流（Phase 1）：抓取入库的原始政策文档，含状态与附件解析情况
export default function DocumentsPage() {
  return (
    <main className="mx-auto max-w-content px-6 pb-10 py-6">
      <DocumentList />
    </main>
  );
}
