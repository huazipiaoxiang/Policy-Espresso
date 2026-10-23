"use client";

import { useState } from "react";

const THEMES = [
  "跨境理财通", "大湾区金融", "反洗钱", "资本充足率", "流动性管理",
  "消费者保护", "数字银行", "绿色金融", "风险管理", "合规监管",
];

const JURISDICTIONS = [
  { value: "hk", label: "香港" },
  { value: "cn", label: "中国大陆" },
  { value: "gb", label: "英国" },
  { value: "sg", label: "新加坡" },
];

const BUSINESS_LINES = [
  "零售银行", "商业银行", "投资银行", "财富管理", "环球市场",
  "风险管理", "合规部门", "运营部门",
];

interface Subscription {
  id: string;
  type: "theme" | "jurisdiction" | "business_line";
  value: string;
  label: string;
  notify_email: boolean;
  notify_wecom: boolean;
}

export default function SubscriptionsPage() {
  const [subscriptions, setSubscriptions] = useState<Subscription[]>([
    { id: "1", type: "theme", value: "跨境理财通", label: "#跨境理财通", notify_email: true, notify_wecom: false },
    { id: "2", type: "jurisdiction", value: "hk", label: "香港", notify_email: true, notify_wecom: true },
    { id: "3", type: "business_line", value: "财富管理", label: "财富管理", notify_email: false, notify_wecom: true },
  ]);

  const [showAddModal, setShowAddModal] = useState(false);
  const [addType, setAddType] = useState<"theme" | "jurisdiction" | "business_line">("theme");
  const [addValue, setAddValue] = useState("");

  const handleAdd = () => {
    if (!addValue) return;
    const newSub: Subscription = {
      id: String(Date.now()),
      type: addType,
      value: addValue,
      label: addType === "theme" ? `#${addValue}` : addValue,
      notify_email: true,
      notify_wecom: false,
    };
    setSubscriptions([...subscriptions, newSub]);
    setShowAddModal(false);
    setAddValue("");
  };

  const handleRemove = (id: string) => {
    setSubscriptions(subscriptions.filter((s) => s.id !== id));
  };

  const toggleNotify = (id: string, channel: "email" | "wecom") => {
    setSubscriptions(
      subscriptions.map((s) =>
        s.id === id
          ? { ...s, [channel === "email" ? "notify_email" : "notify_wecom"]: !s[channel === "email" ? "notify_email" : "notify_wecom"] }
          : s
      )
    );
  };

  const themeSubs = subscriptions.filter((s) => s.type === "theme");
  const jurisdictionSubs = subscriptions.filter((s) => s.type === "jurisdiction");
  const businessLineSubs = subscriptions.filter((s) => s.type === "business_line");

  return (
    <main className="mx-auto max-w-content px-6 pb-10 pt-[72px]">
      <div className="mb-6">
        <div className="mb-1 text-[10px] uppercase tracking-wider text-[var(--text-3)]">My Subscriptions</div>
        <h1 className="text-[20px] font-semibold">我的订阅</h1>
        <p className="mt-1 text-[13px] text-[var(--text-2)]">
          订阅感兴趣的主题、地区或业务线，系统将推送相关政策更新
        </p>
      </div>

      <div className="mb-6 grid grid-cols-3 gap-4">
        <div className="card p-4">
          <div className="mb-2 text-[11px] text-[var(--text-3)]">主题订阅</div>
          <div className="font-mono text-[28px] font-semibold">{themeSubs.length}</div>
        </div>
        <div className="card p-4">
          <div className="mb-2 text-[11px] text-[var(--text-3)]">地区订阅</div>
          <div className="font-mono text-[28px] font-semibold">{jurisdictionSubs.length}</div>
        </div>
        <div className="card p-4">
          <div className="mb-2 text-[11px] text-[var(--text-3)]">业务线订阅</div>
          <div className="font-mono text-[28px] font-semibold">{businessLineSubs.length}</div>
        </div>
      </div>

      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-[16px] font-semibold">订阅管理</h2>
        <button
          onClick={() => setShowAddModal(true)}
          className="rounded-md bg-[var(--accent)] px-3 py-1.5 text-[12px] text-white hover:bg-[var(--accent)]/90"
        >
          + 新增订阅
        </button>
      </div>

      {themeSubs.length > 0 && (
        <div className="mb-6">
          <div className="mb-3 text-[13px] font-medium text-[var(--text-2)]">主题</div>
          <div className="space-y-2">
            {themeSubs.map((sub) => (
              <div key={sub.id} className="card flex items-center gap-3 p-3">
                <span className="rounded-full bg-[var(--accent)]/10 px-2.5 py-1 text-[12px] text-[var(--accent)]">
                  {sub.label}
                </span>
                <div className="ml-auto flex items-center gap-3">
                  <label className="flex items-center gap-1.5 text-[11px] text-[var(--text-2)]">
                    <input
                      type="checkbox"
                      checked={sub.notify_email}
                      onChange={() => toggleNotify(sub.id, "email")}
                      className="rounded"
                    />
                    邮件
                  </label>
                  <label className="flex items-center gap-1.5 text-[11px] text-[var(--text-2)]">
                    <input
                      type="checkbox"
                      checked={sub.notify_wecom}
                      onChange={() => toggleNotify(sub.id, "wecom")}
                      className="rounded"
                    />
                    企业微信
                  </label>
                  <button
                    onClick={() => handleRemove(sub.id)}
                    className="text-[11px] text-[var(--danger)] hover:underline"
                  >
                    取消订阅
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {jurisdictionSubs.length > 0 && (
        <div className="mb-6">
          <div className="mb-3 text-[13px] font-medium text-[var(--text-2)]">地区</div>
          <div className="space-y-2">
            {jurisdictionSubs.map((sub) => (
              <div key={sub.id} className="card flex items-center gap-3 p-3">
                <span className="rounded-full bg-[var(--surface-2)] px-2.5 py-1 text-[12px] text-[var(--text-2)]">
                  {sub.label}
                </span>
                <div className="ml-auto flex items-center gap-3">
                  <label className="flex items-center gap-1.5 text-[11px] text-[var(--text-2)]">
                    <input
                      type="checkbox"
                      checked={sub.notify_email}
                      onChange={() => toggleNotify(sub.id, "email")}
                      className="rounded"
                    />
                    邮件
                  </label>
                  <label className="flex items-center gap-1.5 text-[11px] text-[var(--text-2)]">
                    <input
                      type="checkbox"
                      checked={sub.notify_wecom}
                      onChange={() => toggleNotify(sub.id, "wecom")}
                      className="rounded"
                    />
                    企业微信
                  </label>
                  <button
                    onClick={() => handleRemove(sub.id)}
                    className="text-[11px] text-[var(--danger)] hover:underline"
                  >
                    取消订阅
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {businessLineSubs.length > 0 && (
        <div className="mb-6">
          <div className="mb-3 text-[13px] font-medium text-[var(--text-2)]">业务线</div>
          <div className="space-y-2">
            {businessLineSubs.map((sub) => (
              <div key={sub.id} className="card flex items-center gap-3 p-3">
                <span className="rounded-full bg-[var(--surface-2)] px-2.5 py-1 text-[12px] text-[var(--text-2)]">
                  {sub.label}
                </span>
                <div className="ml-auto flex items-center gap-3">
                  <label className="flex items-center gap-1.5 text-[11px] text-[var(--text-2)]">
                    <input
                      type="checkbox"
                      checked={sub.notify_email}
                      onChange={() => toggleNotify(sub.id, "email")}
                      className="rounded"
                    />
                    邮件
                  </label>
                  <label className="flex items-center gap-1.5 text-[11px] text-[var(--text-2)]">
                    <input
                      type="checkbox"
                      checked={sub.notify_wecom}
                      onChange={() => toggleNotify(sub.id, "wecom")}
                      className="rounded"
                    />
                    企业微信
                  </label>
                  <button
                    onClick={() => handleRemove(sub.id)}
                    className="text-[11px] text-[var(--danger)] hover:underline"
                  >
                    取消订阅
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {subscriptions.length === 0 && (
        <div className="card p-12 text-center">
          <div className="mb-2 text-[14px] text-[var(--text-2)]">暂无订阅</div>
          <div className="text-[12px] text-[var(--text-3)]">
            点击上方"新增订阅"按钮，开始订阅感兴趣的内容
          </div>
        </div>
      )}

      {showAddModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="card w-[480px] p-6">
            <h3 className="mb-4 text-[16px] font-semibold">新增订阅</h3>
            <div className="mb-4">
              <label className="mb-2 block text-[12px] text-[var(--text-2)]">订阅类型</label>
              <div className="flex gap-2">
                <button
                  onClick={() => setAddType("theme")}
                  className={`flex-1 rounded-md border px-3 py-2 text-[12px] ${
                    addType === "theme"
                      ? "border-[var(--accent)] bg-[var(--accent)]/10 text-[var(--accent)]"
                      : "border-[var(--border)] bg-[var(--surface-2)] text-[var(--text-2)]"
                  }`}
                >
                  主题
                </button>
                <button
                  onClick={() => setAddType("jurisdiction")}
                  className={`flex-1 rounded-md border px-3 py-2 text-[12px] ${
                    addType === "jurisdiction"
                      ? "border-[var(--accent)] bg-[var(--accent)]/10 text-[var(--accent)]"
                      : "border-[var(--border)] bg-[var(--surface-2)] text-[var(--text-2)]"
                  }`}
                >
                  地区
                </button>
                <button
                  onClick={() => setAddType("business_line")}
                  className={`flex-1 rounded-md border px-3 py-2 text-[12px] ${
                    addType === "business_line"
                      ? "border-[var(--accent)] bg-[var(--accent)]/10 text-[var(--accent)]"
                      : "border-[var(--border)] bg-[var(--surface-2)] text-[var(--text-2)]"
                  }`}
                >
                  业务线
                </button>
              </div>
            </div>
            <div className="mb-4">
              <label className="mb-2 block text-[12px] text-[var(--text-2)]">选择</label>
              {addType === "theme" && (
                <div className="flex flex-wrap gap-2">
                  {THEMES.map((theme) => (
                    <button
                      key={theme}
                      onClick={() => setAddValue(theme)}
                      className={`rounded-full border px-3 py-1 text-[12px] ${
                        addValue === theme
                          ? "border-[var(--accent)] bg-[var(--accent)]/10 text-[var(--accent)]"
                          : "border-[var(--border)] bg-[var(--surface-2)] text-[var(--text-2)]"
                      }`}
                    >
                      #{theme}
                    </button>
                  ))}
                </div>
              )}
              {addType === "jurisdiction" && (
                <div className="flex flex-wrap gap-2">
                  {JURISDICTIONS.map((j) => (
                    <button
                      key={j.value}
                      onClick={() => setAddValue(j.value)}
                      className={`rounded-full border px-3 py-1 text-[12px] ${
                        addValue === j.value
                          ? "border-[var(--accent)] bg-[var(--accent)]/10 text-[var(--accent)]"
                          : "border-[var(--border)] bg-[var(--surface-2)] text-[var(--text-2)]"
                      }`}
                    >
                      {j.label}
                    </button>
                  ))}
                </div>
              )}
              {addType === "business_line" && (
                <div className="flex flex-wrap gap-2">
                  {BUSINESS_LINES.map((bl) => (
                    <button
                      key={bl}
                      onClick={() => setAddValue(bl)}
                      className={`rounded-full border px-3 py-1 text-[12px] ${
                        addValue === bl
                          ? "border-[var(--accent)] bg-[var(--accent)]/10 text-[var(--accent)]"
                          : "border-[var(--border)] bg-[var(--surface-2)] text-[var(--text-2)]"
                      }`}
                    >
                      {bl}
                    </button>
                  ))}
                </div>
              )}
            </div>
            <div className="flex gap-2">
              <button
                onClick={handleAdd}
                disabled={!addValue}
                className="flex-1 rounded-md bg-[var(--accent)] px-4 py-2 text-[13px] text-white hover:bg-[var(--accent)]/90 disabled:opacity-50"
              >
                确认订阅
              </button>
              <button
                onClick={() => {
                  setShowAddModal(false);
                  setAddValue("");
                }}
                className="flex-1 rounded-md border border-[var(--border)] bg-[var(--surface-2)] px-4 py-2 text-[13px] text-[var(--text-2)] hover:bg-[var(--surface)]"
              >
                取消
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
