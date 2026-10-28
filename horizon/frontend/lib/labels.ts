// 界面中文标签：后端枚举只在此处映射一次，避免各页面各写一份。
export const POLICY_STATUS_LABELS: Record<string, string> = {
  draft: "草稿", ai_checked: "已分析", pending_review: "待审核", in_review: "审核中",
  approved: "审核通过", published: "已发布", rejected: "已驳回", needs_info: "待补资料",
};

// 未接入 LLM 时影响分保持为 0，界面按"未评定"显示，避免把占位 0 当成模型结论
export function impactScoreLabel(score: number, digits = 0, withUnit = true): string {
  if (score <= 0) return "未评定";
  return withUnit ? `${score.toFixed(digits)} 分` : score.toFixed(digits);
}

export const ANALYSIS_MODEL_LABELS: Record<string, string> = {
  "offline-rules": "离线规则（未接入 AI）",
  "mock-deterministic": "演示模型（未接入 AI）",
};

export function analysisModelLabel(model?: string | null): string {
  if (!model) return "未记录";
  return ANALYSIS_MODEL_LABELS[model] ?? model;
}

export const DIRECTION_LABELS: Record<string, string> = {
  positive: "利好", negative: "利空", mixed: "利弊并存", neutral: "中性",
};

// 8 维评分卡（02 §5.2）：direction 不参与加权，权重只对 7 个评分维度生效
export const SCORE_DIMENSION_ORDER = [
  "relevance", "exposure", "urgency", "certainty", "actionability", "differential", "compliance",
];

export const SCORE_DIMENSION_LABELS: Record<string, string> = {
  relevance: "相关性",
  exposure: "暴露规模",
  urgency: "紧迫性",
  certainty: "确定性",
  actionability: "可行动性",
  differential: "差异化",
  compliance: "合规敏感度",
};

export const SCORE_DIMENSION_WEIGHTS: Record<string, string> = {
  relevance: "25%",
  exposure: "20%",
  urgency: "15%",
  certainty: "10%",
  actionability: "10%",
  differential: "15%",
  compliance: "5%",
};

export const JURISDICTION_LABELS: Record<string, string> = {
  HK: "香港", CN: "中国内地", GD: "广东", SZ: "深圳", GBA: "大湾区",
  MO: "澳门", GB: "英国", SG: "新加坡", EU: "欧盟",
};

export const DECISION_LABELS: Record<string, string> = {
  approve: "通过", reject: "驳回", request_info: "要求补充资料",
};

export const TASK_STATUS_LABELS: Record<string, string> = {
  pending: "待处理", claimed: "已领取", approved: "已通过", rejected: "已驳回", needs_info: "待补资料",
};
