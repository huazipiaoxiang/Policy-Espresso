"use client";

import { useState, useMemo } from "react";

const DEMO_AUDIT_LOGS = [
  {
    id: "LOG-001",
    time: "2024-11-15 14:32:18",
    actor: "Reviewer A",
    action: "审核通过",
    objectType: "policy",
    objectId: "POL-001",
    detail: "status: pending_review → approved",
    reason: "内容完整，符合大湾区跨境汇款合规要求",
  },
  {
    id: "LOG-002",
    time: "2024-11-15 14:28:05",
    actor: "System (AI)",
    action: "AI 分析",
    objectType: "policy",
    objectId: "POL-008",
    detail: "confidence: 0.92, scope: high",
    reason: "",
  },
  {
    id: "LOG-003",
    time: "2024-11-15 13:55:42",
    actor: "Reviewer B",
    action: "审核驳回",
    objectType: "policy",
    objectId: "POL-005",
    detail: "status: pending_review → rejected",
    reason: "缺少关键附件，需补充 SFC 原文",
  },
  {
    id: "LOG-004",
    time: "2024-11-15 12:40:11",
    actor: "Admin",
    action: "分发",
    objectType: "policy",
    objectId: "POL-002",
    detail: "channels: email, wecom, feishu",
    reason: "",
  },
  {
    id: "LOG-005",
    time: "2024-11-15 11:22:33",
    actor: "Reviewer A",
    action: "领取任务",
    objectType: "policy",
    objectId: "POL-007",
    detail: "assignee: — → Reviewer A",
    reason: "",
  },
  {
    id: "LOG-006",
    time: "2024-11-15 10:15:08",
    actor: "System (Crawler)",
    action: "文档采集",
    objectType: "document",
    objectId: "DOC-011",
    detail: "source: HKMA, format: PDF",
    reason: "",
  },
  {
    id: "LOG-007",
    time: "2024-11-15 09:48:22",
    actor: "Reviewer C",
    action: "退回补充",
    objectType: "policy",
    objectId: "POL-003",
    detail: "status: pending_review → info_requested",
    reason: "需要 MAS 原文确认具体条款编号",
  },
  {
    id: "LOG-008",
    time: "2024-11-14 18:30:55",
    actor: "System (AI)",
    action: "AI 分析",
    objectType: "policy",
    objectId: "POL-006",
    detail: "confidence: 0.78, scope: medium",
    reason: "",
  },
  {
    id: "LOG-009",
    time: "2024-11-14 17:12:40",
    actor: "Admin",
    action: "发布",
    objectType: "policy",
    objectId: "POL-001",
    detail: "status: approved → published",
    reason: "",
  },
  {
    id: "LOG-010",
    time: "2024-11-14 16:05:18",
    actor: "Reviewer B",
    action: "跳过审核",
    objectType: "policy",
    objectId: "POL-009",
    detail: "reason: scope=low, confidence<0.5",
    reason: "低相关性政策，不满足预警条件",
  },
];

const ACTION_BADGE: Record<string, string> = {
  "审核通过": "green",
  "审核驳回": "red",
  "分发": "green",
  "发布": "green",
  "领取任务": "amber",
  "退回补充": "amber",
  "AI 分析": "",
  "文档采集": "",
  "跳过审核": "",
};

export default function AuditPage() {
  const [search, setSearch] = useState("");
  const [action, setAction] = useState("");
  const [actor, setActor] = useState("");
  const [currentPage, setCurrentPage] = useState(1);
  const pageSize = 5;

  const filtered = useMemo(() => {
    let list = DEMO_AUDIT_LOGS;
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      list = list.filter(
        (l) =>
          l.actor.toLowerCase().includes(q) ||
          l.action.toLowerCase().includes(q) ||
          l.objectId.toLowerCase().includes(q)
      );
    }
    if (action) {
      list = list.filter((l) => l.action === action);
    }
    if (actor) {
      list = list.filter((l) => l.actor.includes(actor));
    }
    return list;
  }, [search, action, actor]);

  const totalPages = Math.ceil(filtered.length / pageSize);
  const startIndex = (currentPage - 1) * pageSize;
  const endIndex = startIndex + pageSize;
  const pageData = filtered.slice(startIndex, endIndex);

  const goToPage = (page: number) => {
    if (page >= 1 && page <= totalPages) {
      setCurrentPage(page);
    }
  };

  return (
    <main>
      <div className="pagehead">
        <div>
          <div className="eyebrow">AUDIT LOGS</div>
          <h1>审计日志</h1>
          <p className="sub">共 {DEMO_AUDIT_LOGS.length} 条 · 只追加，保留 ≥7 年</p>
        </div>
        <div style={{ display: "flex", gap: "9px" }}>
          <button
            className="btn primary"
            onClick={() => {
              const headers = ["时间", "操作者", "动作", "对象", "变更", "原因"];
              const rows = filtered.map((log) => [
                log.time,
                log.actor,
                log.action,
                `${log.objectType}:${log.objectId}`,
                log.detail,
                log.reason || "—",
              ]);
              const csvContent = [headers, ...rows]
                .map((row) => row.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(","))
                .join("\n");
              const blob = new Blob(["\ufeff" + csvContent], { type: "text/csv;charset=utf-8;" });
              const url = URL.createObjectURL(blob);
              const a = document.createElement("a");
              a.href = url;
              a.download = `audit_logs_${new Date().toISOString().slice(0, 10)}.csv`;
              document.body.appendChild(a);
              a.click();
              document.body.removeChild(a);
              URL.revokeObjectURL(url);
            }}
          >
            导出 CSV
          </button>
        </div>
      </div>

      <div className="consumer-search">
        <input
          type="text"
          placeholder="搜索操作者、对象或动作…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <select
          className="filter"
          value={action}
          onChange={(e) => setAction(e.target.value)}
        >
          <option value="">全部动作</option>
          <option>审核通过</option>
          <option>审核驳回</option>
          <option>分发</option>
          <option>发布</option>
          <option>AI 分析</option>
          <option>领取任务</option>
        </select>
        <select
          className="filter"
          value={actor}
          onChange={(e) => setActor(e.target.value)}
        >
          <option value="">全部操作者</option>
          <option>Reviewer A</option>
          <option>Reviewer B</option>
          <option>Reviewer C</option>
          <option>Admin</option>
          <option>System</option>
        </select>
      </div>

      <section className="panel">
        <div className="tablewrap">
          <table>
            <thead>
              <tr>
                <th>时间</th>
                <th>操作者</th>
                <th>动作</th>
                <th>对象</th>
                <th>变更</th>
                <th>原因</th>
              </tr>
            </thead>
            <tbody>
              {pageData.length === 0 ? (
                <tr>
                  <td colSpan={6} style={{ textAlign: "center", padding: "40px 16px", color: "#949aa3" }}>
                    无匹配记录
                  </td>
                </tr>
              ) : (
                pageData.map((log) => (
                <tr key={log.id}>
                  <td style={{ whiteSpace: "nowrap", fontSize: "12px", color: "#6b7280", fontFamily: "monospace" }}>
                    {log.time}
                  </td>
                  <td style={{ fontSize: "12px", fontWeight: 600 }}>{log.actor}</td>
                  <td>
                    <span className={`badge ${ACTION_BADGE[log.action] ?? ""}`}>
                      {log.action}
                    </span>
                  </td>
                  <td style={{ fontSize: "12px", fontFamily: "monospace", color: "#6b7280" }}>
                    {log.objectType}:{log.objectId}
                  </td>
                  <td style={{ fontSize: "12px", color: "#6b7280" }}>{log.detail}</td>
                  <td style={{ fontSize: "12px", color: "#8c929a", maxWidth: "200px" }}>
                    {log.reason || "—"}
                  </td>
                </tr>
              ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      <div style={{ display: "flex", justifyContent: "center", gap: "6px", marginTop: "20px" }}>
        <button className="btn" disabled={currentPage === 1} onClick={() => goToPage(currentPage - 1)}>
          ← 上一页
        </button>
        {Array.from({ length: totalPages }, (_, i) => i + 1).map((page) => (
          <button
            key={page}
            className={`btn ${page === currentPage ? "primary" : ""}`}
            onClick={() => goToPage(page)}
          >
            {page}
          </button>
        ))}
        <button className="btn" disabled={currentPage === totalPages} onClick={() => goToPage(currentPage + 1)}>
          下一页 →
        </button>
      </div>

      <p className="footnote">
        审计日志为只追加模式，所有审核、分发、AI 分析动作均在此留痕。日志保留期限 ≥7 年，满足金融监管合规要求。
      </p>
    </main>
  );
}
