"use client";

import { useEffect, useRef } from "react";
import * as echarts from "echarts";
import { SCORE_DIMENSION_LABELS } from "@/lib/labels";

const DIM_LABELS = SCORE_DIMENSION_LABELS;

// ScoreRadar（08 §4）：8 轴雷达，null 轴虚线留空
export default function ScoreRadar({
  scores,
}: {
  scores: Record<string, { score: number | null; reason: string }>;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ref.current) return;
    const chart = echarts.init(ref.current, "dark", { renderer: "svg" });
    const dims = Object.keys(DIM_LABELS);
    const values = dims.map((d) => scores[d]?.score ?? null);
    const max = 5;
    chart.setOption({
      backgroundColor: "transparent",
      radar: {
        indicator: dims.map((d) => ({ name: DIM_LABELS[d], max })),
        radius: "62%",
        axisName: { color: "var(--text-2)", fontSize: 10 },
        splitLine: { lineStyle: { color: "var(--border)" } },
        splitArea: { areaStyle: { color: ["transparent"] } },
        axisLine: { lineStyle: { color: "var(--border)" } },
      },
      series: [
        {
          type: "radar",
          data: [
            {
              value: values.map((v) => (v == null ? 0 : v)),
              name: "影响评分",
              areaStyle: { color: "rgba(34,211,238,.15)" },
              lineStyle: { color: "var(--accent)", type: values.some((v) => v == null) ? "dashed" : "solid" },
              itemStyle: { color: "var(--accent)" },
              // null 轴置 0 但在 tooltip 标注缺值
            },
          ],
        },
      ],
      tooltip: {
        formatter: () => {
          const rows = dims.map((d, i) => {
            const v = values[i];
            return `${DIM_LABELS[d]}: ${v == null ? "缺证据（未评分）" : v}`;
          });
          return rows.join("<br/>");
        },
        backgroundColor: "var(--surface-2)",
        borderColor: "var(--border)",
        textStyle: { color: "var(--text)", fontSize: 11 },
      },
    });
    const onResize = () => chart.resize();
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      chart.dispose();
    };
  }, [scores]);

  return <div ref={ref} className="h-[220px] w-full" />;
}
