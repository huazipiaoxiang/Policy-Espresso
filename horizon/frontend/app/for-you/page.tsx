"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import { API_BASE, demoApiHeaders } from "@/lib/auth";
import { DIRECTION_LABELS, JURISDICTION_LABELS } from "@/lib/labels";
import {
  DEFAULT_SUBSCRIPTIONS,
  MARKET_OPTIONS,
  TOPIC_OPTIONS,
  loadSubscriptions,
  matchesSelectedTopic,
  normalizeTheme,
  type SubscriptionPreferences,
} from "@/lib/subscriptions";

interface Policy {
  id: string;
  title: string;
  themes: string[];
  jurisdiction: string;
  issuing_body: string;
  published_at: string | null;
  dispatched_at: string | null; // 系统发布动作时间（区分于官方发布日期）
  direction: string | null; // 影响方向（positive/negative/mixed/neutral）
  priority: string;
  score_total: number;
  impacted_domains: string[];
  foreign_bank_differential: boolean;
  impact_dimensions?: {
    business_loss: number;
    business_opportunity: number;
    reputation_risk: number;
    impact_total: number;
    affected_customer_count: number;
  };
  unassessed?: boolean;
  preprocess?: {
    loss_pct: number;
    profit_pct: number;
    reputation_pct: number;
    opportunity_pct: number;
    keywords: string[];
    affected_business: { code: string; name: string }[];
    customer_segments: string[];
  } | null;
}

interface Recommendation {
  items: Policy[];
  match_mode: "rm_matched" | "fallback";
  rm: string | null;
  matched_customer_count: number;
  scores_source: string;
  // 与本行无直接关联（相关度 0）而未进入列表的政策数量
  hidden_no_impact?: number;
  // week：本周新入库；all：本周无新入库时回退最近入库
  window?: "week" | "all";
  period: { start: string; end: string };
}

function dateLabel(value: string | null | undefined) {
  return value ? value.slice(0, 10) : "—";
}

function directionBadgeClass(direction: string | null): string {
  if (direction === "positive") return "green";
  if (direction === "negative") return "red";
  if (direction === "mixed") return "amber";
  return "";
}

export default function ForYouPage() {
  const { ready, role, username } = useAuth();
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [reco, setReco] = useState<Recommendation | null>(null);
  const [recoLoading, setRecoLoading] = useState(true);
  const [preferences, setPreferences] = useState<SubscriptionPreferences>(DEFAULT_SUBSCRIPTIONS);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // 本周 / 本月 AI 聚合
  const [digestTab, setDigestTab] = useState<"week" | "month">("week");
  const [digestMd, setDigestMd] = useState("");
  const [digestCount, setDigestCount] = useState(0);
  const [digestModel, setDigestModel] = useState("");
  const [digestLoading, setDigestLoading] = useState(false);

  // 政策列表筛选与排序
  const [directionFilter, setDirectionFilter] = useState("");
  const [sortBy, setSortBy] = useState<"impact" | "date">("impact");
  const [searchText, setSearchText] = useState("");
  // 分页：每页 10 条，最多展示 100 条（10 页）
  const [page, setPage] = useState(1);

  // 推荐列表：本周新入库政策 + 预处理表格三维分（后端已按综合分降序）
  const loadReco = useCallback(async () => {
    setRecoLoading(true);
    try {
      const query = username ? `?username=${encodeURIComponent(username)}` : "";
      const response = await fetch(`${API_BASE}/policies/for-you${query}`, {
        headers: demoApiHeaders(),
        cache: "no-store",
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body?.error?.message || "推荐政策加载失败");
      setReco(body);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "推荐政策加载失败");
    } finally {
      setRecoLoading(false);
    }
  }, [username]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const all: Policy[] = [];
      let page = 1;
      while (true) {
        const response = await fetch(`${API_BASE}/policies?status=published&page=${page}&page_size=100`, {
          headers: demoApiHeaders(),
          cache: "no-store",
        });
        const body = await response.json();
        if (!response.ok) throw new Error(body?.error?.message || "已发布政策加载失败");
        all.push(...(body.items || []));
        if (all.length >= body.total || !body.items?.length) break;
        page += 1;
      }
      setPolicies(all);
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "已发布政策加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!ready) return;
    setPreferences(loadSubscriptions());
    void load();
    void loadReco();
  }, [load, loadReco, ready, role]);

  const selectedTopics = useMemo(
    () => TOPIC_OPTIONS.filter((topic) => preferences.topics.includes(topic.value)).map((topic) => topic.label),
    [preferences.topics],
  );
  const selectedJurisdictions = useMemo(
    () => new Set(MARKET_OPTIONS.filter((market) => preferences.markets.includes(market.value)).flatMap((market) => market.jurisdictions)),
    [preferences.markets],
  );
  const matched = useMemo(() => policies.filter((policy) => {
    // 主题匹配走归一化（兼容历史英文标签，如 fintech → 金融科技与虚拟资产）
    const topicMatch = matchesSelectedTopic(policy.themes, selectedTopics);
    const marketMatch = selectedJurisdictions.has(policy.jurisdiction);
    return topicMatch && marketMatch;
  }), [policies, selectedJurisdictions, selectedTopics]);

  // 本周口径：香港时区的今天与 7 天前，只做 date-only 字符串比较，不做时区转换
  const hkToday = useMemo(() => new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Hong_Kong" }), []);
  const weekAgo = useMemo(() => {
    const [year, month, day] = hkToday.split("-").map(Number);
    return new Date(Date.UTC(year, month - 1, day - 7)).toISOString().slice(0, 10);
  }, [hkToday]);
  const monthlyStart = useMemo(() => `${hkToday.slice(0, 8)}01`, [hkToday]);
  const inRange = useCallback((policy: Policy, start: string) => {
    // 本周/本月窗口按「系统发布动作时间」判断（无发布记录时回退官方日期），
    // 与「今日已发布」口径一致：用户预期是最近收到发布的政策，而非官方发文日期。
    const key = (policy.dispatched_at || policy.published_at || "").slice(0, 10);
    return key >= start && key <= hkToday;
  }, [hkToday]);
  const weekly = useMemo(() => matched.filter((policy) => inRange(policy, weekAgo)), [matched, inRange, weekAgo]);
  const monthly = useMemo(() => matched.filter((policy) => inRange(policy, monthlyStart)), [matched, inRange, monthlyStart]);
  // 本月表格：按影响程度从高到低排序
  const monthSorted = useMemo(
    () => [...monthly].sort((a, b) => (b.impact_dimensions?.impact_total ?? 0) - (a.impact_dimensions?.impact_total ?? 0)),
    [monthly],
  );

  // AI 聚合：按当前周期把匹配政策交给后端 LLM 生成速览
  const periodList = digestTab === "week" ? weekly : monthly;
  const periodKey = digestTab === "week" ? weekAgo : monthlyStart;
  // 推荐列表：本周新入库政策（后端已按预处理综合分降序），前端只做筛选与按日期重排
  const allSorted = useMemo(() => {
    let filtered = reco?.items ?? [];
    if (directionFilter) {
      filtered = filtered.filter((policy) => (policy.direction || "neutral") === directionFilter);
    }
    const keyword = searchText.trim().toLowerCase();
    if (keyword) {
      filtered = filtered.filter((policy) =>
        (policy.title || "").toLowerCase().includes(keyword) ||
        (policy.issuing_body || "").toLowerCase().includes(keyword)
      );
    }
    if (sortBy === "date") {
      return [...filtered].sort((a, b) =>
        (b.dispatched_at || b.published_at || "").localeCompare(a.dispatched_at || a.published_at || "")
      );
    }
    return filtered; // 综合分排序由后端给出（预处理表格口径）
  }, [reco, directionFilter, sortBy, searchText]);

  // 分页：每页 10 条
  const PAGE_SIZE = 10;
  const totalPages = Math.max(1, Math.ceil(allSorted.length / PAGE_SIZE));
  const pagedPolicies = allSorted.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  // 筛选/排序/搜索变化时回到第一页
  useEffect(() => {
    setPage(1);
  }, [directionFilter, sortBy, searchText]);

  useEffect(() => {
    if (!periodList.length) {
      setDigestMd("");
      setDigestCount(0);
      return;
    }
    let active = true;
    setDigestLoading(true);
    fetch(`${API_BASE}/policies/digest`, {
      method: "POST",
      headers: { ...demoApiHeaders(), "Content-Type": "application/json" },
      body: JSON.stringify({ period: digestTab, policy_ids: periodList.map((policy) => policy.id) }),
    })
      .then(async (response) => {
        const body = await response.json();
        if (!response.ok) throw new Error(body?.error?.message || "速览生成失败");
        return body;
      })
      .then((body) => {
        if (active) {
          setDigestMd(body.digest_md || "");
          setDigestCount(body.policy_count || 0);
          setDigestModel(body.model || "");
        }
      })
      .catch(() => {
        if (active) setDigestMd("速览暂时不可用，请稍后再试。");
      })
      .finally(() => {
        if (active) setDigestLoading(false);
      });
    return () => {
      active = false;
    };
  }, [digestTab, periodKey, periodList]);

  return (
    <div className="content">
      <div className="pagehead">
        <div>
          <div className="eyebrow">POLICY INTELLIGENCE</div>
          <h1>为你推荐</h1>
          <p className="sub">本周 / 本月与你相关的政策动态 · 关联业务图谱</p>
        </div>
      </div>

      {error && <div className="notice" style={{ marginBottom: 16 }}>{error}<button className="link" onClick={() => void load()} style={{ marginLeft: 12 }}>重试</button></div>}

      <div className="section-title">
        <div>
          <div className="insight-eyebrow">✦ Your Policy Insights</div>
          <h2>本周 / 本月与你相关的政策动态</h2>
          <small>政策动态 · 基于你的订阅偏好匹配结果</small>
        </div>
        <Link href="/subscriptions" className="btn">管理订阅</Link>
      </div>
      <section className="ai-digest">
        <div className="ai-digest-head">
          <div className="ai-digest-titles">
            <h3>{digestTab === "week" ? "本周与你相关的政策动态" : "本月与你相关的政策动态"}</h3>
            <p>按你的订阅偏好（关注主题 × 关注市场）匹配本周期内发布的政策，自动聚合为一段动态速览。</p>
          </div>
          <div className="ai-digest-side">
            <div className="ai-digest-tabs" role="tablist">
              <button
                type="button"
                role="tab"
                aria-selected={digestTab === "week"}
                className={digestTab === "week" ? "active" : ""}
                onClick={() => setDigestTab("week")}
              >
                本周
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={digestTab === "month"}
                className={digestTab === "month" ? "active" : ""}
                onClick={() => setDigestTab("month")}
              >
                本月
              </button>
            </div>
            <div className="ai-digest-count" title="全部已发布政策">
              <b>{allSorted.length}</b>
              <small>条政策</small>
            </div>
          </div>
        </div>
        {loading ? (
          <div className="ai-digest-body"><p className="ai-digest-placeholder">正在加载本期相关政策…</p></div>
        ) : periodList.length === 0 ? (
          <div className="ai-digest-body"><p className="ai-digest-placeholder">该周期内没有与你订阅偏好匹配的新发布政策，切换周期或调整订阅后再试。</p></div>
        ) : (
          <div className="ai-digest-body">
            {digestLoading ? (
              <p className="ai-digest-placeholder" style={{ marginTop: 14 }}>✦ 正在生成本{digestTab === "week" ? "周" : "月"}速览…</p>
            ) : digestMd ? (
              <details className="ai-digest-summary">
                <summary>✦ 本{digestTab === "week" ? "周" : "月"}速览：{digestMd.split("\n")[0]}</summary>
                <div className="inside">{digestMd}</div>
              </details>
            ) : null}
          </div>
        )}
        {/* 为你推荐：即使没有客户画像或聚合内容为空，也展示预处理表格三维分数的推荐列表 */}
        <div className="notice" style={{ margin: "12px 0", fontSize: 12 }}>
          {reco?.window === "all" && (reco.items?.length ?? 0) > 0 && (
            <span style={{ color: "#b08900" }}>本周暂无新入库的已发布政策，已回退展示最近入库的政策</span>
          )}
          {reco && (
            <span style={{ color: "#8b929c" }}>
              {reco.window === "all" ? " · " : ""}统计区间 {reco.period.start} ~ {reco.period.end}
            </span>
          )}
        </div>
            <div className="rowflex" style={{ margin: "12px 0", gap: 12, flexWrap: "wrap" }}>
              <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12 }}>
                <span>影响方向</span>
                <select className="filter" value={directionFilter} onChange={(e) => setDirectionFilter(e.target.value)}>
                  <option value="">全部</option>
                  <option value="positive">利好</option>
                  <option value="negative">利空</option>
                  <option value="mixed">利弊并存</option>
                  <option value="neutral">中性</option>
                </select>
              </label>
              <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12 }}>
                <span>排序</span>
                <select className="filter" value={sortBy} onChange={(e) => setSortBy(e.target.value as "impact" | "date")}>
                  <option value="impact">按影响程度</option>
                  <option value="date">按发布日期</option>
                </select>
              </label>
              <input
                className="search"
                value={searchText}
                onChange={(e) => setSearchText(e.target.value)}
                placeholder="搜索政策名称…"
                style={{ width: 200 }}
              />
            </div>
            <div className="ai-digest-table tablewrap">
              <table>
                <thead>
                  <tr>
                    <th>政策名称</th>
                    <th>市场</th>
                    <th>相关主题</th>
                    <th>影响方向</th>
                    <th>影响维度评分</th>
                    <th>受影响的其他业务线</th>
                    <th>发布日期</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {recoLoading ? (
                    <tr><td colSpan={8} style={{ textAlign: "center", padding: 40, color: "#949aa3" }}>正在加载本周推荐政策…</td></tr>
                  ) : allSorted.length === 0 ? (
                    <tr><td colSpan={8} style={{ textAlign: "center", padding: 40, color: "#949aa3" }}>当前没有符合条件的推荐政策，请调整筛选或稍后再试</td></tr>
                  ) : pagedPolicies.map((policy) => {
                    const topics = [...new Set(policy.themes.map(normalizeTheme))].filter(Boolean);
                    const dispatched = policy.dispatched_at || policy.published_at;
                    return (
                      <tr key={policy.id}>
                        <td style={{ minWidth: 200, maxWidth: 280 }}>
                          <div className="policytitle">
                            <Link href={`/policies/${policy.id}`}>
                              {policy.title}
                              {policy.foreign_bank_differential && <span title="存在外资行差异条款"> ⚠</span>}
                            </Link>
                            <small>{policy.issuing_body || "发文机构未注明"}</small>
                          </div>
                        </td>
                        <td><span className="badge">{JURISDICTION_LABELS[policy.jurisdiction] || policy.jurisdiction || "—"}</span></td>
                        <td>
                          <div className="rowflex">
                            {topics.length
                              ? topics.slice(0, 2).map((topic) => <span className="badge" key={topic}>{topic}</span>)
                              : "—"}
                            {topics.length > 2 && <small style={{ color: "#949aa3" }}>+{topics.length - 2}</small>}
                          </div>
                        </td>
                        <td>
                          <span className={`badge ${directionBadgeClass(policy.direction)}`}>
                            {DIRECTION_LABELS[policy.direction || ""] ?? "—"}
                          </span>
                        </td>
                        <td style={{ whiteSpace: "nowrap" }}>
                          {policy.impact_dimensions ? (
                            policy.impact_dimensions.business_loss || policy.impact_dimensions.business_opportunity || policy.impact_dimensions.reputation_risk ? (
                              <div style={{ display: "flex", flexDirection: "column", gap: 2, fontSize: 12 }}>
                                <span>业务损失 <b>{policy.impact_dimensions.business_loss}</b></span>
                                <span>业务机会 <b>{policy.impact_dimensions.business_opportunity}</b></span>
                                <span>声誉风险 <b>{policy.impact_dimensions.reputation_risk}</b></span>
                                <span style={{ color: "#8b929c" }}>综合 <b>{policy.impact_dimensions.impact_total}</b></span>
                              </div>
                            ) : <span style={{ fontSize: 12, color: "#8b929c" }}>无直接影响</span>
                          ) : "—"}
                        </td>
                        <td>
                          <div className="rowflex">
                            {policy.impacted_domains?.length
                              ? policy.impacted_domains.slice(0, 3).map((line) => <span className="badge" key={line}>{line}</span>)
                              : "—"}
                          </div>
                        </td>
                        <td style={{ whiteSpace: "nowrap" }} title={dispatched ? `官方发布日期：${dateLabel(policy.published_at)}` : undefined}>
                          {dateLabel(dispatched)}
                        </td>
                        <td style={{ whiteSpace: "nowrap" }}><Link href={`/policies/${policy.id}`} className="link">解读 →</Link></td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {allSorted.length > 0 && (
              <div className="rowflex" style={{ justifyContent: "center", marginTop: 12, gap: 12, alignItems: "center" }}>
                <button className="btn" disabled={page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>
                  ← 上一页
                </button>
                <span style={{ fontSize: 12, color: "#8b929c" }}>
                  第 {page} / {totalPages} 页 · 共 {allSorted.length} 条
                </span>
                <button className="btn" disabled={page >= totalPages} onClick={() => setPage((p) => Math.min(totalPages, p + 1))}>
                  下一页 →
                </button>
              </div>
            )}
        {reco?.hidden_no_impact ? (
          <p className="footnote" style={{ marginTop: 8 }}>
            已隐藏 {reco.hidden_no_impact} 条与本行无直接关联的政策（相关度为 0，不计入影响评分）
          </p>
        ) : null}
        <div className="ai-digest-foot">
          ✦ 生成来源：{digestModel || "—"} · 数据时间：{periodKey} 至 {hkToday}（香港时区）
        </div>
      </section>
    </div>
  );
}
