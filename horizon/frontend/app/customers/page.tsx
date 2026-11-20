"use client";

import { useEffect, useMemo, useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import { API_BASE, demoApiHeaders } from "@/lib/auth";

interface Customer {
  customer_id: string;
  name_masked: string;
  business_line: string;
  segment: string;
  region: string;
  loan_balance_cny_yi: number;
  other_bank_loans_cny_yi: number;
  other_bank_count: number;
  overseas_business: string[];
  products: string[];
  relationship_manager: string;
  subsidy_eligible: boolean;
}

export default function CustomersPage() {
  const { ready } = useAuth();
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [businessLineFilter, setBusinessLineFilter] = useState("");
  const [keyword, setKeyword] = useState("");

  useEffect(() => {
    if (!ready) return;
    let active = true;
    fetch(`${API_BASE}/customers`, { headers: demoApiHeaders(), cache: "no-store" })
      .then(async (resp) => {
        const body = await resp.json();
        if (!resp.ok) throw new Error(body?.error?.message || "客户信息加载失败");
        return body;
      })
      .then((body) => {
        if (active) setCustomers(body.items || []);
      })
      .catch((reason) => {
        if (active) setError(reason instanceof Error ? reason.message : "客户信息加载失败");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [ready]);

  const businessLines = useMemo(() => {
    const set = new Set<string>();
    customers.forEach((c) => {
      if (c.business_line) set.add(c.business_line);
    });
    return Array.from(set).sort();
  }, [customers]);

  const filtered = useMemo(() => {
    const byLine = businessLineFilter
      ? customers.filter((c) => c.business_line === businessLineFilter)
      : customers;
    const text = keyword.trim().toLowerCase();
    if (!text) return byLine;
    return byLine.filter((c) =>
      [c.customer_id, c.name_masked, c.segment, c.region, c.relationship_manager]
        .some((value) => (value || "").toLowerCase().includes(text))
    );
  }, [customers, businessLineFilter, keyword]);

  const summary = useMemo(() => ({
    count: filtered.length,
    totalLoan: Math.round(filtered.reduce((sum, c) => sum + (c.loan_balance_cny_yi || 0), 0) * 10) / 10,
    subsidy: filtered.filter((c) => c.subsidy_eligible).length,
    managers: new Set(filtered.map((c) => c.relationship_manager).filter(Boolean)).size,
  }), [filtered]);

  return (
    <div className="content">
      <div className="pagehead">
        <div>
          <div className="eyebrow">CUSTOMERS</div>
          <h1>客户信息</h1>
          <p className="sub">政策使用者对应的客户信息 · 模拟数据</p>
        </div>
      </div>

      <div className="notice" style={{ marginBottom: 16 }}>
        <div style={{ marginBottom: 4 }}><strong>管理员只读视图</strong></div>
        <div>来源：<code>seed/synthetic_customers.json</code>，合成演示客户数据（非真实客户），完整展示全部 12 个字段；本页不提供编辑、删除、导入入口。</div>
        <div>口径：金额单位为「亿元」；「贴息资格」标记用于贴息类政策的客户聚合；「客户经理」与登录用户名匹配后，决定「为你推荐」走规则 A（客户敞口测算）还是规则 B（预处理百分比）。</div>
      </div>

      <div className="rowflex" style={{ gap: 12, marginBottom: 16, flexWrap: "wrap" }}>
        {[
          { label: "当前筛选客户数", value: `${summary.count} / ${customers.length}` },
          { label: "贷款余额合计(亿)", value: summary.totalLoan },
          { label: "贴息资格客户", value: summary.subsidy },
          { label: "覆盖客户经理", value: summary.managers },
        ].map((card) => (
          <div className="panel" key={card.label} style={{ padding: "12px 16px", minWidth: 150 }}>
            <div style={{ fontSize: 12, color: "#8b929c" }}>{card.label}</div>
            <div style={{ fontSize: 22, fontWeight: 600 }}>{card.value}</div>
          </div>
        ))}
      </div>

      {error && <div className="notice" style={{ marginBottom: 16 }}>{error}</div>}

      {loading ? (
        <div className="panel" style={{ padding: 40, textAlign: "center" }}>加载客户信息…</div>
      ) : (
        <div className="panel">
          <div className="panelhead">
            <h2>客户列表</h2>
            <small>{filtered.length} / {customers.length} 户</small>
          </div>

          <div className="sectionbody">
            <div className="rowflex" style={{ gap: 8, marginBottom: 12, flexWrap: "wrap" }}>
              <button
                type="button"
                className={businessLineFilter === "" ? "btn primary" : "btn"}
                onClick={() => setBusinessLineFilter("")}
              >
                全部业务线
              </button>
              {businessLines.map((line) => (
                <button
                  key={line}
                  type="button"
                  className={businessLineFilter === line ? "btn primary" : "btn"}
                  onClick={() => setBusinessLineFilter(line)}
                >
                  {line}
                </button>
              ))}
              <input
                className="search"
                value={keyword}
                onChange={(event) => setKeyword(event.target.value)}
                placeholder="搜索客户名称 / 编号 / 客户经理 / 客群…"
                style={{ width: 260 }}
              />
            </div>

            <div className="tablewrap">
              <table>
                <thead>
                  <tr>
                    <th>客户编号</th>
                    <th>客户</th>
                    <th>客户经理</th>
                    <th>业务线</th>
                    <th>客群</th>
                    <th>地区</th>
                    <th>贷款规模(亿)</th>
                    <th>他行贷款(亿)</th>
                    <th>他行家数</th>
                    <th>贴息资格</th>
                    <th>海外业务</th>
                    <th>产品</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.length === 0 ? (
                    <tr><td colSpan={12} style={{ textAlign: "center", padding: 40, color: "#949aa3" }}>暂无客户数据</td></tr>
                  ) : filtered.map((c) => (
                    <tr key={c.customer_id}>
                      <td style={{ whiteSpace: "nowrap", fontSize: 12, color: "#8b929c" }}>{c.customer_id}</td>
                      <td style={{ minWidth: 160 }}>{c.name_masked}</td>
                      <td><span className="badge">{c.relationship_manager || "—"}</span></td>
                      <td><span className="badge">{c.business_line}</span></td>
                      <td>{c.segment || "—"}</td>
                      <td>{c.region || "—"}</td>
                      <td>{c.loan_balance_cny_yi}</td>
                      <td>{c.other_bank_loans_cny_yi}</td>
                      <td>{c.other_bank_count ?? "—"}</td>
                      <td>
                        {c.subsidy_eligible
                          ? <span className="badge green">是</span>
                          : <span className="badge">否</span>}
                      </td>
                      <td>{c.overseas_business?.length ? c.overseas_business.join("、") : "—"}</td>
                      <td style={{ fontSize: 12 }}>{c.products?.length ? c.products.join("、") : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
