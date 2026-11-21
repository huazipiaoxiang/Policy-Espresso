"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import SortableTh from "@/components/SortableTh";
import { API_BASE, demoApiHeaders } from "@/lib/auth";

interface ResponseLink {
  summary: string; // 简述
  url: string; // 原文链接
}

interface BusinessLine {
  code: string;
  name: string;
}

interface AgentTrace {
  mode: "agent" | "rules" | string;
  model: string;
  rounds: number;
  tools: string[];
  blocked: { tool: string; reason: string }[];
  permissions: { granted: string[]; denied: string[]; note: string };
  summary?: string;
}

interface PreprocessItem {
  id: string;
  policy_id: string;
  title: string;
  issuing_body: string;
  jurisdiction: string;
  policy_type: string;
  themes: string[];
  status: string;
  priority: string;
  published_at: string | null;
  fetched_at: string | null;
  preprocessed_at: string | null;
  keywords: string[];
  affected_business: BusinessLine[];
  customer_segments: string[];
  loss_pct: number;
  profit_pct: number;
  reputation_pct: number;
  opportunity_pct: number;
  impact_total: number;
  direction: string;
  hsbc_response: ResponseLink[];
  peer_bank_response: ResponseLink[];
  market_applications: ResponseLink[];
  extras: Record<string, unknown>;
  agent?: AgentTrace | null;
  source: string;
  confidence: number;
}

interface Overview {
  total: number;
  week_new: number;
  avg_impact_total: number;
  with_external_research: number;
}

const DIRECTION_LABELS: Record<string, string> = {
  positive: "利好",
  negative: "利空",
  mixed: "利弊并存",
  neutral: "中性",
};

function dateLabel(value: string | null): string {
  return value ? value.slice(0, 10) : "—";
}

function estimateMark(item: PreprocessItem, dimension: string) {
  const estimated = (item.extras?.estimated_dimensions as string[] | undefined) || [];
  if (!estimated.includes(dimension)) return null;
  return (
    <sup title="该维度四维评分缺失，按相关度/紧迫度/确定性规则估算" style={{ marginLeft: 2, color: "#b08900" }}>
      ≈
    </sup>
  );
}

function LinkList({
  title,
  items,
  emptyText = "网上暂无公开响应",
}: {
  title: string;
  items: ResponseLink[];
  emptyText?: string;
}) {
  return (
    <div style={{ marginTop: 8 }}>
      <strong style={{ fontSize: 12 }}>{title}</strong>
      {items.length === 0 ? (
        <p style={{ fontSize: 12, color: "#949aa3", margin: "4px 0" }}>{emptyText}</p>
      ) : (
        <ul style={{ margin: "4px 0 0 16px", fontSize: 12 }}>
          {items.map((item) => (
            <li key={item.url} style={{ marginBottom: 4 }}>
              <span>{item.summary || "（无简述）"}</span>{" "}
              <a href={item.url} target="_blank" rel="noreferrer" className="link">原文 →</a>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function PreprocessPage() {
  const { ready, role } = useAuth();
  const [items, setItems] = useState<PreprocessItem[]>([]);
  const [sortField, setSortField] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const [overview, setOverview] = useState<Overview | null>(null);

  function onSort(field: string) {
    if (sortField === field) {
      setSortDir((dir) => (dir === "asc" ? "desc" : "asc"));
    } else {
      setSortField(field);
      setSortDir("asc");
    }
  }

  const sortedItems = useMemo(() => {
    if (!sortField) return items;
    return [...items].sort((a, b) => {
      const av = (a as unknown as Record<string, unknown>)[sortField] ?? "";
      const bv = (b as unknown as Record<string, unknown>)[sortField] ?? "";
      if (av < bv) return sortDir === "asc" ? -1 : 1;
      if (av > bv) return sortDir === "asc" ? 1 : -1;
      return 0;
    });
  }, [items, sortField, sortDir]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const pageSize = 20;
  const [search, setSearch] = useState("");
  const [direction, setDirection] = useState("");
  const [onlyWeek, setOnlyWeek] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [rebuilding, setRebuilding] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
      if (search.trim()) params.set("q", search.trim());
      if (direction) params.set("direction", direction);
      if (onlyWeek) params.set("only_week", "true");
      const [listResp, overviewResp] = await Promise.all([
        fetch(`${API_BASE}/preprocess?${params.toString()}`, { headers: demoApiHeaders(), cache: "no-store" }),
        fetch(`${API_BASE}/preprocess/overview`, { headers: demoApiHeaders(), cache: "no-store" }),
      ]);
      const listBody = await listResp.json();
      if (!listResp.ok) throw new Error(listBody?.error?.message || "预处理表格加载失败");
      setItems(listBody.items || []);
      setTotal(listBody.total || 0);
      if (overviewResp.ok) setOverview(await overviewResp.json());
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "预处理表格加载失败");
    } finally {
      setLoading(false);
    }
  }, [page, search, direction, onlyWeek]);

  useEffect(() => {
    if (!ready) return;
    void load();
  }, [load, ready]);

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  async function rebuild(policyId: string, research: boolean) {
    setRebuilding(policyId);
    try {
      const resp = await fetch(
        `${API_BASE}/preprocess/${policyId}/rebuild?research=${research}`,
        { method: "POST", headers: demoApiHeaders() },
      );
      const body = await resp.json();
      if (!resp.ok) throw new Error(body?.error?.message || "重建失败");
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "重建失败");
    } finally {
      setRebuilding("");
    }
  }

  return (
    <div className="content">
      <div className="pagehead">
        <div>
          <div className="eyebrow">POLICY PREPROCESS</div>
          <h1>政策预处理表格</h1>
          <p className="sub">政策抓取入库并完成分析后自动生成 · 供「为你推荐」与政策详情消费 · 只读</p>
        </div>
      </div>

      <div className="notice" style={{ marginBottom: 16 }}>
        <div style={{ marginBottom: 4 }}><strong>字段口径</strong></div>
        <div>
          政策原文抓取后，政策生成收尾与预处理由系统接入的 <strong>政策流水线 AI Agent</strong> 复核：读取原文、业务图谱与客户暴露，
          判定业务线/客户类型并提交预处理结论；百分比统一由 <code>compute_consumer_impact</code> 计算（0–100 程度分），Agent 不得自造数字。
        </div>
        <div>Agent 权限除「数据外泄」外全开放：可读库内数据、写政策与预处理、触发任务、发布政策、检索公开信息；内部数据检索词会被出网策略拦截并留痕。</div>
        <div>汇丰反应、类似政策、市场实际应用由预处理阶段自动联网检索公开报道（仅携带政策公开词）。</div>
      </div>

      {overview && (
        <div className="rowflex" style={{ gap: 12, marginBottom: 16, flexWrap: "wrap" }}>
          {[
            { label: "预处理政策总数", value: overview.total },
            { label: "本周新入库", value: overview.week_new },
            { label: "平均综合分", value: overview.avg_impact_total },
            { label: "已检索外部反应", value: overview.with_external_research },
          ].map((card) => (
            <div className="panel" key={card.label} style={{ padding: "12px 16px", minWidth: 150 }}>
              <div style={{ fontSize: 12, color: "#8b929c" }}>{card.label}</div>
              <div style={{ fontSize: 22, fontWeight: 600 }}>{card.value}</div>
            </div>
          ))}
        </div>
      )}

      {error && <div className="notice" style={{ marginBottom: 16 }}>{error}</div>}

      <div className="panel">
        <div className="panelhead">
          <h2>预处理记录</h2>
          <small>{total} 条</small>
        </div>
        <div className="sectionbody">
          <div className="rowflex" style={{ gap: 8, marginBottom: 12, flexWrap: "wrap" }}>
            <input
              className="search"
              value={search}
              onChange={(event) => { setSearch(event.target.value); setPage(1); }}
              placeholder="搜索政策标题 / 发文机构…"
              style={{ width: 240 }}
            />
            <select
              className="filter"
              value={direction}
              onChange={(event) => { setDirection(event.target.value); setPage(1); }}
            >
              <option value="">全部影响方向</option>
              <option value="positive">利好</option>
              <option value="negative">利空</option>
              <option value="mixed">利弊并存</option>
              <option value="neutral">中性</option>
            </select>
            <button
              type="button"
              className={onlyWeek ? "btn primary" : "btn"}
              onClick={() => { setOnlyWeek(!onlyWeek); setPage(1); }}
            >
              仅本周新入库
            </button>
          </div>

          {loading ? (
            <div style={{ padding: 40, textAlign: "center" }}>加载预处理表格…</div>
          ) : (
            <div className="tablewrap">
              <table>
                <thead>
                  <tr>
                    <SortableTh label="政策" field="title" sortField={sortField} sortDir={sortDir} onSort={onSort} />
                    <th>关键词</th>
                    <th>影响业务</th>
                    <th>可能影响的客户类型</th>
                    <th>损失% / 盈利%</th>
                    <th>信誉% / 机会%</th>
                    <SortableTh label="综合分" field="impact_total" sortField={sortField} sortDir={sortDir} onSort={onSort} />
                    <th>外部反应</th>
                    <SortableTh label="预处理时间" field="preprocessed_at" sortField={sortField} sortDir={sortDir} onSort={onSort} />
                  </tr>
                </thead>
                <tbody>
                  {sortedItems.length === 0 ? (
                    <tr><td colSpan={9} style={{ textAlign: "center", padding: 40, color: "#949aa3" }}>暂无预处理记录</td></tr>
                  ) : sortedItems.map((item) => {
                    const researchCount =
                      item.hsbc_response.length + item.peer_bank_response.length + item.market_applications.length;
                    return (
                      <tr key={item.id}>
                        <td style={{ minWidth: 220, maxWidth: 300 }}>
                          <div className="policytitle">
                            <Link href={`/policies/${item.policy_id}`}>{item.title}</Link>
                            <small>
                              {item.issuing_body || "发文机构未注明"} · {item.jurisdiction || "—"} ·{" "}
                              {item.agent?.mode === "agent" ? "AI Agent 处理" : "规则处理"}
                            </small>
                          </div>
                          <details style={{ marginTop: 6, fontSize: 12 }}>
                            <summary style={{ cursor: "pointer" }}>详情 / 重建</summary>
                            <div style={{ marginTop: 6, minWidth: 280 }}>
                              <p>影响方向：{DIRECTION_LABELS[item.direction] || item.direction}</p>
                              <p>生成来源：{item.source} · 置信度 {Number(item.confidence || 0).toFixed(2)}</p>
                              <p>
                                处理方式：
                                {item.agent?.mode === "agent"
                                  ? `AI Agent（模型 ${item.agent.model}，${item.agent.rounds} 轮工具调用）`
                                  : "规则通道（未接入生成式模型或 Agent 未产出结论）"}
                              </p>
                              {item.agent?.summary ? <p>Agent 结论：{item.agent.summary}</p> : null}
                              {item.agent?.tools?.length ? <p>Agent 使用工具：{item.agent.tools.join("、")}</p> : null}
                              {item.agent?.blocked?.length ? (
                                <p style={{ color: "#b08900" }}>
                                  已拦截出网请求：
                                  {item.agent.blocked.map((blocked) => `${blocked.tool}（${blocked.reason}）`).join("；")}
                                </p>
                              ) : null}
                              <p>
                                Agent 权限：除数据外泄外全开放
                                {item.agent?.permissions?.granted?.length
                                  ? `（${item.agent.permissions.granted.join(" / ")}）`
                                  : "（read / write / trigger / publish / public_egress）"}
                              </p>
                              <p>主题：{item.themes.join("、") || "—"}</p>
                              <p>业务线口径：{String(item.extras?.business_basis || "—")}</p>
                              <p>百分比口径：{String(item.extras?.percentage_basis || "—")}</p>
                              <p>
                                敞口口径：{String(item.extras?.affected_customer_count ?? 0)} 户 /
                                {String(item.extras?.affected_amount_cny_yi ?? 0)} 亿元
                              </p>
                              <p>
                                联网证据：{String(item.extras?.web_evidence_count ?? 0)} 条
                                {(item.extras?.web_keywords as string[] | undefined)?.length
                                  ? `（其中业务词已参与判定：${(item.extras?.web_keywords as string[]).join("、")}）`
                                  : ""}
                              </p>
                              <LinkList title="汇丰对此政策/话题的反应" items={item.hsbc_response} />
                              <LinkList title="类似政策" items={item.peer_bank_response} />
                              <LinkList
                                title="市面上实际应用"
                                items={item.market_applications}
                                emptyText="网上暂无公开落地案例"
                              />
                              {role === "admin" && (
                                <div className="rowflex" style={{ gap: 8, marginTop: 8 }}>
                                  <button
                                    type="button"
                                    className="btn"
                                    disabled={rebuilding === item.policy_id}
                                    onClick={() => void rebuild(item.policy_id, false)}
                                  >
                                    {rebuilding === item.policy_id ? "Agent 重建中…" : "重建（Agent 复核）"}
                                  </button>
                                  <button
                                    type="button"
                                    className="btn"
                                    disabled={rebuilding === item.policy_id}
                                    onClick={() => void rebuild(item.policy_id, true)}
                                  >
                                    重建 + 联网检索（Agent 复核）
                                  </button>
                                </div>
                              )}
                            </div>
                          </details>
                        </td>
                        <td>
                          <div className="rowflex" style={{ flexWrap: "wrap", gap: 4 }}>
                            {item.keywords.slice(0, 4).map((keyword) => <span className="badge" key={keyword}>{keyword}</span>)}
                            {item.keywords.length > 4 && <small style={{ color: "#949aa3" }}>+{item.keywords.length - 4}</small>}
                          </div>
                        </td>
                        <td>
                          <div className="rowflex" style={{ flexWrap: "wrap", gap: 4 }}>
                            {item.affected_business.length
                              ? item.affected_business.map((line) => <span className="badge" key={line.code}>{line.code}</span>)
                              : "—"}
                          </div>
                        </td>
                        <td style={{ maxWidth: 220, fontSize: 12 }}>
                          {item.customer_segments.length ? item.customer_segments.slice(0, 3).join("、") : "—"}
                          {item.customer_segments.length > 3 && <span style={{ color: "#949aa3" }}> 等 {item.customer_segments.length} 类</span>}
                        </td>
                        <td style={{ whiteSpace: "nowrap" }}>
                          {item.loss_pct === 0 && item.profit_pct === 0 && item.reputation_pct === 0 && item.opportunity_pct === 0 ? (
                            <span title="相关度为 0：规则/模型判定本行不在适用范围内，不做影响估算" style={{ color: "#949aa3" }}>无直接影响</span>
                          ) : (
                            <>
                              <span className="badge red">{item.loss_pct}%{estimateMark(item, "business_loss")}</span>{" "}
                              {item.profit_pct > 0
                                ? <span className="badge green">{item.profit_pct}%{estimateMark(item, "profit")}</span>
                                : <span title="利空政策不折算正向盈利" style={{ color: "#949aa3" }}>—</span>}
                            </>
                          )}
                        </td>
                        <td style={{ whiteSpace: "nowrap" }}>
                          {item.loss_pct === 0 && item.profit_pct === 0 && item.reputation_pct === 0 && item.opportunity_pct === 0 ? (
                            <span style={{ color: "#949aa3" }}>—</span>
                          ) : (
                            <>
                              <span className="badge amber">{item.reputation_pct}%{estimateMark(item, "reputation_risk")}</span>{" "}
                              <span className="badge">{item.opportunity_pct}%{estimateMark(item, "business_opportunity")}</span>
                            </>
                          )}
                        </td>
                        <td><b>{item.impact_total}</b></td>
                        <td style={{ minWidth: 220, maxWidth: 300, fontSize: 12 }}>
                          {researchCount === 0 ? (
                            <span style={{ color: "#949aa3" }}>网上暂无公开响应</span>
                          ) : (
                            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                              {([
                                ["汇丰", item.hsbc_response],
                                ["类似政策", item.peer_bank_response],
                                ["市场", item.market_applications],
                              ] as [string, ResponseLink[]][]).map(([label, links]) => (
                                links[0] ? (
                                  <div key={label} style={{ display: "flex", gap: 4, alignItems: "flex-start" }}>
                                    <span className="badge" style={{ flexShrink: 0 }}>{label}</span>
                                    <a
                                      href={links[0].url}
                                      target="_blank"
                                      rel="noreferrer"
                                      className="link"
                                      title={links[0].summary}
                                    >
                                      {links[0].summary.slice(0, 26)}
                                    </a>
                                  </div>
                                ) : null
                              ))}
                            </div>
                          )}
                        </td>
                        <td style={{ whiteSpace: "nowrap", fontSize: 12 }}>{dateLabel(item.preprocessed_at)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {total > pageSize && (
            <div className="rowflex" style={{ justifyContent: "center", marginTop: 12, gap: 12, alignItems: "center" }}>
              <button className="btn" disabled={page <= 1} onClick={() => setPage((value) => Math.max(1, value - 1))}>← 上一页</button>
              <span style={{ fontSize: 12, color: "#8b929c" }}>第 {page} / {totalPages} 页 · 共 {total} 条</span>
              <button className="btn" disabled={page >= totalPages} onClick={() => setPage((value) => Math.min(totalPages, value + 1))}>下一页 →</button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
