export const SUBSCRIPTION_STORAGE_KEY = "horizon-subscription-preferences";

// 关注主题与后端主题受控词表（seed/themes.yaml）保持一致：
// “为你推荐”按主题标签精确匹配，改名会导致永远匹配不到政策。
export const TOPIC_OPTIONS = [
  { value: "跨境理财通", label: "跨境理财通" },
  { value: "跨境支付", label: "跨境支付" },
  { value: "人民币国际化", label: "人民币国际化" },
  { value: "贷款与贴息", label: "贷款与贴息" },
  { value: "债券与资本市场", label: "债券与资本市场" },
  { value: "资产管理", label: "资产管理" },
  { value: "保险与再保险", label: "保险与再保险" },
  { value: "税务与优惠", label: "税务与优惠" },
  { value: "数据跨境", label: "数据跨境" },
  { value: "绿色与转型金融", label: "绿色与转型金融" },
  { value: "金融科技与虚拟资产", label: "金融科技与虚拟资产" },
  { value: "专业资格互认", label: "专业资格互认" },
  { value: "市场准入与牌照", label: "市场准入与牌照" },
  { value: "资本与流动性要求", label: "资本与流动性要求" },
  { value: "消费者保护", label: "消费者保护" },
  { value: "反洗钱与制裁", label: "反洗钱与制裁" },
];

export const MARKET_OPTIONS = [
  { value: "hk", label: "香港", jurisdictions: ["HK"] },
  { value: "cn", label: "中国内地", jurisdictions: ["CN", "GD", "SZ", "GBA", "MO"] },
  { value: "gb", label: "英国", jurisdictions: ["GB"] },
  { value: "sg", label: "新加坡", jurisdictions: ["SG"] },
  { value: "eu", label: "欧盟", jurisdictions: ["EU"] },
];

export interface SubscriptionPreferences {
  topics: string[];
  markets: string[];
  businessArea: string;
  emailNotify: boolean;
}

export const DEFAULT_SUBSCRIPTIONS: SubscriptionPreferences = {
  topics: ["跨境理财通", "人民币国际化", "债券与资本市场"],
  markets: ["hk", "cn"],
  businessArea: "财富管理与零售银行",
  emailNotify: true,
};

export function loadSubscriptions(): SubscriptionPreferences {
  if (typeof window === "undefined") return DEFAULT_SUBSCRIPTIONS;
  try {
    const stored = JSON.parse(window.localStorage.getItem(SUBSCRIPTION_STORAGE_KEY) || "null") as Partial<SubscriptionPreferences> | null;
    if (!stored) return DEFAULT_SUBSCRIPTIONS;
    const topicValues = new Set(TOPIC_OPTIONS.map((item) => item.value));
    const marketValues = new Set(MARKET_OPTIONS.map((item) => item.value));
    const storedTopics = Array.isArray(stored.topics)
      ? stored.topics.filter((item): item is string => typeof item === "string" && topicValues.has(item))
      : [];
    const storedMarkets = Array.isArray(stored.markets)
      ? stored.markets.filter((item): item is string => typeof item === "string" && marketValues.has(item))
      : [];
    return {
      // 词表改版后旧浏览器里的取值会被全部过滤掉，此时回落到默认偏好而不是留下空订阅
      topics: storedTopics.length ? storedTopics : DEFAULT_SUBSCRIPTIONS.topics,
      markets: storedMarkets.length ? storedMarkets : DEFAULT_SUBSCRIPTIONS.markets,
      businessArea: typeof stored.businessArea === "string" ? stored.businessArea : DEFAULT_SUBSCRIPTIONS.businessArea,
      emailNotify: typeof stored.emailNotify === "boolean" ? stored.emailNotify : DEFAULT_SUBSCRIPTIONS.emailNotify,
    };
  } catch {
    return DEFAULT_SUBSCRIPTIONS;
  }
}

export function saveSubscriptions(preferences: SubscriptionPreferences) {
  window.localStorage.setItem(SUBSCRIPTION_STORAGE_KEY, JSON.stringify(preferences));
}
