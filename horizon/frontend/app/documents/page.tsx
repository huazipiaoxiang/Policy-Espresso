"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState, useEffect, useCallback } from "react";
import { useAuth } from "@/components/AuthProvider";
import ConfirmDialog from "@/components/ConfirmDialog";
import { API_BASE, demoApiHeaders } from "@/lib/auth";
import { JURISDICTION_LABELS } from "@/lib/labels";

interface Document {
  id: string;
  source_id: string;
  title: string;
  url: string;
  lang: string;
  published_at: string;
  fetched_at: string;
  status: string;
  duplicate_of: string | null;
  attachments: any[];
  content_len: number;
  processing_error: string;
  policy_id: string | null;
  source_name: string;
  jurisdiction: string;
}

export default function DocumentsPage() {
  const { role } = useAuth();
  const searchParams = useSearchParams();
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [currentPage, setCurrentPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [uploadOpen, setUploadOpen] = useState(searchParams.get("upload") === "1");
  const [uploadTitle, setUploadTitle] = useState("");
  const [uploadJurisdiction, setUploadJurisdiction] = useState("");
  const [uploadPublishedAt, setUploadPublishedAt] = useState("");
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<Document | null>(null);
  const [busyId, setBusyId] = useState("");
  const [notice, setNotice] = useState("");
  const pageSize = 20;

  const fetchDocuments = useCallback(async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams({
        page: String(currentPage),
        page_size: String(pageSize),
      });
      if (status) params.set("status", status);

      const response = await fetch(`${API_BASE}/documents?${params}`, {
        headers: demoApiHeaders(),
      });
      if (!response.ok) throw new Error(`API error: ${response.status}`);
      const data = await response.json();
      setDocuments(data.items || []);
      setTotal(data.total || 0);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch documents");
      console.error("Fetch error:", err);
    } finally {
      setLoading(false);
    }
  }, [currentPage, status]);

  useEffect(() => {
    fetchDocuments();
  }, [fetchDocuments]);

  useEffect(() => {
    setCurrentPage(1);
  }, [status]);

  const getStatusLabel = (s: string) => {
    const labels: Record<string, string> = {
      new: "待解析", processed: "已解析", failed: "解析失败",
      ignored: "已忽略", needs_full_text: "待补充",
    };
    return labels[s] || s;
  };

  async function uploadDocument(event: React.FormEvent) {
    event.preventDefault();
    if (!uploadFile) return;
    setUploading(true);
    setUploadResult("");
    const body = new FormData();
    body.append("file", uploadFile);
    body.append("jurisdiction", uploadJurisdiction);
    if (uploadTitle.trim()) body.append("title", uploadTitle.trim());
    if (uploadPublishedAt) body.append("published_at", uploadPublishedAt);
    try {
      const response = await fetch(`${API_BASE}/documents/upload`, {
        method: "POST", headers: demoApiHeaders(), body,
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data?.error?.message || "上传失败");
      setUploadResult(data.status === "failed"
        ? `已保存原文件，但处理失败：${data.processing_error}`
        : data.policy_id ? "上传、解析和 AI 分析已完成" : `上传完成：${data.processing_error || "未生成政策"}`);
      setUploadFile(null);
      setUploadTitle("");
      await fetchDocuments();
    } catch (reason) {
      setUploadResult(reason instanceof Error ? reason.message : "上传失败");
    } finally {
      setUploading(false);
    }
  }

  const filteredDocs = search.trim()
    ? documents.filter((d) => d.title.toLowerCase().includes(search.trim().toLowerCase()))
    : documents;

  async function removeDocument() {
    const doc = deleteTarget;
    if (!doc) return;
    setBusyId(doc.id);
    setNotice("");
    try {
      const response = await fetch(`${API_BASE}/documents/${doc.id}`, {
        method: "DELETE",
        headers: demoApiHeaders(),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(body?.error?.message || "删除失败");
      }
      setDeleteTarget(null);
      setNotice(`文档「${doc.title}」已删除${doc.policy_id ? "，关联政策一并删除" : ""}`);
      await fetchDocuments();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "删除失败");
    } finally {
      setBusyId("");
    }
  }

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  const goToPage = (page: number) => {
    if (page >= 1 && page <= totalPages) setCurrentPage(page);
  };

  const visiblePages = () => {
    const pages: number[] = [];
    const start = Math.max(1, currentPage - 2);
    const end = Math.min(totalPages, currentPage + 2);
    for (let i = start; i <= end; i++) pages.push(i);
    return pages;
  };

  return (
    <main>
      <div className="pagehead">
        <div>
          <div className="eyebrow">ORIGINAL DOCUMENTS</div>
          <h1>原文库</h1>
          <p className="sub">监管机构、官方网站采集的原始文件 · 与政策库分开管理</p>
        </div>
        {role === "admin" && <button className="btn primary" onClick={() => setUploadOpen((open) => !open)}>上传政策文件</button>}
      </div>

      {role === "admin" && uploadOpen && <section className="panel" style={{ marginBottom: 18 }}>
        <div className="panelhead"><h2>上传政策原文</h2><small>PDF / DOC / DOCX / XLS / XLSX，最大 20 MB</small></div>
        <div className="sectionbody">
          <form onSubmit={uploadDocument}>
            <div className="rowflex" style={{ alignItems: "flex-end" }}>
              <label style={{ flex: 1 }}><small>政策标题（可选）</small><input className="search" style={{ width: "100%" }} value={uploadTitle} onChange={(event) => setUploadTitle(event.target.value)} /></label>
              <label><small>所属市场</small>
                <select className="filter" required value={uploadJurisdiction} onChange={(event) => setUploadJurisdiction(event.target.value)}>
                  <option value="">请选择市场</option>
                  {Object.entries(JURISDICTION_LABELS).map(([code, label]) => (
                    <option key={code} value={code}>{label}（{code}）</option>
                  ))}
                </select>
              </label>
              <label><small>发布日期（可选）</small>
                <input className="search" type="date" value={uploadPublishedAt} onChange={(event) => setUploadPublishedAt(event.target.value)} />
              </label>
              <input type="file" accept=".pdf,.doc,.docx,.xls,.xlsx" required onChange={(event) => setUploadFile(event.target.files?.[0] || null)} />
              <button className="btn primary" disabled={uploading || !uploadFile}>{uploading ? "上传并分析中…" : "开始上传"}</button>
            </div>
          </form>
          {uploadResult && <div className="info" style={{ marginTop: 12 }}>{uploadResult}</div>}
        </div>
      </section>}

      {notice && <div className="info" style={{ marginBottom: 18 }}>{notice}</div>}

      <div className="doc-intro">
        原文库收录所有从监管机构、官方网站等渠道采集的原始文件。每份文件经解析后生成对应的政策条目，
        与政策库独立管理。支持按状态筛选，并可追踪文件的解析进度与关联解读。
      </div>

      <div className="consumer-search">
        <input
          type="text"
          placeholder="搜索文档标题…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <select
          className="filter"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
        >
          <option value="">全部状态</option>
          <option value="processed">已解析</option>
          <option value="new">待解析</option>
          <option value="failed">解析失败</option>
          <option value="ignored">已忽略</option>
          <option value="needs_full_text">待补充</option>
        </select>
        <span>共 {total.toLocaleString()} 份文档{search.trim() ? `（当前页匹配 ${filteredDocs.length} 份）` : ""}</span>
      </div>

      <section className="panel">
        <div className="tablewrap">
          <table>
            <thead>
              <tr>
                <th>文档标题</th>
                <th>市场 / 来源</th>
                <th>日期</th>
                <th>语言</th>
                <th>文档状态</th>
                <th>附件</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={7} style={{ textAlign: "center", padding: "40px 16px", color: "#949aa3" }}>
                    加载中…
                  </td>
                </tr>
              ) : error ? (
                <tr>
                  <td colSpan={7} style={{ textAlign: "center", padding: "40px 16px", color: "#dc2626" }}>
                    加载失败：{error}
                  </td>
                </tr>
              ) : filteredDocs.length === 0 ? (
                <tr>
                  <td colSpan={7} style={{ textAlign: "center", padding: "40px 16px", color: "#949aa3" }}>
                    无匹配记录
                  </td>
                </tr>
              ) : (
                filteredDocs.map((doc) => (
                  <tr key={doc.id} className="clickable">
                    <td style={{ minWidth: "260px" }}>
                      <div className="policytitle">
                        {doc.title}
                        <small>{doc.id}</small>
                      </div>
                    </td>
                    <td>
                      {JURISDICTION_LABELS[doc.jurisdiction] || doc.jurisdiction || "—"}
                      <br />
                      <span style={{ color: "#8c929a", fontSize: "11px" }}>{doc.source_name || doc.source_id}</span>
                    </td>
                    <td style={{ whiteSpace: "nowrap", fontSize: "12px", color: "#6b7280" }}>
                      {doc.published_at ? doc.published_at.slice(0, 10) : "—"}
                    </td>
                    <td>
                      <span className="badge">{doc.lang || "zh"}</span>
                    </td>
                    <td>
                      <span className={`badge ${
                        doc.status === "processed" ? "green" :
                        doc.status === "failed" ? "red" :
                        doc.status === "new" ? "amber" : ""
                      }`}>
                        {getStatusLabel(doc.status)}
                      </span>
                      {doc.processing_error && <small title={doc.processing_error} style={{ display: "block", maxWidth: 220, color: "var(--red)", marginTop: 5 }}>{doc.processing_error}</small>}
                    </td>
                    <td style={{ fontSize: "12px", color: "#6b7280" }}>
                      {doc.attachments?.length || 0} 个
                    </td>
                    <td>
                      <div className="rowflex">
                        <Link href={`/documents/${doc.id}`} className="link">原文 →</Link>
                        {doc.policy_id && <Link href={`/policies/${doc.policy_id}`} className="link">政策 →</Link>}
                        {role === "admin" && <button className="link" disabled={busyId === doc.id} onClick={() => setDeleteTarget(doc)} style={{ color: "var(--red)" }}>删除</button>}
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      {totalPages > 1 && (
        <div style={{ display: "flex", justifyContent: "center", gap: "6px", marginTop: "20px", flexWrap: "wrap" }}>
          <button className="btn" disabled={currentPage === 1} onClick={() => goToPage(currentPage - 1)}>
            ← 上一页
          </button>
          {visiblePages()[0] > 1 && (
            <>
              <button className="btn" onClick={() => goToPage(1)}>1</button>
              {visiblePages()[0] > 2 && <span style={{ padding: "6px 4px", color: "#949aa3" }}>…</span>}
            </>
          )}
          {visiblePages().map((page) => (
            <button
              key={page}
              className={`btn ${page === currentPage ? "primary" : ""}`}
              onClick={() => goToPage(page)}
            >
              {page}
            </button>
          ))}
          {visiblePages()[visiblePages().length - 1] < totalPages && (
            <>
              {visiblePages()[visiblePages().length - 1] < totalPages - 1 && (
                <span style={{ padding: "6px 4px", color: "#949aa3" }}>…</span>
              )}
              <button className="btn" onClick={() => goToPage(totalPages)}>{totalPages}</button>
            </>
          )}
          <button className="btn" disabled={currentPage === totalPages} onClick={() => goToPage(currentPage + 1)}>
            下一页 →
          </button>
        </div>
      )}

      <p className="footnote">
        第 {currentPage}/{totalPages} 页，共 {total.toLocaleString()} 份文档。数据来自后端 API 实时抓取。
      </p>

      {deleteTarget && (
        <ConfirmDialog
          title="删除原文"
          confirmLabel="确认删除"
          busy={busyId === deleteTarget.id}
          onCancel={() => setDeleteTarget(null)}
          onConfirm={removeDocument}
          acknowledgeLabel={`我已确认删除「${deleteTarget.title}」${deleteTarget.policy_id ? "及其关联政策" : ""}`}
          description={<>
            <p>文档编号：{deleteTarget.id}（{deleteTarget.source_name || deleteTarget.source_id}）</p>
            {deleteTarget.policy_id ? (
              <p>该文档已生成政策，删除后政策的 AI 分析、审核、预警和图谱关联会一并清除。</p>
            ) : (
              <p>删除后仅移除原文记录及其本地文件。</p>
            )}
            <p>此操作不可撤销，删除记录会写入审计日志。</p>
          </>}
        />
      )}
    </main>
  );
}
