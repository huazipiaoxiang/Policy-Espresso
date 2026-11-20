"use client";

import { useCallback, useEffect, useState } from "react";
import { API_BASE, demoApiHeaders } from "@/lib/auth";
import { DIRECTION_LABELS, JURISDICTION_LABELS, analysisModelLabel } from "@/lib/labels";

// 「政策跟踪报告」模块（政策运营专员视角）：
// 邮件由系统接入的跟进 Agent 现场生成（政策要点 + 影响判断 + 受影响客户概况 + 使用者反馈）；
// Agent 不可用时退回本地模板，保证按钮始终可用、不会出现「生成失败」空界面。

interface TrackingAssessment {
  direction: string;
  score_total: number;
  priority: string;
  confidence: number;
  model: string;
  transmission_chain: string[];
  affected: {
    business_lines?: string[];
    segments?: string[];
    exposure_range?: { low: number; high: number; currency: string; unit: string; basis: string } | null;
  };
  recommended_actions: (string | { action: string; owner?: string; deadline?: string })[];
}

export interface TrackingPolicy {
  id: string;
  title: string;
  doc_number: string | null;
  issuing_body: string;
  published_at: string | null;
  effective_at: string | null;
  jurisdiction: string;
  policy_type: string;
  priority: string;
  score_total: number;
  confidence: number;
  summary_zh: string;
  themes: string[];
  impacted_domains: string[];
  url: string;
  assessments: TrackingAssessment[];
}

interface GeneratedEmail {
  subject: string;
  body: string;
  model: string;
  generated_by: string;
  generated_at: string;
}

/** 本地兜底用的受影响客户统计（结构同 /affected-customers 接口）。 */
interface LocalCustomerStats {
  total_customers: number;
  loan_balance_total_cny_yi: number;
  other_bank_loans_total_cny_yi: number;
  overseas_customers: number;
  match_rule?: string;
  source?: string;
  by_business_line?: { business_line: string; customers: number; loan_balance_cny_yi: number }[];
  by_segment?: { segment: string; customers: number; loan_balance_cny_yi: number }[];
  top_customers?: {
    name_masked: string;
    business_line: string;
    segment?: string;
    loan_balance_cny_yi: number;
    other_bank_loans_cny_yi: number;
  }[];
}

function localCustomerLines(stats: LocalCustomerStats | null): string[] {
  if (!stats) {
    return ["受影响客户统计暂不可用，可在 Horizon 政策解读页的「受影响客户概况」中查看完整名单。"];
  }
  if (!stats.total_customers) {
    return ["客户库中暂未匹配到受影响客户，建议核实政策适用主体与业务线标注。"];
  }
  const lines = [
    `按客户库全量匹配，共 ${stats.total_customers} 户客户受影响：本行贷款合计 `
      + `${stats.loan_balance_total_cny_yi} 亿元，他行贷款合计 ${stats.other_bank_loans_total_cny_yi} 亿元，`
      + `含海外业务客户 ${stats.overseas_customers} 户。`,
  ];
  const lineBuckets = stats.by_business_line ?? [];
  if (lineBuckets.length) {
    lines.push(`业务线分布：${lineBuckets.map((item) => `${item.business_line} ${item.customers} 户（贷款 ${item.loan_balance_cny_yi} 亿元）`).join("、")}`);
  }
  const segmentBuckets = stats.by_segment ?? [];
  if (segmentBuckets.length) {
    lines.push(`客群分布：${segmentBuckets.map((item) => `${item.segment} ${item.customers} 户`).join("、")}`);
  }
  const top = (stats.top_customers ?? []).slice(0, 5);
  if (top.length) {
    lines.push(`单户敞口前列（前 ${top.length} 户）：`);
    top.forEach((customer, index) => lines.push(
      `  ${index + 1}. ${customer.name_masked}（${customer.segment || "—"}，${customer.business_line}，`
      + `贷款 ${customer.loan_balance_cny_yi} 亿元，他行贷款 ${customer.other_bank_loans_cny_yi} 亿元）`
    ));
  }
  lines.push(`统计口径：${stats.match_rule || "按政策业务线匹配"}；数据来源：${stats.source || "合成客户数据集"}。`);
  return lines;
}

function dateLabel(value: string | null | undefined) {
  return value ? value.slice(0, 10) : "未标注";
}

function actionText(item: string | { action: string; owner?: string; deadline?: string }) {
  if (typeof item === "string") return item;
  const tail = [item.owner ? `负责人：${item.owner}` : "", item.deadline ? `截止：${item.deadline}` : ""]
    .filter(Boolean)
    .join("，");
  return tail ? `${item.action}（${tail}）` : item.action;
}

/** Agent 不可用时的本地模板：政策与分析结论来自页面，客户概况来自实时统计接口。 */
function buildLocalEmail(policy: TrackingPolicy, stats: LocalCustomerStats | null): { subject: string; body: string } {
  const assessment = policy.assessments[0];
  const direction = assessment ? DIRECTION_LABELS[assessment.direction] ?? assessment.direction : "未评定";
  const jurisdiction = JURISDICTION_LABELS[policy.jurisdiction] || policy.jurisdiction || "未标注市场";
  const lines: string[] = [];

  lines.push("各位领导、同事：", "");
  lines.push(`现将「${policy.title}」的政策跟踪情况汇报如下，供业务与合规决策参考。`, "");
  lines.push("一、政策基本信息");
  lines.push(`政策编号：${policy.id}`);
  lines.push(`文　　号：${policy.doc_number || "未标注"}`);
  lines.push(`发文机构：${policy.issuing_body || "未标注"}`);
  lines.push(`辖　　区：${jurisdiction}`);
  lines.push(`政策类型：${policy.policy_type || "未标注"}`);
  lines.push(`发布/生效：${dateLabel(policy.published_at)} / ${dateLabel(policy.effective_at)}`);
  lines.push(`优先级：${policy.priority}（影响评分 ${policy.score_total ?? 0} 分）`);
  lines.push(`影响方向：${direction}`);
  if (policy.themes.length) lines.push(`主题标签：${policy.themes.join("、")}`);
  lines.push("");

  lines.push("二、影响判断");
  if (assessment) {
    const chain = assessment.transmission_chain ?? [];
    lines.push("传导路径：");
    if (chain.length) {
      chain.forEach((item, index) => lines.push(`  ${index + 1}. ${item}`));
    } else {
      lines.push("  暂未生成传导路径");
    }
    const businessLines = assessment.affected?.business_lines ?? [];
    lines.push(`受影响业务线：${businessLines.length ? businessLines.join("、") : "未标注"}`);
    const exposure = assessment.affected?.exposure_range;
    lines.push(
      exposure
        ? `客户暴露规模：${exposure.low}–${exposure.high} ${exposure.currency} ${exposure.unit}（${exposure.basis}）`
        : "客户暴露规模：暂未评定"
    );
    lines.push(`分析模型：${analysisModelLabel(assessment.model)}`);
  } else {
    lines.push("当前政策尚无影响分析记录。");
  }
  lines.push("");

  lines.push("三、受影响客户概况");
  lines.push(...localCustomerLines(stats));
  lines.push("");

  lines.push("四、使用者反馈");
  lines.push("政策使用者影响报告的跟进情况可在 Horizon 政策跟进中心查看。");
  lines.push("");

  lines.push("五、建议动作");
  const actions = assessment?.recommended_actions ?? [];
  if (actions.length) {
    actions.forEach((item, index) => lines.push(`  ${index + 1}. ${actionText(item)}`));
  } else {
    lines.push("  暂无建议动作");
  }
  lines.push("");

  lines.push("六、原文出处");
  lines.push(policy.url || "暂无原文链接");
  lines.push("");
  lines.push("政策研究团队");

  return { subject: `【政策跟踪报告】${policy.title}`, body: lines.join("\n") };
}

export default function PolicyTrackingEmail({ policy }: { policy: TrackingPolicy }) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState("");
  const [email, setEmail] = useState<GeneratedEmail | null>(null);
  const [generating, setGenerating] = useState(false);
  const [notice, setNotice] = useState("");

  const generate = useCallback(async () => {
    setGenerating(true);
    setNotice("");
    try {
      // 由系统接入的跟进 Agent 现场生成邮件（含受影响客户概况与使用者反馈）
      const response = await fetch(`${API_BASE}/policies/${policy.id}/tracking-email`, {
        method: "POST",
        headers: demoApiHeaders(),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body?.error?.message || "生成失败");
      setEmail({
        subject: String(body.subject || ""),
        body: String(body.body || ""),
        model: String(body.model || ""),
        generated_by: String(body.generated_by || "ai_agent"),
        generated_at: String(body.generated_at || ""),
      });
    } catch {
      // Agent 不可用时：仍去取实时客户统计，保证邮件里有受影响客户概况
      let stats: LocalCustomerStats | null = null;
      try {
        const statsResp = await fetch(`${API_BASE}/policies/${policy.id}/affected-customers`, { headers: demoApiHeaders() });
        if (statsResp.ok) stats = await statsResp.json();
      } catch {
        // 统计也取不到时，邮件里会说明概况暂不可用
      }
      const local = buildLocalEmail(policy, stats);
      setEmail({
        ...local,
        model: "本地模板",
        generated_by: "local",
        generated_at: new Date().toISOString(),
      });
      setNotice(
        stats
          ? "跟进 Agent 暂不可用，已按实时客户统计与政策结论用本地模板生成，可直接复制发送。"
          : "跟进 Agent 暂不可用，已按政策内容用本地模板生成；受影响客户概况需稍后重试。"
      );
    } finally {
      setGenerating(false);
    }
  }, [policy]);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  useEffect(() => {
    if (open && !email && !generating) void generate();
  }, [open, email, generating, generate]);

  async function copy(text: string, label: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(label);
      setTimeout(() => setCopied(""), 2500);
    } catch {
      setCopied("复制失败，请手动选中文本复制");
      setTimeout(() => setCopied(""), 3000);
    }
  }

  const subject = email?.subject ?? "";
  const body = email?.body ?? "";
  const mailto = `mailto:?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
  const agentLabel = email?.generated_by === "ai_agent"
    ? `AI Agent 生成（模型 ${email.model}）`
    : `跟进 Agent 离线处理（${email?.model || "本地模板"}）`;

  return (
    <section className="panel full">
      <div className="panelhead">
        <h2>政策跟踪报告</h2>
        <small>由跟进 Agent 现场生成可直接发送的跟踪报告邮件</small>
      </div>
      <div className="sectionbody">
        <p className="textblock">
          政策自抓取、分析到发布均由 AI 自动完成。点击下方按钮，跟进 Agent 会结合政策要点、AI 影响判断、
          受影响客户概况与使用者反馈，现场生成一封政策跟踪报告邮件。
        </p>
        <div className="rowflex" style={{ marginTop: 12 }}>
          <button
            className="btn primary"
            type="button"
            onClick={() => {
              setEmail(null);
              setOpen(true);
            }}
          >
            生成跟踪报告邮件
          </button>
        </div>
      </div>

      {open && (
        <div className="confirm-backdrop" role="presentation" onClick={() => setOpen(false)}>
          <div
            className="confirm-modal email-modal"
            role="dialog"
            aria-modal="true"
            aria-label="政策跟踪报告邮件"
            onClick={(event) => event.stopPropagation()}
          >
            <h2>政策跟踪报告邮件</h2>
            <div className="confirm-body">
              {generating ? (
                <p className="textblock" style={{ color: "var(--muted)" }}>跟进 Agent 正在生成邮件，请稍候…</p>
              ) : (
                <>
                  {notice && <p className="textblock" style={{ color: "var(--text-3)", margin: 0 }}>{notice}</p>}
                  <div className="email-field">
                    <small>收件人</small>
                    <span>待填写（可复制正文后自行发送）</span>
                  </div>
                  <div className="email-field">
                    <small>主题</small>
                    <span>{subject}</span>
                  </div>
                  <div className="email-field">
                    <small>正文</small>
                    <pre className="email-preview">{body}</pre>
                  </div>
                  {email && <p className="agent-brief-meta" style={{ margin: 0 }}>{agentLabel}</p>}
                </>
              )}
            </div>
            <div className="confirm-actions">
              {copied && <span className="email-copied">{copied}</span>}
              <button className="btn" type="button" disabled={generating || !body} onClick={() => copy(body, "正文已复制")}>复制正文</button>
              <button
                className="btn"
                type="button"
                disabled={generating || !body}
                onClick={() => copy(`${subject}\n\n${body}`, "主题与正文已复制")}
              >
                复制主题与正文
              </button>
              <button
                className="btn primary"
                type="button"
                disabled={generating || !body}
                onClick={() => {
                  if (body) window.location.href = mailto;
                }}
              >
                用邮件客户端发送
              </button>
              <button className="btn" type="button" disabled={generating} onClick={generate}>重新生成</button>
              <button className="btn" type="button" onClick={() => setOpen(false)}>关闭</button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
