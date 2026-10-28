"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import ReviewConsole, { ReviewTaskItem } from "@/components/ReviewConsole";
import { API_BASE, demoApiHeaders } from "@/lib/auth";

export default function ReviewPage() {
  const { role } = useAuth();
  const [tasks, setTasks] = useState<ReviewTaskItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch(`${API_BASE}/review-tasks`, { headers: demoApiHeaders() })
      .then(async (response) => {
        const body = await response.json();
        if (!response.ok) throw new Error(body?.error?.message || "审核任务加载失败");
        setTasks(body.items || []);
      })
      .catch((reason: Error) => setError(reason.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <main className="content">
      <div className="pagehead">
        <div>
          <div className="eyebrow">REVIEW WORKSPACE</div>
          <h1>审核工作台</h1>
          <p className="sub">{role === "analyst" ? "处理一级审核，核对政策原文、证据与影响分析" : role === "approver" ? "处理二级审核，复核重点政策结论" : "查看审核依据，已审核政策请到发布中心处理"}</p>
        </div>
      </div>
      {error && <div className="notice" style={{ marginBottom: 16 }}>{error}</div>}
      {loading ? <div className="panel" style={{ padding: 40, textAlign: "center" }}>加载审核任务…</div> : <ReviewConsole initialTasks={tasks} />}
      <p className="footnote">审核决定由服务端校验角色和任务级别；P0/P1 需两级审核，P2/P3 单级审核。</p>
    </main>
  );
}
