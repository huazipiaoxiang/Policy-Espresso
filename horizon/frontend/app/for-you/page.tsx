"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import BusinessMapPage from "@/app/business-map/page";
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
    money_loss: number;
    business_opportunity: number;
    reputation_loss: number;
    impact_total: number;
    affected_customer_count: number;
  };
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
  const { ready, role } = useAuth();
  const [policies, setPolicies] = useState<Policy[]>([]);
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
  }, [load, ready, role]);

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
  // 周期表格（本周/本月共用）：先按影响方向筛选，再按排序方式排序
  const periodSorted = useMemo(() => {
    let filtered = directionFilter
      ? periodList.filter((p) => (p.direction || "neutral") === directionFilter)
      : periodList;
    const keyword = searchText.trim().toLowerCase();
    if (keyword) {
      filtered = filtered.filter((p) => (p.title || "").toLowerCase().includes(keyword));
    }
    const sorted = [...filtered];
    if (sortBy === "impact") {
      sorted.sort((a, b) => (b.impact_dimensions?.impact_total ?? 0) - (a.impact_dimensions?.impact_total ?? 0));
    } else {
      sorted.sort((a, b) => (b.dispatched_at || "").localeCompare(a.dispatched_at || ""));
    }
    return sorted;
  }, [periodList, directionFilter, sortBy, searchText]);
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
        if (!response.ok) throw new Error(body?.error?.message || "AI 聚合生成失败");
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
        if (active) setDigestMd("AI 聚合暂时不可用，请稍后再试。");
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
          <p className="sub">AI 聚合本周 / 本月与你相关的政策动态 · 关联业务图谱</p>
        </div>
      </div>

      {error && <div className="notice" style={{ marginBottom: 16 }}>{error}<button className="link" onClick={() => void load()} style={{ marginLeft: 12 }}>重试</button></div>}

      <div className="section-title">
        <div>
          <div className="insight-eyebrow">✦ Your AI Policy Insights</div>
          <h2>本周 / 本月与你相关的政策动态</h2>
          <small>AI 聚合 · 基于你的订阅偏好匹配结果</small>
        </div>
        <Link href="/subscriptions" className="btn">管理订阅</Link>
      </div>
      <section className="ai-digest">
        <div className="ai-digest-head">
          <div className="ai-digest-titles">
            <h3>{digestTab === "week" ? "本周与你相关的政策动态" : "本月与你相关的政策动态"}</h3>
            <p>按你的订阅偏好（关注主题 × 关注市场）匹配本周期内发布的政策，由 AI 聚合为一段动态速览。</p>
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
            <div className="ai-digest-count" title={`${periodKey} 至 ${hkToday}`}>
              <b>{periodList.length}</b>
              <small>条相关动态</small>
            </div>
          </div>
        </div>
        {loading ? (
          <div className="ai-digest-body"><p className="ai-digest-placeholder">正在加载本期相关政策…</p></div>
        ) : periodList.length === 0 ? (
          <div className="ai-digest-body"><p className="ai-digest-placeholder">该周期内没有与你订阅偏好匹配的新发布政策，切换周期或调整订阅后再试。</p></div>
        ) : (
          <>
            {digestLoading ? (
              <p className="ai-digest-placeholder" style={{ marginTop: 14 }}>✦ AI 正在生成本{digestTab === "week" ? "周" : "月"}速览…</p>
            ) : digestMd ? (
              <details className="ai-digest-summary">
                <summary>✦ AI 本{digestTab === "week" ? "周" : "月"}速览：{digestMd.split("\n")[0]}</summary>
                <div className="inside">{digestMd}</div>
              </details>
            ) : null}
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
                  {periodSorted.length === 0 ? (
                    <tr><td colSpan={8} style={{ textAlign: "center", padding: 40, color: "#949aa3" }}>没有符合当前筛选条件的政策</td></tr>
                  ) : periodSorted.map((policy) => {
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
                            <div style={{ display: "flex", flexDirection: "column", gap: 2, fontSize: 12 }}>
                              <span>金钱损失 <b>{policy.impact_dimensions.money_loss}</b></span>
                              <span>业务机会 <b>{policy.impact_dimensions.business_opportunity}</b></span>
                              <span>声誉损失 <b>{policy.impact_dimensions.reputation_loss}</b></span>
                            </div>
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
          </>
        )}
        <div className="ai-digest-foot">
          ✦ 生成来源：{digestModel || "—"} · 数据时间：{periodKey} 至 {hkToday}（香港时区）
        </div>
      </section>

      {/* 业务图谱：与侧边栏「业务图谱」tab 打开的页面完全一致（与上方 AI 聚合区块保持大间距） */}
      <div style={{ marginTop: 36 }}>
        <BusinessMapPage />
      </div>
    </div>
  );
}
