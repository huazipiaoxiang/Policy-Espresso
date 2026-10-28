"use client";

import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { API_BASE, demoApiHeaders } from "@/lib/auth";
import { JURISDICTION_LABELS } from "@/lib/labels";

interface Source {
  id: string;
  code: string;
  name: string;
  org: string;
  jurisdiction: string;
  tier: number;
  adapter: string;
  url: string;
  enabled: boolean;
  health: {
    consecutive_fail?: number;
    last_ok_at?: string;
    circuit_open_until?: string | null;
    last_errors?: string[];
  };
}

type SourceStatus = "normal" | "degraded" | "circuit" | "disabled";
type FilterKey = "all" | "normal" | "unhealthy" | "disabled";

function statusOf(source: Source): SourceStatus {
  if (!source.enabled) return "disabled";
  const failures = source.health.consecutive_fail || 0;
  const circuitUntil = source.health.circuit_open_until;
  if (failures >= 5 || (circuitUntil && new Date(circuitUntil) > new Date())) return "circuit";
  if (failures > 0) return "degraded";
  return "normal";
}

function dateLabel(value?: string) {
  return value ? new Date(value).toLocaleString("zh-CN", { hour12: false }) : "尚无成功记录";
}

export default function SourcesPage() {
  const searchParams = useSearchParams();
  const initialView = searchParams.get("view");
  const [activeFilter, setActiveFilter] = useState<FilterKey>(initialView === "unhealthy" ? "unhealthy" : "all");
  const [sources, setSources] = useState<Source[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetch(`${API_BASE}/sources?page=1&page_size=100`, { headers: demoApiHeaders(), cache: "no-store" });
      const body = await response.json();
      if (!response.ok) throw new Error(body?.error?.message || "数据源加载失败");
      setSources(body.items || []);
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "数据源加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    if (searchParams.get("view") === "unhealthy") setActiveFilter("unhealthy");
  }, [searchParams]);

  const counts = useMemo(() => ({
    all: sources.length,
    normal: sources.filter((source) => statusOf(source) === "normal").length,
    unhealthy: sources.filter((source) => ["degraded", "circuit"].includes(statusOf(source))).length,
    disabled: sources.filter((source) => statusOf(source) === "disabled").length,
  }), [sources]);
  const rows = sources.filter((source) => {
    const status = statusOf(source);
    if (activeFilter === "normal") return status === "normal";
    if (activeFilter === "unhealthy") return status === "degraded" || status === "circuit";
    if (activeFilter === "disabled") return status === "disabled";
    return true;
  });
  const metrics: { key: FilterKey; label: string; value: number }[] = [
    { key: "all", label: "全部数据源", value: counts.all },
    { key: "normal", label: "正常或待检查", value: counts.normal },
    { key: "unhealthy", label: "波动或熔断", value: counts.unhealthy },
    { key: "disabled", label: "已停用", value: counts.disabled },
  ];

  async function update(source: Source, action: "toggle" | "run") {
    setBusyId(source.id);
    setNotice("");
    try {
      const response = await fetch(`${API_BASE}/sources/${source.id}${action === "run" ? "/run" : ""}`, {
        method: action === "run" ? "POST" : "PATCH",
        headers: { ...demoApiHeaders(), "Content-Type": "application/json" },
        ...(action === "toggle" ? { body: JSON.stringify({ enabled: !source.enabled }) } : {}),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body?.error?.message || "操作失败");
      setNotice(action === "run"
        ? `「${source.name}」抓取完成：发现 ${body.discovered} 条，新增 ${body.created} 条，更新 ${body.updated} 条${body.analyzed ? `，已分析 ${body.analyzed} 篇` : ""}${body.failed ? `，失败 ${body.failed} 项` : ""}`
        : `「${source.name}」已${source.enabled ? "停用" : "启用"}`);
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "操作失败");
    } finally {
      setBusyId("");
    }
  }

  return (
    <main>
      <div className="pagehead">
        <div><div className="eyebrow">DATA SOURCES</div><h1>数据源</h1><p className="sub">监管数据采集渠道与真实健康状态 · 共 {sources.length} 个数据源</p></div>
        <button className="btn" onClick={() => void load()} disabled={loading}>刷新状态</button>
      </div>

      <div className="grid4">{metrics.map((metric) => <button className="metric" key={metric.key} onClick={() => setActiveFilter(metric.key)} style={{ textAlign: "left" }}><small>{metric.label}</small><b>{metric.value}</b><span>点击查看对应数据源</span></button>)}</div>
      {notice && <div className="info" style={{ marginTop: 16 }}>{notice}</div>}
      {error && <div className="notice" style={{ marginTop: 16 }}>{error}</div>}

      <section className="panel" style={{ marginTop: 18 }}>
        <div className="panelhead"><h2>{metrics.find((metric) => metric.key === activeFilter)?.label}</h2><small>{rows.length} 个</small></div>
        <div className="tablewrap"><table><thead><tr><th>来源</th><th>市场</th><th>等级</th><th>采集方式</th><th>最近成功</th><th>状态</th><th>操作</th></tr></thead><tbody>
          {loading ? <tr><td colSpan={7} style={{ padding: 36, textAlign: "center" }}>加载中…</td></tr> : rows.length === 0 ? <tr><td colSpan={7} style={{ padding: 36, textAlign: "center" }}>当前分类没有数据源</td></tr> : rows.map((source) => {
            const status = statusOf(source);
            const statusLabel = status === "circuit" ? "熔断" : status === "degraded" ? "波动" : status === "disabled" ? "已停用" : source.health.last_ok_at ? "正常" : "待检查";
            return <tr key={source.id}>
              <td style={{ minWidth: 180 }}><div className="policytitle">{source.name}<small>{source.org || source.code}</small></div></td>
              <td>{JURISDICTION_LABELS[source.jurisdiction] || source.jurisdiction || "—"}</td>
              <td><span className={`badge ${source.tier === 1 ? "red" : source.tier === 2 ? "amber" : ""}`}>T{source.tier}</span></td>
              <td><span className="badge">{source.adapter}</span><br />{/^https?:\/\//i.test(source.url) ? <a href={source.url} target="_blank" rel="noreferrer" className="link">官方入口</a> : <small>手动上传</small>}</td>
              <td style={{ whiteSpace: "nowrap" }}>{dateLabel(source.health.last_ok_at)}</td>
              <td><span className={`badge ${status === "normal" ? "green" : status === "degraded" ? "amber" : status === "circuit" ? "red" : ""}`}>{statusLabel}</span>{source.health.last_errors?.[0] && <small title={source.health.last_errors[0]}>有错误记录</small>}</td>
              <td><div className="rowflex"><button className="link" disabled={busyId === source.id || !source.enabled} onClick={() => void update(source, "run")}>{busyId === source.id ? "抓取中…" : "立即抓取"}</button><button className="link" disabled={busyId === source.id} onClick={() => void update(source, "toggle")}>{source.enabled ? "停用" : "启用"}</button></div></td>
            </tr>;
          })}
        </tbody></table></div>
      </section>
      <div className="info" style={{ marginTop: 18 }}><strong>采集策略：</strong>每天香港时间 09:00 抓取全部启用数据源，成功后只分析新增或内容变化的文档；单源失败不会影响其他来源。连续失败达到阈值后自动熔断。</div>
      <p className="footnote">数据源和状态均来自后端数据库。立即抓取会当场执行本轮采集并分析新增内容，源文件较多时需要等待片刻，运行记录可在系统概览的任务记录中查看。</p>
    </main>
  );
}
