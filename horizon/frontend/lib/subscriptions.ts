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

// 历史数据里部分政策的主题标签是英文（早期分析管线未对齐受控词表），
// 这里维护 英文标签 → 受控中文主题 的兼容映射，使订阅匹配不遗漏；
// 未命中的英文标签（如机构名 hkma/sfc、地域名 hong_kong、非金融主题 healthcare）视为不匹配。
export const THEME_ALIASES: Record<string, string> = {
  // 人民币国际化
  offshore_RMB: "人民币国际化",
  exchange_rate: "人民币国际化",
  foreign_exchange_framework: "人民币国际化",
  monetary_policy: "人民币国际化",
  // 跨境支付
  trade_finance: "跨境支付",
  "trade-finance": "跨境支付",
  cross_border_trade_finance: "跨境支付",
  "cross-border_trade_finance": "跨境支付",
  bilateral_currency_settlement: "跨境支付",
  // 债券与资本市场
  bond: "债券与资本市场",
  bond_market: "债券与资本市场",
  bond_auction: "债券与资本市场",
  "bond-tokenization": "债券与资本市场",
  sovereign_bond: "债券与资本市场",
  infrastructure_finance: "债券与资本市场",
  infrastructure: "债券与资本市场",
  public_private_partnership: "债券与资本市场",
  Belt_and_Road: "债券与资本市场",
  derivatives: "债券与资本市场",
  clearing: "债券与资本市场",
  // 资产管理
  retail_investment: "资产管理",
  // 数据跨境
  cross_border_data_sharing: "数据跨境",
  // 绿色与转型金融
  green_finance: "绿色与转型金融",
  sustainable_finance: "绿色与转型金融",
  green_technology: "绿色与转型金融",
  carbon_neutrality: "绿色与转型金融",
  sustainable_development: "绿色与转型金融",
  ESG_disclosure: "绿色与转型金融",
  carbon_markets: "绿色与转型金融",
  // 金融科技与虚拟资产
  fintech: "金融科技与虚拟资产",
  virtual_assets: "金融科技与虚拟资产",
  tokenization: "金融科技与虚拟资产",
  digital_securities: "金融科技与虚拟资产",
  digital_infrastructure: "金融科技与虚拟资产",
  "corporate-treasury": "金融科技与虚拟资产",
  artificial_intelligence: "金融科技与虚拟资产",
  ai_in_finance: "金融科技与虚拟资产",
  responsible_ai: "金融科技与虚拟资产",
  sandbox: "金融科技与虚拟资产",
  governance: "金融科技与虚拟资产",
  // 贷款与贴息
  msme_support: "贷款与贴息",
  // 市场准入与牌照
  regulation: "市场准入与牌照",
  regulatory_framework: "市场准入与牌照",
  regulatory_guidance: "市场准入与牌照",
  intermediaries: "市场准入与牌照",
  // 资本与流动性要求
  banking_regulation: "资本与流动性要求",
  interest_rate: "资本与流动性要求",
  financial_stability: "资本与流动性要求",
  credit_risk: "资本与流动性要求",
  liquidity_management: "资本与流动性要求",
  // 消费者保护
  public_awareness: "消费者保护",
  // 反洗钱与制裁
  cybersecurity: "反洗钱与制裁",
  fraud_prevention: "反洗钱与制裁",
};

/** 主题标签归一化：英文别名映射为受控中文主题，其余原样返回。 */
export function normalizeTheme(theme: string): string {
  return THEME_ALIASES[theme] ?? theme;
}

/** 政策主题是否命中已选订阅主题（兼容英文别名）。 */
export function matchesSelectedTopic(policyThemes: string[], selectedLabels: string[]): boolean {
  return policyThemes.some((theme) => selectedLabels.includes(normalizeTheme(theme)));
}

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
