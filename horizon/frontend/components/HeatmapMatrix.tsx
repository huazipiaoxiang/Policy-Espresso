"use client";

import { useEffect, useRef } from "react";
import * as echarts from "echarts";
import type { BusinessMapData } from "@/lib/api";

// 业务线 × 主题 矩阵热力图（08 §3.5）
export default function HeatmapMatrix({ data }: { data: BusinessMapData }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ref.current) return;
    const chart = echarts.init(ref.current, "dark", { renderer: "svg" });
    const lines = Object.keys(data.matrix);
    const themes = data.themes;

    const values: [number, number, number][] = [];
    let max = 1;
    lines.forEach((code, y) => {
      themes.forEach((theme, x) => {
        const cell = data.matrix[code].cells[theme];
        if (cell && cell.policy_count > 0) {
          values.push([x, y, cell.policy_count]);
          max = Math.max(max, cell.policy_count);
        }
      });
    });

    chart.setOption({
      backgroundColor: "transparent",
      grid: { left: 90, right: 20, top: 10, bottom: 90 },
      tooltip: {
        formatter: (p: { value: [number, number, number] }) => {
          const [x, y, count] = p.value;
          const code = lines[y];
          const theme = themes[x];
          const cell = data.matrix[code].cells[theme];
          return `${data.matrix[code].name} × ${theme}<br/>相关政策 ${cell?.policy_count ?? 0} 条 · 平均影响分 ${cell?.avg_score ?? 0}`;
        },
        backgroundColor: "var(--surface-2)",
        borderColor: "var(--border)",
        textStyle: { color: "var(--text)", fontSize: 11 },
      },
      xAxis: { type: "category", data: themes, axisLabel: { color: "var(--text-3)", fontSize: 10, rotate: 45 },
               axisLine: { lineStyle: { color: "var(--border)" } }, splitArea: { show: false } },
      yAxis: { type: "category", data: lines.map((c) => data.matrix[c].name),
               axisLabel: { color: "var(--text-2)", fontSize: 11 },
               axisLine: { lineStyle: { color: "var(--border)" } }, splitLine: { show: false } },
      visualMap: {
        min: 0, max, calculable: true, orient: "horizontal", left: "center", bottom: 0,
        textStyle: { color: "var(--text-3)", fontSize: 10 },
        inRange: { color: ["var(--surface-2)", "var(--accent)"] },
      },
      series: [{ type: "heatmap", data: values, label: { show: true, color: "var(--text)", fontSize: 10 },
                 itemStyle: { borderColor: "var(--border)", borderWidth: 1 } }],
    });
    const onResize = () => chart.resize();
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      chart.dispose();
    };
  }, [data]);

  return <div ref={ref} className="h-[420px] w-full" />;
}
