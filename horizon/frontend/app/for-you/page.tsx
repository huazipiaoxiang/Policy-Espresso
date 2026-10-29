"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import { API_BASE, demoApiHeaders } from "@/lib/auth";
import { JURISDICTION_LABELS } from "@/lib/labels";
import {
  DEFAULT_SUBSCRIPTIONS,
  MARKET_OPTIONS,
  TOPIC_OPTIONS,
  loadSubscriptions,
  type SubscriptionPreferences,
} from "@/lib/subscriptions";

interface Policy {
  id: string;
  title: string;
  summary_zh: string;
  themes: string[];
  jurisdiction: string;
  issuing_body: string;
  published_at: string | null;
}

function dateLabel(policy: Policy) {
  return policy.published_at ? policy.published_at.slice(0, 10) : "日期未注明";
}

function PolicyCard({ policy }: { policy: Policy }) {
  return (
    <article className="consumer-card">
      <span className="badge green">已审核发布</span>
      <div className="rowflex">
        {policy.themes.map((topic) => <span className="topic-chip" key={topic}>{topic}</span>)}
      </div>
      <h3>{policy.title}</h3>
      <p>{policy.summary_zh || "暂未生成摘要，请查看政策原文。"}</p>
      <div className="consumer-card-footer">
        <div className="rowflex">
          <small>{JURISDICTION_LABELS[policy.jurisdiction] || policy.jurisdiction || "市场未注明"}</small>
          <small>·</small>
          <small>{policy.issuing_body || "发文机构未注明"}</small>
          <small>·</small>
          <small>{dateLabel(policy)}</small>
        </div>
        <Link href={`/policies/${policy.id}`} className="btn" style={{ padding: "6px 12px", fontSize: 11 }}>
          阅读解读 →
        </Link>
      </div>
    </article>
  );
}

export default function ForYouPage() {
  const { ready, role } = useAuth();
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [preferences, setPreferences] = useState<SubscriptionPreferences>(DEFAULT_SUBSCRIPTIONS);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

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
  const latest = policies.slice(0, 8);
  const matched = useMemo(() => policies.filter((policy) => {
    const topicMatch = policy.themes.some((theme) => selectedTopics.includes(theme));
    const marketMatch = selectedJurisdictions.has(policy.jurisdiction);
    return topicMatch && marketMatch;
  }), [policies, selectedJurisdictions, selectedTopics]);

  return (
    <div className="content">
      <div className="pagehead">
        <div>
          <div className="eyebrow">POLICY INTELLIGENCE</div>
          <h1>为你推荐</h1>
          <p className="sub">发现最新监管动态 · 无需订阅即可浏览已发布政策情报</p>
        </div>
        <Link href="/subscriptions" className="btn">管理我的订阅</Link>
      </div>

      <div className="consumer-hero">
        <div>
          <span className="badge green">已审核发布</span>
          <h2>最新政策情报速览</h2>
          <p>以下摘要来自当前数据库中已审核发布的政策；关注主题和关注市场共同决定“与你相关”的匹配结果。</p>
          <div className="rowflex">
            {selectedTopics.length ? selectedTopics.map((topic) => <span className="topic-chip" key={topic}>{topic}</span>) : <small>尚未选择关注主题</small>}
          </div>
        </div>
        <div className="hero-count"><b>{policies.length}</b><small>条已发布政策</small></div>
      </div>

      {error && <div className="notice" style={{ marginBottom: 16 }}>{error}<button className="link" onClick={() => void load()} style={{ marginLeft: 12 }}>重试</button></div>}

      <div className="section-title"><h2>最新发布</h2><small>{loading ? "加载中…" : `显示 ${latest.length} 条，共 ${policies.length} 条`}</small></div>
      {loading ? <div className="empty-state">正在加载已发布政策…</div> : latest.length ? (
        <div className="consumer-grid">{latest.map((policy) => <PolicyCard policy={policy} key={policy.id} />)}</div>
      ) : <div className="empty-state">暂无已审核发布的政策</div>}

      <div className="section-title">
        <h2>与你相关</h2>
        <small>{preferences.topics.length && preferences.markets.length ? `基于 ${selectedTopics.length} 个关注主题和 ${preferences.markets.length} 个关注市场` : "请先选择关注主题和市场"}</small>
      </div>
      {!loading && matched.length > 0 && (
        <>
          <div className="consumer-grid">{matched.map((policy) => <PolicyCard policy={policy} key={policy.id} />)}</div>
          <div className="empty-state">已按你保存的订阅偏好匹配 {matched.length} 条政策。<br /><Link href="/subscriptions" className="btn primary" style={{ marginTop: 10 }}>调整订阅偏好</Link></div>
        </>
      )}
      {!loading && matched.length === 0 && (
        <div className="empty-state">
          {preferences.topics.length && preferences.markets.length ? "当前已发布政策中没有同时匹配关注主题和市场的内容" : "尚未设置完整的订阅偏好"}
          <br /><small>政策必须具有对应主题标签，且属于所选市场，才会出现在这里。</small>
          <div><Link href="/subscriptions" className="btn primary" style={{ marginTop: 12 }}>选择关注主题和市场</Link></div>
        </div>
      )}
    </div>
  );
}
