"use client";

import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { getAudit, getSystemLogs, type AuditItem, type SystemLogDay } from "@/lib/api";
import { AUDIT_ACTION_LABELS as ACTION_LABELS } from "@/lib/labels";

// 系统日志页：默认展示系统运行日志（/admin/system-logs，按天分组，含运行错误），
// 另保留「操作审计」（/admin/audit，人工生命周期事件）作为次级视图。
// 支持 ?object_type=&object_id= 定位某个政策/原文的完整操作审计历史（此时默认切到操作审计）。

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
  review_task: "处理任务",
};

const JOB_STATUS_BADGE: Record<string, string> = {
  ok: "green",
  failed: "red",
  running: "amber",
};

const JOB_STATUS_LABELS: Record<string, string> = {
  ok: "成功",
  failed: "失败",
  running: "运行中",
};

function fmtTime(at: string): string {
  return at ? at.slice(0, 19).replace("T", " ") : "—";
}

function fmtClock(at: string | null): string {
  if (!at) return "—";
  return at.slice(11, 19);
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

// 运行统计的简写：挑出最值得看的几个口径，其余折叠。
const STAT_KEYS = ["created", "updated", "failed", "analyzed", "skipped", "duplicates_marked", "discovered", "ignored", "sources"];
function fmtStats(stats: Record<string, unknown> | null | undefined): string {
  if (!stats || Object.keys(stats).length === 0) return "—";
  const parts: string[] = [];
  for (const key of STAT_KEYS) {
    const value = stats[key];
    if (typeof value === "number") parts.push(`${key} ${value}`);
  }
  return parts.length ? parts.join(" · ") : "—";
}

export default function AuditPage() {
  const searchParams = useSearchParams();
  const objectType = searchParams.get("object_type") || (searchParams.get("docId") ? "document" : null);
  const objectId = searchParams.get("object_id") || searchParams.get("docId");

  // 带对象定位参数（从政策/原文详情跳转）时默认看操作审计；否则默认看系统日志。
  const [tab, setTab] = useState<"system" | "audit">(objectType || objectId ? "audit" : "system");

  return (
    <main>
      <div className="pagehead">
        <div>
          <div className="eyebrow">SYSTEM LOGS</div>
          <h1>系统日志</h1>
          <p className="sub">系统每日抓取政策与运行记录 · 每天一份 · 含运行出错详情</p>
        </div>
      </div>

      <div className="tabs" role="tablist" aria-label="日志类型" style={{ marginBottom: 18 }}>
        <button
          className={`tab ${tab === "system" ? "active" : ""}`}
          onClick={() => setTab("system")}
        >
          系统日志
        </button>
        <button
          className={`tab ${tab === "audit" ? "active" : ""}`}
          onClick={() => setTab("audit")}
        >
          操作审计
        </button>
      </div>

      {tab === "system" ? (
        <SystemLogsView />
      ) : (
        <AuditLogsView objectType={objectType} objectId={objectId} />
      )}
    </main>
  );
}

function SystemLogsView() {
  const [days, setDays] = useState<SystemLogDay[]>([]);
  const [totalDays, setTotalDays] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [range, setRange] = useState(14);
  const [onlyFailed, setOnlyFailed] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const body = await getSystemLogs(range);
      if (!body) {
        setError("系统日志暂不可用，请稍后重试。");
        return;
      }
      setDays(body.days || []);
      setTotalDays(body.total_days || 0);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "系统日志加载失败");
    } finally {
      setLoading(false);
    }
  }, [range]);

  useEffect(() => { void load(); }, [load]);

  const visibleDays = useMemo(() => {
    if (!onlyFailed) return days;
    return days
      .map((day) => ({ ...day, runs: day.runs.filter((run) => run.status === "failed") }))
      .filter((day) => day.runs.length > 0);
  }, [days, onlyFailed]);

  const totalRuns = useMemo(() => days.reduce((acc, day) => acc + day.summary.total, 0), [days]);
  const failedRuns = useMemo(() => days.reduce((acc, day) => acc + day.summary.failed, 0), [days]);

  return (
    <>
      <div className="consumer-search">
        <select className="filter" value={range} onChange={(e) => setRange(Number(e.target.value))}>
          <option value={7}>最近 7 天</option>
          <option value={14}>最近 14 天</option>
          <option value={30}>最近 30 天</option>
        </select>
        <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13, color: "#4b525c" }}>
          <input
            type="checkbox"
            checked={onlyFailed}
            onChange={(e) => setOnlyFailed(e.target.checked)}
          />
          仅看运行出错
        </label>
        <span style={{ fontSize: 12, color: "#8b929c", marginLeft: "auto" }}>
          共 {totalDays} 天 · {totalRuns} 次运行{failedRuns > 0 ? ` · ${failedRuns} 次失败` : ""}
        </span>
        <button className="btn" onClick={() => void load()} disabled={loading}>刷新</button>
      </div>

      {loading ? (
        <section className="panel" style={{ padding: "40px 16px", textAlign: "center", color: "#949aa3" }}>加载中…</section>
      ) : error ? (
        <section className="panel" style={{ padding: "40px 16px", textAlign: "center", color: "#b3261e" }}>{error}</section>
      ) : visibleDays.length === 0 ? (
        <section className="panel" style={{ padding: "40px 16px", textAlign: "center", color: "#949aa3" }}>
          {onlyFailed ? "所选范围内没有运行出错的记录" : "暂无系统运行日志"}
        </section>
      ) : (
        visibleDays.map((day) => (
          <section key={day.date} className="panel" style={{ marginBottom: 16 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8, padding: "10px 16px", borderBottom: "1px solid var(--border)" }}>
              <div>
                <b style={{ fontSize: 14 }}>{day.date}</b>
                <span style={{ fontSize: 12, color: "#8b929c", marginLeft: 8 }}>
                  当日 {day.summary.total} 次运行
                </span>
              </div>
              <div style={{ display: "flex", gap: 6 }}>
                <span className="badge green">成功 {day.summary.ok}</span>
                {day.summary.failed > 0 && <span className="badge red">失败 {day.summary.failed}</span>}
                {day.summary.running > 0 && <span className="badge amber">运行中 {day.summary.running}</span>}
              </div>
            </div>
            <div className="tablewrap">
              <table>
                <thead>
                  <tr>
                    <th>任务</th>
                    <th>来源</th>
                    <th>状态</th>
                    <th>开始时间</th>
                    <th>运行结果</th>
                  </tr>
                </thead>
                <tbody>
                  {day.runs.map((run) => (
                    <tr key={run.id}>
                      <td style={{ fontSize: "12px", fontWeight: 600, whiteSpace: "nowrap" }}>{run.label}</td>
                      <td style={{ fontSize: "12px", fontFamily: "monospace", color: "#6b7280" }}>
                        {run.source_code || "—"}
                      </td>
                      <td>
                        <span className={`badge ${JOB_STATUS_BADGE[run.status] ?? ""}`}>
                          {JOB_STATUS_LABELS[run.status] || run.status}
                        </span>
                      </td>
                      <td style={{ fontSize: "12px", fontFamily: "monospace", color: "#6b7280", whiteSpace: "nowrap" }}>
                        {run.clock || fmtClock(run.started_at)}
                      </td>
                      <td style={{ fontSize: "12px", color: "#6b7280", maxWidth: 420 }}>
                        {run.status === "failed" && run.error ? (
                          <div style={{ color: "#b3261e", wordBreak: "break-word" }}>{run.error}</div>
                        ) : (
                          <div>{fmtStats(run.stats)}</div>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        ))
      )}

      <p className="footnote">
        系统日志来自后台调度任务运行记录（JobRun）：每日抓取政策、政策分析、健康检查、心跳巡检与保留清理，
        按自然日归档为「每天一份」。失败任务会显示具体错误原因，便于定位与修复。
      </p>
    </>
  );
}

function AuditLogsView({ objectType, objectId }: { objectType: string | null; objectId: string | null }) {
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
      if (!body) {
        setItems([]);
        setTotal(0);
        setError("操作审计暂不可用，请稍后重试。");
        return;
      }
      setItems(body.items || []);
      setTotal(body.total || 0);
      setCurrentPage(1);
    } catch (reason) {
      setItems([]);
      setTotal(0);
      setError(reason instanceof Error ? reason.message : "操作审计加载失败");
    } finally {
      setLoading(false);
    }
  }, [objectType, objectId]);

  useEffect(() => { void load(); }, [load]);

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
    <>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, marginBottom: 14 }}>
        <p style={{ fontSize: 12, color: "#8b929c", margin: 0 }}>共 {total} 条操作记录 · 只追加，保留 ≥7 年 · 时间均为 UTC</p>
        <button className="btn primary" onClick={exportCsv} disabled={!filtered.length}>导出 CSV</button>
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
        操作审计为只追加模式，所有采集、分析、发布与删除动作均在此留痕。日志保留期限 ≥7 年，满足金融监管合规要求。
      </p>
    </>
  );
}
