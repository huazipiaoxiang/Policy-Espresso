"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState, useEffect } from "react";
import { API_BASE, demoApiHeaders } from "@/lib/auth";
import { JURISDICTION_LABELS } from "@/lib/labels";

interface DocumentVersion {
  version_no: number;
  changed_at: string;
  changed_ratio: number | null;
  minor_edit: boolean;
}

interface DocumentDetail {
  id: string;
  source_id: string;
  title: string;
  url: string;
  canonical_url: string;
  lang: string;
  published_at: string;
  fetched_at: string;
  status: string;
  duplicate_of: string | null;
  attachments: { name?: string; content_type?: string; size?: number; processing_error?: string }[];
  content_len: number;
  processing_error: string;
  policy_id: string | null;
  source_name: string;
  jurisdiction: string;
  content_text: string;
  versions: DocumentVersion[];
}

const STATUS_LABELS: Record<string, string> = {
  new: "待解析",
  processed: "已解析",
  failed: "解析失败",
  ignored: "已忽略",
  needs_full_text: "待补充",
};

function statusBadgeClass(status: string): string {
  if (status === "processed") return "badge green";
  if (status === "failed") return "badge red";
  if (status === "new" || status === "needs_full_text") return "badge amber";
  return "badge";
}

function formatBytes(bytes?: number): string {
  if (!bytes) return "—";
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

export default function DocumentDetailPage() {
  const params = useParams();
  const router = useRouter();
  const id = params?.id as string;

  const [doc, setDoc] = useState<DocumentDetail | null>(null);
  const [policy, setPolicy] = useState<{ id: string; title: string } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const response = await fetch(`${API_BASE}/documents/${id}`, {
          headers: demoApiHeaders(),
        });
        if (response.status === 404) {
          if (!cancelled) { setDoc(null); setError("not_found"); }
          return;
        }
        if (!response.ok) throw new Error(`API error: ${response.status}`);
        const data = await response.json();
        if (cancelled) return;
        setDoc(data);
        setError(null);
        if (data.policy_id) {
          try {
            const pResponse = await fetch(`${API_BASE}/policies/${data.policy_id}`, {
              headers: demoApiHeaders(),
            });
            if (pResponse.ok) {
              const pData = await pResponse.json();
              if (!cancelled) setPolicy({ id: pData.id, title: pData.title });
            }
          } catch {
            if (!cancelled) setPolicy({ id: data.policy_id, title: "" });
          }
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to fetch document");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, [id]);

  if (loading) {
    return (
      <main>
        <Link href="/documents" className="back">&larr; 返回原文库</Link>
        <div className="pagehead">
          <div>
            <div className="eyebrow">DOCUMENT DETAIL</div>
            <h1>加载中…</h1>
          </div>
        </div>
      </main>
    );
  }

  if (!doc || error === "not_found") {
    return (
      <main>
        <Link href="/documents" className="back">&larr; 返回原文库</Link>
        <div className="pagehead">
          <div>
            <div className="eyebrow">DOCUMENT NOT FOUND</div>
            <h1>文档未找到</h1>
            <p className="sub">请求的文档 ID「{id}」不存在或已被移除。</p>
          </div>
        </div>
        <section className="panel" style={{ padding: "40px", textAlign: "center" }}>
          <p style={{ color: "#6b7280", marginBottom: 16 }}>请检查文档链接是否正确，或返回原文库重新选择。</p>
          <Link href="/documents" className="btn primary">返回原文库</Link>
        </section>
      </main>
    );
  }

  if (error) {
    return (
      <main>
        <Link href="/documents" className="back">&larr; 返回原文库</Link>
        <div className="pagehead">
          <div>
            <div className="eyebrow">DOCUMENT ERROR</div>
            <h1>加载失败</h1>
            <p className="sub">{error}</p>
          </div>
        </div>
        <section className="panel" style={{ padding: "40px", textAlign: "center" }}>
          <button className="btn primary" onClick={() => window.location.reload()}>重试</button>
        </section>
      </main>
    );
  }

  const contentPreview = (doc.content_text || "").slice(0, 8000);
  const contentTruncated = (doc.content_text || "").length > 8000;

  return (
    <main>
      <Link href="/documents" className="back">&larr; 返回原文库</Link>

      <div className="pagehead">
        <div>
          <div className="eyebrow">DOCUMENT DETAIL</div>
          <h1>{doc.title}</h1>
          <p className="sub">
            {doc.id} &middot; {doc.source_name || doc.source_id || "未知来源"} &middot;{" "}
            {JURISDICTION_LABELS[doc.jurisdiction] || doc.jurisdiction || "市场未标注"}
          </p>
        </div>
        <div className="rowflex">
          <span className={statusBadgeClass(doc.status)}>{STATUS_LABELS[doc.status] || doc.status}</span>
          <span className="badge">{doc.lang || "zh"}</span>
        </div>
      </div>

      <div className="details-grid">
        <div className="stack">
          {/* Document info */}
          <div className="panel">
            <div className="panelhead">
              <h2>文档信息</h2>
              <small>Document Information</small>
            </div>
            <div className="sectionbody">
              <div className="fieldgrid">
                <div className="field">
                  <small>文档编号</small>
                  <strong style={{ fontFamily: "monospace" }}>{doc.id}</strong>
                </div>
                <div className="field">
                  <small>市场</small>
                  <strong>{JURISDICTION_LABELS[doc.jurisdiction] || doc.jurisdiction || "—"}</strong>
                </div>
                <div className="field">
                  <small>来源机构</small>
                  <strong>{doc.source_name || doc.source_id || "—"}</strong>
                </div>
                <div className="field">
                  <small>发布日期</small>
                  <strong>{doc.published_at ? doc.published_at.slice(0, 10) : "—"}</strong>
                </div>
                <div className="field">
                  <small>采集时间</small>
                  <strong>{doc.fetched_at ? new Date(doc.fetched_at).toLocaleString("zh-CN") : "—"}</strong>
                </div>
                <div className="field">
                  <small>文档语言</small>
                  <strong>{doc.lang || "zh"}</strong>
                </div>
              </div>

              {doc.duplicate_of && (
                <>
                  <div className="divider" />
                  <div className="info">该文档与 <Link href={`/documents/${doc.duplicate_of}`} style={{ fontWeight: 700, color: "var(--red)" }}>{doc.duplicate_of}</Link> 内容重复。</div>
                </>
              )}

              {(doc.url.startsWith("http") || doc.canonical_url?.startsWith("http")) && (
                <>
                  <div className="divider" />
                  <div>
                    <small style={{ display: "block", fontSize: 11, color: "#8b929c", marginBottom: 8 }}>
                      原文链接
                    </small>
                    <a
                      href={doc.canonical_url?.startsWith("http") ? doc.canonical_url : doc.url}
                      target="_blank"
                      rel="noreferrer"
                      style={{ fontSize: 12, color: "var(--red)", fontWeight: 700 }}
                    >
                      {doc.source_name || "来源"} 官方页面 &rarr;
                    </a>
                  </div>
                </>
              )}
            </div>
          </div>

          {/* Parse status */}
          <div className="panel">
            <div className="panelhead">
              <h2>解析状态</h2>
              <small>Parsing Status</small>
            </div>
            <div className="sectionbody">
              <div className="fieldgrid" style={{ marginBottom: 12 }}>
                <div className="field">
                  <small>解析状态</small>
                  <strong><span className={statusBadgeClass(doc.status)}>{STATUS_LABELS[doc.status] || doc.status}</span></strong>
                </div>
                <div className="field">
                  <small>正文长度</small>
                  <strong>{doc.content_len.toLocaleString()} 字符</strong>
                </div>
                <div className="field">
                  <small>附件数量</small>
                  <strong>{doc.attachments?.length || 0} 个</strong>
                </div>
              </div>

              {doc.attachments?.length > 0 && (
                <div>
                  <small style={{ display: "block", fontSize: 11, color: "#8b929c", marginBottom: 6 }}>附件列表</small>
                  {doc.attachments.map((a, i) => (
                    <div key={i} style={{ padding: "6px 0", fontSize: 12, color: "#606a76", borderBottom: i < doc.attachments.length - 1 ? "1px solid #eceef0" : "none" }}>
                      {a.name || "未命名附件"} · {a.content_type || "未知格式"} · {formatBytes(a.size)}
                    </div>
                  ))}
                </div>
              )}

              {(doc.processing_error || doc.attachments?.some((a) => a.processing_error)) && (
                <div className="info" style={{ marginTop: 12 }}>
                  处理提示：{doc.processing_error || doc.attachments?.find((a) => a.processing_error)?.processing_error}
                </div>
              )}
            </div>
          </div>

          {/* Original content */}
          <div className="panel">
            <div className="panelhead">
              <h2>原文正文</h2>
              <small>Extracted Text</small>
            </div>
            <div className="sectionbody">
              {doc.content_text ? (
                <>
                  <div style={{ maxHeight: 420, overflowY: "auto", fontSize: 12, lineHeight: 1.7, color: "#3c444e", whiteSpace: "pre-wrap", border: "1px solid #eceef0", borderRadius: 8, padding: "12px 14px" }}>
                    {contentPreview}
                  </div>
                  <small style={{ display: "block", marginTop: 8, color: "#8b929c" }}>
                    {contentTruncated ? `正文共 ${doc.content_len.toLocaleString()} 字符，此处仅显示前 8,000 字符。` : `正文共 ${doc.content_len.toLocaleString()} 字符。`}
                  </small>
                </>
              ) : (
                <div style={{ textAlign: "center", padding: "24px 0", color: "#949aa3" }}>
                  {doc.status === "new" && "文档尚未开始解析，暂无正文。"}
                  {doc.status === "needs_full_text" && "正文不完整，等待补充全文。"}
                  {doc.status === "failed" && "文档解析失败，无可用正文。"}
                  {!["new", "needs_full_text", "failed"].includes(doc.status) && "暂无正文内容。"}
                </div>
              )}
            </div>
          </div>

          {/* Linked policy */}
          <div className="panel">
            <div className="panelhead">
              <h2>关联解读</h2>
              <small>Linked Policy</small>
            </div>
            <div className="sectionbody">
              {doc.policy_id ? (
                <div>
                  <Link href={`/policies/${doc.policy_id}`} style={{ fontWeight: 600, color: "var(--red)" }}>
                    {policy?.title || `政策 ${doc.policy_id}`}
                  </Link>
                  <br />
                  <small style={{ color: "#8b929c", fontSize: 11 }}>{doc.policy_id}</small>
                </div>
              ) : (
                <div style={{ textAlign: "center", padding: "24px 0", color: "#949aa3" }}>
                  暂无关联解读。文档解析完成后可在此查看生成的政策条目。
                </div>
              )}
            </div>
          </div>
        </div>

        <div className="stack">
          {/* Version history */}
          <div className="panel">
            <div className="panelhead">
              <h2>版本历史</h2>
              <small>Version History</small>
            </div>
            <div className="sectionbody">
              {doc.versions?.length > 0 ? (
                doc.versions.map((v, i) => (
                  <div
                    key={v.version_no}
                    style={{
                      padding: "10px 0",
                      borderBottom: i < doc.versions.length - 1 ? "1px solid #eceef0" : "none",
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <strong style={{ fontFamily: "monospace", fontSize: 12 }}>V{v.version_no}</strong>
                      <small style={{ color: "#8b929c" }}>{v.changed_at ? new Date(v.changed_at).toLocaleString("zh-CN") : "—"}</small>
                    </div>
                    <p style={{ margin: "4px 0 0", fontSize: 12, color: "#606a76" }}>
                      {v.minor_edit ? "小幅修改" : "版本更新"}
                      {v.changed_ratio != null && ` · 变动比例 ${(v.changed_ratio * 100).toFixed(0)}%`}
                    </p>
                  </div>
                ))
              ) : (
                <div style={{ textAlign: "center", padding: "24px 0", color: "#949aa3" }}>
                  暂无版本记录。
                </div>
              )}
            </div>
          </div>

          {/* Actions */}
          <div className="panel">
            <div className="panelhead">
              <h2>操作</h2>
              <small>Actions</small>
            </div>
            <div className="sectionbody">
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {(doc.content_text || (doc.attachments?.length ?? 0) > 0) && (
                  <button
                    className="btn primary"
                    onClick={async () => {
                      try {
                        const response = await fetch(`${API_BASE}/documents/${doc.id}/pdf`, {
                          headers: demoApiHeaders(),
                        });
                        if (!response.ok) {
                          const data = await response.json().catch(() => null);
                          alert(data?.error?.message || "PDF 生成失败");
                          return;
                        }
                        const blob = await response.blob();
                        const url = URL.createObjectURL(blob);
                        const a = document.createElement("a");
                        a.href = url;
                        a.download = `${doc.id}.pdf`;
                        document.body.appendChild(a);
                        a.click();
                        document.body.removeChild(a);
                        URL.revokeObjectURL(url);
                      } catch (reason) {
                        alert(reason instanceof Error ? reason.message : "下载失败");
                      }
                    }}
                  >
                    下载 PDF
                  </button>
                )}
                <button className="btn" onClick={() => router.push(`/audit?docId=${doc.id}`)}>
                  查看审计日志
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <p className="footnote">
        原文库文档来自监管机构与官方网站采集。正文为解析管线提取的纯文本，可能与原始排版存在差异。
      </p>
    </main>
  );
}
