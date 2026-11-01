"use client";

import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { getAudit, type AuditItem } from "@/lib/api";

// 审计日志页：展示真实 audit_log 记录（只读接口 /admin/audit）。
// 支持 ?object_type=&object_id= 定位某个政策/原文的完整审计历史。

const ACTION_LABELS: Record<string, string> = {
  ai_analyze: "AI 分析",
  submit_review: "提交审核",
  skip_review: "跳过审核",
  claim_task: "领取任务",
  review_approve: "审核通过",
  review_reject: "审核驳回",
  review_request_info: "退回补充",
  dispatch: "发布",
  delete_policy: "删除政策",
  upload_document: "上传原文",
  delete_document: "删除原文",
};

const ACTION_BADGE: Record<string, string> = {
  review_approve: "green",
  dispatch: "green",
  upload_document: "green",
  review_reject: "red",
  delete_policy: "red",
  delete_document: "red",
  claim_task: "amber",
  review_request_info: "amber",
  skip_review: "amber",
};

const OBJECT_LABELS: Record<string, string> = {
  policy: "政策",
  document: "原文",
  review_task: "审核任务",
};

function fmtTime(at: string): string {
  return at ? at.slice(0, 19).replace("T", " ") : "—";
}

function fmtJson(value: Record<string, unknown> | null | undefined): string {
  if (!value || Object.keys(value).length === 0) return "—";
  return Object.entries(value)
    .map(([key, item]) => `${key}: ${typeof item === "object" ? JSON.stringify(item) : String(item)}`)
    .join(" · ");
}

function fmtChange(before: Record<string, unknown> | null, after: Record<string, unknown> | null): string {
  const keys = new Set([...Object.keys(before || {}), ...Object.keys(after || {})]);
  const parts = [...keys].map((key) => {
    const oldValue = before?.[key];
    const newValue = after?.[key];
    const fmt = (item: unknown) => (item == null || item === "" ? "—" : typeof item === "object" ? JSON.stringify(item) : String(item));
    if (oldValue === undefined) return `${key}: — → ${fmt(newValue)}`;
    if (newValue === undefined) return `${key}: ${fmt(oldValue)} → —`;
    if (fmt(oldValue) === fmt(newValue)) return "";
    return `${key}: ${fmt(oldValue)} → ${fmt(newValue)}`;
  }).filter(Boolean);
  return parts.length ? parts.join(" · ") : "—";
}

export default function AuditPage() {
  const searchParams = useSearchParams();
  const objectType = searchParams.get("object_type") || (searchParams.get("docId") ? "document" : null);
  const objectId = searchParams.get("object_id") || searchParams.get("docId");

  const [items, setItems] = useState<AuditItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [action, setAction] = useState("");
  const [actor, setActor] = useState("");
  const [currentPage, setCurrentPage] = useState(1);
  const pageSize = 10;

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const query = [
        objectType ? `&object_type=${encodeURIComponent(objectType)}` : "",
        objectId ? `&object_id=${encodeURIComponent(objectId)}` : "",
      ].join("");
      const body = await getAudit(query);
      if (!body) throw new Error("审计日志加载失败");
      setItems(body.items || []);
      setTotal(body.total || 0);
      setCurrentPage(1);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "审计日志加载失败");
    } finally {
      setLoading(false);
    }
  }, [objectType, objectId]);

  useEffect(() => { load(); }, [load]);

  const actors = useMemo(() => [...new Set(items.map((item) => item.actor))].sort(), [items]);

  const filtered = useMemo(() => {
    let list = items;
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      list = list.filter((item) =>
        item.actor.toLowerCase().includes(q) ||
        (ACTION_LABELS[item.action] || item.action).toLowerCase().includes(q) ||
        item.object_id.toLowerCase().includes(q)
      );
    }
    if (action) {
      list = list.filter((item) => item.action === action);
    }
    if (actor) {
      list = list.filter((item) => item.actor === actor);
    }
    return list;
  }, [items, search, action, actor]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const startIndex = (currentPage - 1) * pageSize;
  const endIndex = startIndex + pageSize;
  const pageData = filtered.slice(startIndex, endIndex);

  const goToPage = (page: number) => {
    if (page >= 1 && page <= totalPages) {
      setCurrentPage(page);
    }
  };

  function exportCsv() {
    const escape = (value: string) => `"${value.replaceAll('"', '""')}"`;
    const lines = ["时间,操作者,动作,对象,变更,原因", ...filtered.map((item) => [
      fmtTime(item.at), item.actor, ACTION_LABELS[item.action] || item.action,
      `${item.object_type}:${item.object_id}`, fmtChange(item.before, item.after), item.reason || "—",
    ].map(escape).join(","))];
    const blob = new Blob(["\ufeff" + lines.join("\n")], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `audit_logs_${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  return (
    <main>
      <div className="pagehead">
        <div>
          <div className="eyebrow">AUDIT LOGS</div>
          <h1>审计日志</h1>
          <p className="sub">共 {total} 条 · 只追加，保留 ≥7 年 · 时间均为 UTC</p>
        </div>
        <div style={{ display: "flex", gap: "9px" }}>
          <button className="btn primary" onClick={exportCsv} disabled={!filtered.length}>导出 CSV</button>
        </div>
      </div>

      {(objectType || objectId) && (
        <div className="info" style={{ marginBottom: 14 }}>
          当前仅显示 {OBJECT_LABELS[objectType || ""] || objectType || "对象"} <b>{objectId}</b> 的审计历史（{filtered.length} 条）。
          <a className="link" href="/audit">清除筛选，查看全部日志 →</a>
        </div>
      )}

      <div className="consumer-search">
        <input
          type="text"
          placeholder="搜索操作者、对象或动作…"
          value={search}
          onChange={(e) => { setSearch(e.target.value); setCurrentPage(1); }}
        />
        <select
          className="filter"
          value={action}
          onChange={(e) => { setAction(e.target.value); setCurrentPage(1); }}
        >
          <option value="">全部动作</option>
          {Object.entries(ACTION_LABELS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
        </select>
        <select
          className="filter"
          value={actor}
          onChange={(e) => { setActor(e.target.value); setCurrentPage(1); }}
        >
          <option value="">全部操作者</option>
          {actors.map((name) => <option key={name} value={name}>{name}</option>)}
        </select>
      </div>

      <section className="panel">
        <div className="tablewrap">
          <table>
            <thead>
              <tr>
                <th>时间（UTC）</th>
                <th>操作者</th>
                <th>动作</th>
                <th>对象</th>
                <th>变更</th>
                <th>原因</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={6} style={{ textAlign: "center", padding: "40px 16px" }}>
                    加载中…
                  </td>
                </tr>
              ) : error ? (
                <tr>
                  <td colSpan={6} style={{ textAlign: "center", padding: "40px 16px", color: "#b3261e" }}>
                    {error}
                  </td>
                </tr>
              ) : pageData.length === 0 ? (
                <tr>
                  <td colSpan={6} style={{ textAlign: "center", padding: "40px 16px", color: "#949aa3" }}>
                    无匹配记录
                  </td>
                </tr>
              ) : (
                pageData.map((log) => (
                <tr key={log.id}>
                  <td style={{ whiteSpace: "nowrap", fontSize: "12px", color: "#6b7280", fontFamily: "monospace" }}>
                    {fmtTime(log.at)}
                  </td>
                  <td style={{ fontSize: "12px", fontWeight: 600 }}>{log.actor}</td>
                  <td>
                    <span className={`badge ${ACTION_BADGE[log.action] ?? ""}`}>
                      {ACTION_LABELS[log.action] || log.action}
                    </span>
                  </td>
                  <td style={{ fontSize: "12px", fontFamily: "monospace", color: "#6b7280" }}>
                    {OBJECT_LABELS[log.object_type] || log.object_type}:{log.object_id}
                  </td>
                  <td style={{ fontSize: "12px", color: "#6b7280", maxWidth: 340 }}>
                    <div>{fmtChange(log.before, log.after)}</div>
                    <div style={{ fontSize: 11, color: "#9ca3af", marginTop: 2 }}>
                      前：{fmtJson(log.before)}<br />后：{fmtJson(log.after)}
                    </div>
                  </td>
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
        审计日志为只追加模式，所有采集、AI 分析、审核、发布与删除动作均在此留痕。日志保留期限 ≥7 年，满足金融监管合规要求。
      </p>
    </main>
  );
}
