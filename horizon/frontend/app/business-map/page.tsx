"use client";

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import Link from "next/link";
import { useAuth } from "@/components/AuthProvider";
import { API_BASE, demoApiHeaders } from "@/lib/auth";
import { JURISDICTION_LABELS, POLICY_STATUS_LABELS, impactScoreLabel } from "@/lib/labels";

interface PolicySummary {
  id: string;
  title: string;
  summary_zh: string;
  themes: string[];
  score_total: number;
  priority: string;
  status: string;
  jurisdiction: string;
  published_at: string | null;
}

interface BusinessMapCell {
  policy_count: number;
  avg_score: number;
  policies: PolicySummary[];
}

interface BusinessMapLine {
  name: string;
  sensitivity: Record<string, number>;
  policy_count: number;
  policies: PolicySummary[];
  cells: Record<string, BusinessMapCell>;
}

interface BusinessMapData {
  themes: string[];
  matrix: Record<string, BusinessMapLine>;
  top_themes: Record<string, number>;
  months: number;
}

const CELL_COLORS: Record<number, string> = {
  0: "#f5f6f8",
  1: "#e8f5ee",
  2: "#fff4e0",
  3: "#ffe8ea",
};

const CELL_TEXT_COLORS: Record<number, string> = {
  0: "#b0b5be",
  1: "#2d7a50",
  2: "#966016",
  3: "#bd0010",
};

function levelForCount(count: number): number {
  if (count <= 0) return 0;
  if (count <= 2) return 1;
  if (count <= 5) return 2;
  return 3;
}

function Highlight({ text, query }: { text: string; query: string }): ReactNode {
  const needle = query.trim().toLowerCase();
  if (!needle) return text;
  const lower = text.toLowerCase();
  const parts: ReactNode[] = [];
  let cursor = 0;
  let match = lower.indexOf(needle, cursor);
  while (match >= 0) {
    if (match > cursor) parts.push(text.slice(cursor, match));
    parts.push(<mark key={`${match}-${needle}`}>{text.slice(match, match + needle.length)}</mark>);
    cursor = match + needle.length;
    match = lower.indexOf(needle, cursor);
  }
  if (cursor < text.length) parts.push(text.slice(cursor));
  return parts.length ? parts : text;
}

export default function BusinessMapPage() {
  const { role, ready } = useAuth();
  const [search, setSearch] = useState("");
  const [market, setMarket] = useState("");
  const [businessLine, setBusinessLine] = useState("");
  const [topic, setTopic] = useState("");
  const [data, setData] = useState<BusinessMapData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selection, setSelection] = useState<{ lineCode: string; theme?: string } | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams({ months: "12" });
      if (market) params.set("jurisdiction", market);
      const response = await fetch(`${API_BASE}/business-map?${params}`, {
        headers: demoApiHeaders(),
        cache: "no-store",
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      setData(await response.json() as BusinessMapData);
    } catch {
      setError("业务图谱加载失败，请稍后重试");
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [market]);

  useEffect(() => {
    if (!ready) return;
    void loadData();
  }, [loadData, ready, role]);

  useEffect(() => {
    if (!ready) return;
    const refresh = () => void loadData();
    window.addEventListener("focus", refresh);
    window.addEventListener("pageshow", refresh);
    window.addEventListener("horizon:policy-updated", refresh);
    return () => {
      window.removeEventListener("focus", refresh);
      window.removeEventListener("pageshow", refresh);
      window.removeEventListener("horizon:policy-updated", refresh);
    };
  }, [loadData, ready]);

  const query = search.trim().toLowerCase();
  const filteredRows = useMemo(() => {
    if (!data) return [];
    return Object.entries(data.matrix)
      .filter(([code]) => !businessLine || code === businessLine)
      .map(([code, line]) => {
        const domainMatch = query.length > 0 && `${line.name} ${code}`.toLowerCase().includes(query);
        const matches = (policy: PolicySummary) => {
          if (!query || domainMatch) return true;
          return [policy.title, policy.summary_zh, ...policy.themes]
            .join(" ")
            .toLowerCase()
            .includes(query);
        };
        const cells = Object.fromEntries(
          Object.entries(line.cells)
            .filter(([theme]) => !topic || theme === topic)
            .map(([theme, cell]) => [
              theme,
              { ...cell, policies: cell.policies.filter(matches) },
            ]),
        );
        const policyIds = new Set(
          Object.values(cells).flatMap((cell) => cell.policies.map((policy) => policy.id)),
        );
        return { code, ...line, domainMatch, policies: line.policies.filter((policy) => policyIds.has(policy.id)), cells };
      })
      .filter((row) => !query || row.domainMatch || row.policies.length > 0);
  }, [data, businessLine, query, topic]);

  const visibleTopics = useMemo(
    () => (topic ? data?.themes.filter((theme) => theme === topic) ?? [] : data?.themes ?? []),
    [data, topic],
  );
  const topThemes = useMemo(() => {
    const counts = Object.keys(data?.top_themes ?? {}).map((theme) => {
      const policyIds = new Set<string>();
      filteredRows.forEach((row) => {
        (row.cells[theme]?.policies ?? []).forEach((policy) => policyIds.add(policy.id));
      });
      return [theme, policyIds.size] as const;
    }).filter(([theme]) => !topic || theme === topic);
    return Object.fromEntries(counts);
  }, [data, filteredRows, topic]);
  const selectedRow = selection ? filteredRows.find((row) => row.code === selection.lineCode) : undefined;
  const selectedPolicies = selectedRow
    ? selection?.theme
      ? selectedRow.cells[selection.theme]?.policies ?? []
      : selectedRow.policies
    : [];
  const maxThemeCount = Math.max(1, ...Object.values(topThemes));
  const hasMatches = filteredRows.some((row) => row.policies.length > 0);

  const openPolicies = (lineCode: string, theme?: string) => setSelection({ lineCode, theme });

  return (
    <main className="business-map-page">
      <div className="pagehead">
        <div>
          <div className="eyebrow">BUSINESS MAPPING</div>
          <h1>业务图谱</h1>
          <p className="sub">业务线 × 政策主题 关联矩阵</p>
        </div>
      </div>

      <div className="doc-intro">
        按业务线高敏感主题关联政策库中的真实政策。点击业务线、影响政策数或主题单元格，查看对应的政策清单；颜色深浅代表政策数量。
      </div>

      <div className="consumer-search">
        <input
          type="text"
          placeholder="搜索业务线、政策标题或主题关键词…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          aria-label="搜索业务线、政策标题或主题关键词"
        />
        {search && (
          <button className="business-map-clear" onClick={() => setSearch("")} type="button">
            清空
          </button>
        )}
        <select className="filter" value={market} onChange={(e) => setMarket(e.target.value)} aria-label="市场筛选">
          <option value="">全部市场</option>
          {Object.entries(JURISDICTION_LABELS).map(([code, label]) => (
            <option key={code} value={code}>{label}</option>
          ))}
        </select>
        <select className="filter" value={businessLine} onChange={(e) => setBusinessLine(e.target.value)} aria-label="业务线筛选">
          <option value="">全部业务线</option>
          {Object.entries(data?.matrix ?? {}).map(([code, line]) => (
            <option key={code} value={code}>{line.name}</option>
          ))}
        </select>
        <select className="filter" value={topic} onChange={(e) => setTopic(e.target.value)} aria-label="主题筛选">
          <option value="">全部主题</option>
          {(data?.themes ?? []).map((theme) => <option key={theme} value={theme}>{theme}</option>)}
        </select>
      </div>

      <section className="panel">
        <div className="panelhead">
          <h2>关联矩阵</h2>
          <div className="rowflex">
            <small>近 {data?.months ?? 12} 个月 · 去重政策数</small>
            <button className="business-map-clear" type="button" onClick={() => void loadData()} disabled={loading || !ready}>
              刷新
            </button>
          </div>
        </div>
        {loading ? (
          <div className="business-map-empty">正在加载业务图谱…</div>
        ) : error ? (
          <div className="business-map-empty" role="alert">
            <p>{error}</p>
            <button className="btn" type="button" onClick={() => void loadData()}>重新加载</button>
          </div>
        ) : !data || filteredRows.length === 0 || !hasMatches ? (
          <div className="business-map-empty">
            <p>{query ? "未找到匹配的业务线、政策标题或主题关键词" : topic || businessLine || market ? "当前筛选条件下没有关联政策" : "暂无政策数据"}</p>
            {query && <button className="btn" type="button" onClick={() => setSearch("")}>清空搜索</button>}
          </div>
        ) : (
          <div className="mapping-scroll">
            <table className="mapping-matrix">
              <thead>
                <tr>
                  <th>业务线 / 影响政策</th>
                  {visibleTopics.map((theme) => <th key={theme}><Highlight text={theme} query={search} /></th>)}
                </tr>
              </thead>
              <tbody>
                {filteredRows.map((row) => (
                  <tr key={row.code}>
                    <th>
                      <button
                        className="business-map-domain"
                        type="button"
                        onClick={() => openPolicies(row.code)}
                        title={`查看${row.name}的政策清单`}
                      >
                        <Highlight text={row.name} query={search} />
                        <span>影响政策 {row.policies.length} 条</span>
                      </button>
                    </th>
                    {visibleTopics.map((theme) => {
                      const cell = row.cells[theme];
                      const count = cell?.policies.length ?? 0;
                      const level = levelForCount(count);
                      return (
                        <td key={theme}>
                          <button
                            className={`map-cell${query && count > 0 ? " business-map-search-hit" : ""}`}
                            style={{ background: CELL_COLORS[level], color: CELL_TEXT_COLORS[level] }}
                            type="button"
                            onClick={() => openPolicies(row.code, theme)}
                            aria-label={`${row.name} ${theme}，${count} 条政策`}
                          >
                            {count || "—"}
                          </button>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {data && !loading && !error && (
        <section className="panel" style={{ marginTop: "18px" }}>
          <div className="panelhead">
            <h2>高敏感主题 Top 5</h2>
            <small>去重政策数</small>
          </div>
          <div className="sectionbody">
            {Object.entries(topThemes).map(([theme, count]) => (
              <div className="mapping-bar" key={theme}>
                <span><Highlight text={theme} query={search} /></span>
                <div className="mapping-track"><div style={{ width: `${(count / maxThemeCount) * 100}%` }} /></div>
                <strong>{count}</strong>
              </div>
            ))}
          </div>
        </section>
      )}

      <p className="footnote">
        数据来自近 12 个月政策库，按业务线高敏感主题关联；每条政策在同一业务线或主题内只计一次。点击业务线或单元格查看完整政策清单。
      </p>

      {selection && selectedRow && (
        <div className="business-map-modal-backdrop" role="presentation" onClick={() => setSelection(null)}>
          <section
            className="business-map-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="business-map-modal-title"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="business-map-modal-head">
              <div>
                <h2 id="business-map-modal-title">{selectedRow.name}{selection.theme ? ` × ${selection.theme}` : ""}</h2>
                <p>共 {selectedPolicies.length} 条匹配政策{query ? ` · 搜索“${search.trim()}”` : ""}</p>
              </div>
              <button className="business-map-modal-close" type="button" aria-label="关闭政策清单" onClick={() => setSelection(null)}>×</button>
            </div>
            {selectedPolicies.length === 0 ? (
              <div className="business-map-empty">当前筛选条件下没有匹配政策</div>
            ) : (
              <ul className="business-map-policy-list">
                {selectedPolicies.map((policy) => (
                  <li key={policy.id}>
                    <Link href={`/policies/${policy.id}`} className="business-map-policy-link">
                      <strong><Highlight text={policy.title} query={search} /></strong>
                      <small>{JURISDICTION_LABELS[policy.jurisdiction] || policy.jurisdiction || "未注明市场"} · {POLICY_STATUS_LABELS[policy.status] || policy.status} · 影响分 {impactScoreLabel(policy.score_total, 0, false)}</small>
                      <p><Highlight text={policy.summary_zh || "暂无摘要"} query={search} /></p>
                      <div className="business-map-policy-themes">
                        {policy.themes.map((theme) => <span className="tag" key={theme}><Highlight text={theme} query={search} /></span>)}
                      </div>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      )}
    </main>
  );
}
