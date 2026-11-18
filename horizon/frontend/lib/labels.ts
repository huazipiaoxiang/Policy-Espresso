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

export const JURISDICTION_LABELS: Record<string, string> = {
  HK: "香港", CN: "中国内地", GD: "广东", SZ: "深圳", GBA: "大湾区",
  MO: "澳门", GB: "英国", SG: "新加坡", EU: "欧盟",
};

// 文档语言代码 → 中文含义（后端 detect_lang 产出 zh-Hant / zh-Hans / en）
export function langLabel(lang?: string | null): string {
  if (!lang) return "中文";
  const key = lang.trim().toLowerCase().replace(/_/g, "-");
  if (key.startsWith("zh-hant") || key === "zh-tw" || key === "zh-hk" || key === "zh-mo") return "繁体中文";
  if (key.startsWith("zh-hans") || key === "zh-cn" || key === "zh-sg") return "简体中文";
  if (key.startsWith("en")) return "英文";
  if (key.startsWith("zh")) return "中文";
  return lang;
}

export const PRIORITY_LABELS: Record<string, string> = {
  P0: "P0（最高优先）",
  P1: "P1（高优先）",
  P2: "P2（中等优先）",
  P3: "P3（低优先）",
};

export const DECISION_LABELS: Record<string, string> = {
  approve: "通过", reject: "驳回", request_info: "要求补充资料",
};

export const TASK_STATUS_LABELS: Record<string, string> = {
  pending: "待处理", claimed: "已领取", approved: "已通过", rejected: "已驳回", needs_info: "待补资料",
};

// 审计 / 执行轨迹动作标签（政策生命周期事件，audit_log.action）
export const AUDIT_ACTION_LABELS: Record<string, string> = {
  ai_analyze: "AI 分析完成",
  submit_review: "提交人工审核",
  skip_review: "跳过审核",
  claim_task: "领取审核任务",
  review_approve: "审核通过",
  review_reject: "审核驳回",
  review_request_info: "退回补充",
  dispatch: "发布政策",
  delete_policy: "删除政策",
  upload_document: "上传原文",
  delete_document: "删除原文",
  refresh_scorecard: "刷新评分卡",
  update_policy: "更新政策",
  repair_fixture_content: "修复数据",
};
