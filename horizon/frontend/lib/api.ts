// 服务端数据访问。MVP 用 X-API-Key；云端换 OIDC 后仅改此处。
const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000/api/v1";
const API_KEY = process.env.HORIZON_API_KEY ?? "dev-local-key";

export interface AnalyticsOverview {
  today_new: number;
  pending_review: number;
  p0_p1_open: number;
  avg_response_min: number | null;
  sources_total: number;
  sources_unhealthy: number;
  last_crawl_at: string | null;
}

export interface PolicyItem {
  id: string;
  title: string;
  issuing_body: string;
  priority: "P0" | "P1" | "P2" | "P3";
  status: string;
  score_total: number;
  jurisdiction: string;
  themes: string[];
  target_entity_status: string;
  foreign_bank_differential: boolean;
  published_at: string | null;
  summary_zh: string;
  confidence: number;
}

export interface PolicyDetail extends PolicyItem {
  url: string;
  document_id: string;
  doc_number: string | null;
  effective_at: string | null;
  expiry_at: string | null;
  applicable_scope: string;
  applicable_entities_text: string;
  group_affiliate_mention: Record<string, unknown>;
  amounts: { value: number; currency: string; unit: string; description: string; quote: string }[];
  deadlines: { date: string; description: string; quote: string }[];
  obligations: { actor: string; action: string; condition: string; quote: string }[];
  incentives: { beneficiary: string; benefit: string; condition: string; quote: string }[];
  prompt_version: string;
  document: {
    id: string;
    title: string;
    url: string;
    lang: string;
    published_at: string | null;
    content_text: string;
    attachments: Attachment[];
  } | null;
  assessments: {
    id: string;
    scores: Record<string, { score: number | null; reason: string; evidence_ids: string[] }>;
    direction: string;
    score_total: number;
    priority: string;
    transmission_chain: string[];
    affected: {
      business_lines: string[];
      segments: string[];
      exposure_range: { low: number; high: number; currency: string; unit: string; basis: string; confidence: number } | null;
    };
    recommended_actions: { owner: string; action: string; deadline: string }[];
    case_links: { case_id: string; similarity: number; takeaway: string }[];
    confidence: number;
    model: string;
    prompt_version: string;
  }[];
  evidence: {
    id: string;
    document_id: string;
    span_start: number;
    span_end: number;
    quote: string;
    field_name: string;
  }[];
  scope_judgements: {
    entity_id: string;
    result: string;
    rule_hits: { category: string; quote: string; span_start: number; span_end: number }[];
    llm_reason: string;
    conflict: boolean;
  }[];
}

async function get<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      headers: { "X-API-Key": API_KEY },
      next: { revalidate: 30 },
    });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null; // API 未就绪时前端照常渲染空态
  }
}

export const getOverview = () => get<AnalyticsOverview>("/analytics/overview");
export const getPolicies = (query = "") =>
  get<{ items: PolicyItem[]; total: number }>(`/policies?page=1&page_size=50${query}`);
export const getPolicy = (id: string) => get<PolicyDetail>(`/policies/${id}`);

// ===== Phase 1 文档流 =====

export interface Attachment {
  name: string;
  url: string;
  local_path: string | null;
  parsed_text_path: string | null;
  status?: string; // pending/parsed/failed（附件解析状态，Phase 1 补齐）
  char_count?: number;
}

export interface DocumentItem {
  id: string;
  source_id: string;
  title: string;
  url: string;
  lang: string;
  published_at: string | null;
  fetched_at: string | null;
  status: string;
  duplicate_of: string | null;
  attachments: Attachment[];
  content_len: number;
}

export interface DocumentDetail extends DocumentItem {
  canonical_url: string;
  content_hash: string;
  content_text: string;
  versions: { version_no: number; changed_at: string; changed_ratio: number; minor_edit: boolean }[];
}

export interface DiffItem {
  op: string;
  before: string;
  after: string;
}

export const getDocuments = (query = "") =>
  get<{ items: DocumentItem[]; total: number }>(`/documents?page=1&page_size=50${query}`);
export const getDocument = (id: string) => get<DocumentDetail>(`/documents/${id}`);
export const getVersionDiff = (docId: string, versionNo: number) =>
  get<{ document_id: string; version_no: number; changed_at: string; changed_ratio: number; minor_edit: boolean; diff: DiffItem[] }>(
    `/documents/${docId}/versions/${versionNo}/diff`,
  );

// ===== Phase 3 审核台 / 审计 / 预警 =====

export interface ReviewTaskItem {
  id: string;
  policy_id: string;
  policy_title: string;
  priority: string;
  score_total: number;
  level: number;
  assignee: string;
  status: string;
  sla_due_at: string | null;
  target_entity_status: string;
  foreign_bank_differential: boolean;
}

export interface AuditItem {
  id: string;
  actor: string;
  action: string;
  object_type: string;
  object_id: string;
  before: Record<string, unknown>;
  after: Record<string, unknown>;
  reason: string;
  at: string;
}

export interface AlertItem {
  id: string;
  assessment_id: string | null;
  title: string;
  body_md: string;
  channel_scope: Record<string, unknown>;
  status: string;
  created_at: string;
}

export const getReviewTasks = () => get<{ items: ReviewTaskItem[] }>("/review-tasks");
export const getAudit = (query = "") => get<{ items: AuditItem[]; total: number }>(`/admin/audit?page_size=100${query}`);
export const getAlerts = () => get<{ items: AlertItem[] }>("/alerts");

export interface SourceItem {
  id: string;
  code: string;
  name: string;
  org: string;
  jurisdiction: string;
  tier: number;
  adapter: string;
  url: string;
  lang: string;
  poll_interval_min: number;
  enabled: boolean;
  health: Record<string, unknown>;
}

export const getSources = () => get<{ items: SourceItem[]; total: number }>("/sources?page_size=50");

// ===== Phase 4 案例库 / 业务图谱 / 政策 Studio =====

export interface CaseItem {
  id: string;
  title: string;
  year: number;
  jurisdiction: string;
  themes: string[];
  outcome: string;
  impact: string;
  similarity: number;
}

export interface CaseDetail extends CaseItem {
  policy_summary: string;
  hsbc_response: string;
  lessons: string[];
  source_refs: unknown[];
}

export const getCases = (query = "") => get<{ items: CaseItem[] }>(`/cases?page_size=50${query}`);
export const getCase = (id: string) => get<CaseDetail>(`/cases/${id}`);

export interface BusinessMapData {
  themes: string[];
  matrix: Record<string, {
    name: string;
    sensitivity: Record<string, number>;
    cells: Record<string, { policy_count: number; avg_score: number }>;
  }>;
  top_themes: Record<string, number>;
  months: number;
}

export const getBusinessMap = () => get<BusinessMapData>("/business-map");

export interface CorpusDocItem {
  doc_id: string;
  title: string;
  issuing_bodies: string[];
  doc_number: string;
  published_at: string;
  validity: string;
  themes: string[];
  effective: boolean;
}

export const getCorpus = () => get<{ themes: string[]; docs: CorpusDocItem[]; disclaimer: string }>("/studio/corpus");
export const getStudioProjects = () =>
  get<{ items: { id: string; name: string; theme: string; status: string; created_at: string }[] }>("/studio/projects");

export interface ProposalDetail {
  id: string;
  project_id: string;
  version: number;
  sections: {
    title: string;
    disclaimer: string;
    baseline: { theme: string; current_state: string; key_instruments: string[] }[];
    proposals: {
      id: string;
      theme: string;
      tier: string;
      current_basis: { doc: string; clause: string; quote: string }[];
      non_conflict_argument: string;
      draft_clause: string;
      impact: { on_hk: string; on_hsbc: string; on_industry: string };
      risks: { risk: string; mitigation: string; likelihood: string }[];
      kpis: string[];
      precedents: string[];
    }[];
  };
  boundary_check: { items: { proposal_id: string; status: string; issue: string; suggestion: string }[] };
  reviewer_notes: string;
  created_at: string;
  corpus: { doc_id: string; title: string; published_at: string; validity: string; themes: string[] }[];
  disclaimer: string;
}

export const getProposal = (id: string) => get<ProposalDetail>(`/studio/proposals/${id}`);
export const getStudioProposals = (projectId: string) =>
  get<{ items: { id: string; version: number; created_at: string; proposals: number }[] }>(
    `/studio/projects/${projectId}/proposals`,
  );

// ===== 设置（只读系统状态与配置快照，脱敏） =====

export interface SystemSettings {
  runtime: {
    db: string;
    llm_provider: string;
    storage_backend: string;
    scheduler: string;
    timezone: string;
    version: string;
  };
  llm: {
    provider: string;
    model_tier: Record<string, string>;
    dashscope_configured: boolean;
    ollama_base_url: string;
  };
  storage: {
    backend: string;
    storage_dir_configured: boolean;
    oss_configured: boolean;
    oss_bucket: string;
  };
  crawl: {
    user_agent: string;
    max_rps_per_domain: number;
    respect_robots: boolean;
    max_attachments_per_doc: number;
    max_items_per_source: number;
  };
  notify: {
    inapp: string;
    email: string;
    wecom: string;
    feishu: string;
  };
  security: {
    auth: string;
    job_trigger_token_configured: boolean;
  };
}

export const getSettings = () => get<SystemSettings>("/settings");
