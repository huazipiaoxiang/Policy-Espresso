"use client";

import { useEffect, useState } from "react";
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
  overseas_business: string[];
  products: string[];
  relationship_manager: string;
}

export default function CustomersPage() {
  const { ready } = useAuth();
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

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
        以下客户信息为<strong>模拟数据</strong>（合成客户），非真实客户信息。
      </div>

      {error && <div className="notice" style={{ marginBottom: 16 }}>{error}</div>}

      {loading ? (
        <div className="panel" style={{ padding: 40, textAlign: "center" }}>加载客户信息…</div>
      ) : (
        <div className="panel">
          <div className="panelhead"><h2>客户列表</h2><small>{customers.length} 户</small></div>
          <div className="sectionbody tablewrap">
            <table>
              <thead>
                <tr>
                  <th>客户</th>
                  <th>业务线</th>
                  <th>客群</th>
                  <th>地区</th>
                  <th>贷款规模(亿)</th>
                  <th>他行贷款(亿)</th>
                  <th>海外业务</th>
                </tr>
              </thead>
              <tbody>
                {customers.length === 0 ? (
                  <tr><td colSpan={7} style={{ textAlign: "center", padding: 40, color: "#949aa3" }}>暂无客户数据</td></tr>
                ) : customers.map((c) => (
                  <tr key={c.customer_id}>
                    <td style={{ minWidth: 180 }}>{c.name_masked}</td>
                    <td><span className="badge">{c.business_line}</span></td>
                    <td>{c.segment || "—"}</td>
                    <td>{c.region || "—"}</td>
                    <td>{c.loan_balance_cny_yi}</td>
                    <td>{c.other_bank_loans_cny_yi}</td>
                    <td>{c.overseas_business?.length ? c.overseas_business.join("、") : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
