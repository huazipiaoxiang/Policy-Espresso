"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { API_BASE, demoApiHeaders } from "@/lib/auth";

interface Overview {
  today_new: number;
  pending_review: number;
  p0_p1_open: number;
  sources_total: number;
  sources_unhealthy: number;
  last_crawl_at: string | null;
}

interface JobRun {
  id: string;
  job_type: string;
  source_id: string | null;
  status: string;
  stats: Record<string, unknown>;
  error: string | null;
  started_at: string;
  finished_at: string | null;
}

interface ScheduledJob {
  job_type: string;
  next_run_at: string | null;
  last_run: JobRun | null;
}

interface Settings {
  runtime: { db: string; llm_provider: string; storage_backend: string; scheduler: string; version: string };
}

const jobLabels: Record<string, string> = {
  crawl_all: "每日抓取", analyze_pending: "新增与变更分析", health_check: "数据源健康检查", heartbeat: "每周心跳",
};

function dateLabel(value: string | null) {
  return value ? new Date(value).toLocaleString("zh-CN", { hour12: false }) : "尚无记录";
}

export default function HealthPage() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [jobs, setJobs] = useState<ScheduledJob[]>([]);
  const [history, setHistory] = useState<JobRun[]>([]);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    const get = async (path: string) => {
      const response = await fetch(`${API_BASE}${path}`, { headers: demoApiHeaders(), cache: "no-store" });
      const body = await response.json();
      if (!response.ok) throw new Error(body?.error?.message || "系统运行数据加载失败");
      return body;
    };
    try {
      const [overviewData, jobData, historyData, settingsData] = await Promise.all([
        get("/analytics/overview"), get("/jobs/status"), get("/jobs?page=1&page_size=30"), get("/settings"),
      ]);
      setOverview(overviewData);
      setJobs(jobData.jobs || []);
      setHistory(historyData.items || []);
      setSettings(settingsData);
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "系统运行数据加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const metrics = [
    { label: "今日新增政策", value: overview?.today_new ?? 0, note: "按香港时区入库时间统计", href: "/policies?view=today_new" },
    { label: "待审核", value: overview?.pending_review ?? 0, note: `其中 ${overview?.p0_p1_open ?? 0} 条 P0/P1 待处理`, href: "/policies?view=pending_review" },
    { label: "数据源异常", value: overview?.sources_unhealthy ?? 0, note: "存在连续失败或熔断", href: "/sources?view=unhealthy" },
    { label: "数据源总数", value: overview?.sources_total ?? 0, note: "包含启用和停用来源", href: "/sources" },
  ];
  const failures = history.filter((job) => job.status === "failed");
  const normalSources = Math.max(0, (overview?.sources_total ?? 0) - (overview?.sources_unhealthy ?? 0));

  return (
    <main>
      <div className="pagehead"><div><div className="eyebrow">SYSTEM ADMIN</div><h1>系统概览</h1><p className="sub">真实运行状态、政策指标与调度记录</p></div><button className="btn" onClick={() => void load()} disabled={loading}>刷新数据</button></div>
      {error && <div className="notice" style={{ marginBottom: 16 }}>{error}</div>}
      <div className="grid4">{metrics.map((metric) => <Link href={metric.href} className="metric" key={metric.label} style={{ textDecoration: "none", color: "inherit" }}><small>{metric.label}</small><b>{metric.value}</b><span>{metric.note}</span></Link>)}</div>

      <div className="twocol" style={{ marginTop: 18 }}>
        <section className="panel">
          <div className="panelhead"><h2>数据源状态</h2><Link href="/sources" className="link">管理 →</Link></div>
          <div className="sectionbody">
            <div className="barrow"><span>正常、待检查或停用</span><div className="track"><div className="fill green" style={{ width: `${overview?.sources_total ? normalSources / overview.sources_total * 100 : 0}%` }} /></div><strong>{normalSources}</strong></div>
            <div className="barrow"><span>异常</span><div className="track"><div className="fill red" style={{ width: `${overview?.sources_total ? overview.sources_unhealthy / overview.sources_total * 100 : 0}%` }} /></div><strong>{overview?.sources_unhealthy ?? 0}</strong></div>
            <div className="divider" /><p className="sub">共 {overview?.sources_total ?? 0} 个数据源 · 最近成功抓取：{dateLabel(overview?.last_crawl_at ?? null)}</p>
          </div>
        </section>
        <section className="panel">
          <div className="panelhead"><h2>运行时状态</h2><Link href="/settings" className="link">设置 →</Link></div>
          <div className="sectionbody"><div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div className="rowflex" style={{ justifyContent: "space-between" }}><span className="sub">数据库</span><span className={`badge ${settings?.runtime.db === "ok" ? "green" : "red"}`}>{settings?.runtime.db === "ok" ? "正常" : "异常"}</span></div>
            <div className="rowflex" style={{ justifyContent: "space-between" }}><span className="sub">AI 提供方</span><strong>{settings?.runtime.llm_provider || "—"}</strong></div>
            <div className="rowflex" style={{ justifyContent: "space-between" }}><span className="sub">存储后端</span><strong>{settings?.runtime.storage_backend || "—"}</strong></div>
            <div className="rowflex" style={{ justifyContent: "space-between" }}><span className="sub">调度器</span><span className="badge green">{settings?.runtime.scheduler || "—"}</span></div>
            <div className="rowflex" style={{ justifyContent: "space-between" }}><span className="sub">版本</span><strong>v{settings?.runtime.version || "—"}</strong></div>
          </div></div>
        </section>
      </div>

      <section className="panel" style={{ marginTop: 18 }}>
        <div className="panelhead"><h2>自动任务</h2><small>最近结果与下次执行时间</small></div>
        <div className="tablewrap"><table><thead><tr><th>任务</th><th>最近执行</th><th>状态</th><th>下次执行</th><th>结果 / 错误</th></tr></thead><tbody>
          {jobs.map((job) => <tr key={job.job_type}><td><strong>{jobLabels[job.job_type] || job.job_type}</strong></td><td>{dateLabel(job.last_run?.started_at ?? null)}</td><td><span className={`badge ${job.last_run?.status === "ok" ? "green" : job.last_run?.status === "failed" ? "red" : ""}`}>{job.last_run?.status === "ok" ? "成功" : job.last_run?.status === "failed" ? "失败" : job.last_run?.status || "未执行"}</span></td><td>{dateLabel(job.next_run_at)}</td><td style={{ maxWidth: 360 }}>{job.last_run?.error || (job.last_run ? JSON.stringify(job.last_run.stats) : "等待首次执行")}</td></tr>)}
        </tbody></table></div>
      </section>

      <section className="panel" style={{ marginTop: 18 }}>
        <div className="panelhead"><h2>最近任务失败记录</h2><small>取最近 30 条任务记录</small></div>
        <div className="tablewrap"><table><thead><tr><th>时间</th><th>任务</th><th>来源</th><th>状态</th><th>错误详情</th></tr></thead><tbody>
          {failures.length === 0 ? <tr><td colSpan={5} style={{ padding: 32, textAlign: "center" }}>最近任务记录中没有失败</td></tr> : failures.map((job) => <tr key={job.id}><td>{dateLabel(job.started_at)}</td><td>{jobLabels[job.job_type] || job.job_type}</td><td>{job.source_id || "全部来源"}</td><td><span className="badge red">失败</span></td><td>{job.error || "未记录错误详情"}</td></tr>)}
        </tbody></table></div>
      </section>
      <p className="footnote">本页不展示合成异常或演示指标；任务失败详情来自 JobRun，完整操作记录请查看审计日志。</p>
    </main>
  );
}
