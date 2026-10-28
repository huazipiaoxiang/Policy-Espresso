"use client";

import { useEffect, useState } from "react";
import {
  DEFAULT_SUBSCRIPTIONS,
  MARKET_OPTIONS,
  TOPIC_OPTIONS,
  loadSubscriptions,
  saveSubscriptions,
  type SubscriptionPreferences,
} from "@/lib/subscriptions";

export default function SubscriptionsPage() {
  const [preferences, setPreferences] = useState<SubscriptionPreferences>(DEFAULT_SUBSCRIPTIONS);
  const [ready, setReady] = useState(false);
  const [notice, setNotice] = useState("");

  useEffect(() => {
    setPreferences(loadSubscriptions());
    setReady(true);
  }, []);

  const selectedTopics = preferences.topics;
  const selectedMarkets = preferences.markets;
  const selectedTopicLabels = TOPIC_OPTIONS.filter((topic) => selectedTopics.includes(topic.value)).map((topic) => topic.label);
  const selectedMarketLabels = MARKET_OPTIONS.filter((market) => selectedMarkets.includes(market.value)).map((market) => market.label);

  function toggleValue(key: "topics" | "markets", value: string) {
    setNotice("");
    setPreferences((current) => ({
      ...current,
      [key]: current[key].includes(value) ? current[key].filter((item) => item !== value) : [...current[key], value],
    }));
  }

  function save() {
    saveSubscriptions(preferences);
    setNotice("偏好已保存，“为你推荐”将按这些主题和市场匹配已发布政策。");
  }

  return (
    <div className="content">
      <div className="pagehead">
        <div>
          <div className="eyebrow">MY SUBSCRIPTIONS</div>
          <h1>我的订阅</h1>
          <p className="sub">管理个人关注主题和政策通知偏好</p>
        </div>
      </div>

      {notice && <div className="info" role="status" style={{ marginBottom: 16 }}>{notice}</div>}
      <div className="subscription-layout">
        <div className="panel">
          <div className="panelhead"><h2>我的关注主题</h2><small>{selectedTopics.length} 个已选</small></div>
          <div className="sectionbody">
            <p className="sub" style={{ marginBottom: 4 }}>选择你关注的政策主题，“为你推荐”将匹配具有相同主题标签的已发布政策</p>
            <div className="subscription-list">
              {TOPIC_OPTIONS.map((topic) => (
                <label className="sub-option" key={topic.value}>
                  <input type="checkbox" checked={selectedTopics.includes(topic.value)} onChange={() => toggleValue("topics", topic.value)} disabled={!ready} />
                  {topic.label}
                </label>
              ))}
            </div>
            {selectedTopics.length > 0 ? (
              <div className="note-line">已选 {selectedTopics.length} 个主题：{selectedTopicLabels.map((label) => <span className="topic-chip" key={label} style={{ marginLeft: 6 }}>{label}</span>)}</div>
            ) : (
              <div className="empty-state" style={{ marginTop: 14 }}>尚未选择任何关注主题<br /><small>请从上方列表中勾选感兴趣的主题</small></div>
            )}
          </div>
        </div>

        <div className="panel">
          <div className="panelhead"><h2>我的业务与通知</h2><small>个人偏好设置</small></div>
          <div className="sectionbody">
            <div style={{ marginBottom: 18 }}>
              <label className="form-label" htmlFor="business-area">业务领域</label>
              <select
                id="business-area"
                className="filter"
                style={{ width: "100%", marginTop: 6 }}
                value={preferences.businessArea}
                onChange={(event) => { setNotice(""); setPreferences((current) => ({ ...current, businessArea: event.target.value })); }}
              >
                <option>财富管理与零售银行</option>
                <option>工商金融</option>
                <option>环球银行及资本市场</option>
                <option>合规与风险管理</option>
              </select>
            </div>

            <div style={{ marginBottom: 18 }}>
              <span className="form-label">关注市场</span>
              <div className="rowflex" style={{ marginTop: 6 }}>
                {MARKET_OPTIONS.map((market) => (
                  <label className="sub-option" key={market.value} style={{ padding: "8px 10px" }}>
                    <input type="checkbox" checked={selectedMarkets.includes(market.value)} onChange={() => toggleValue("markets", market.value)} disabled={!ready} />
                    {market.label}
                  </label>
                ))}
              </div>
              {selectedMarketLabels.length > 0 && <div style={{ marginTop: 8 }}>{selectedMarketLabels.map((label) => <span className="topic-chip" key={label}>{label}</span>)}</div>}
            </div>

            <div style={{ marginBottom: 18 }}>
              <span className="form-label">邮件通知</span>
              <div className="rowflex" style={{ marginTop: 6, padding: "12px 14px", border: "1px solid #e6e8eb", borderRadius: 7, justifyContent: "space-between" }}>
                <div>
                  <div style={{ fontSize: 13, fontWeight: 600 }}>每日政策速递</div>
                  <div style={{ fontSize: 11, color: "#8b929c", marginTop: 2 }}>保存通知偏好；当前尚未接入邮件发送服务</div>
                </div>
                <button
                  className="btn"
                  style={{ padding: "6px 14px", fontSize: 12, background: preferences.emailNotify ? "var(--red)" : "#fff", color: preferences.emailNotify ? "#fff" : "#363a42", borderColor: preferences.emailNotify ? "var(--red)" : "#d7d9de" }}
                  onClick={() => { setNotice(""); setPreferences((current) => ({ ...current, emailNotify: !current.emailNotify })); }}
                >
                  {preferences.emailNotify ? "已开启" : "已关闭"}
                </button>
              </div>
            </div>

            <div className="note-line">偏好只保存在当前浏览器。点击保存后，“为你推荐”会使用已保存的主题和市场。</div>
            <div style={{ marginTop: 16 }}><button className="btn primary" onClick={save} disabled={!ready}>保存偏好设置</button></div>
          </div>
        </div>
      </div>
    </div>
  );
}
