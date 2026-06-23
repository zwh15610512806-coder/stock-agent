import { useEffect, useRef } from "react";
import * as echarts from "echarts";
import type { MarketHeatItem } from "../lib/types";

interface HeatmapProps {
  data: MarketHeatItem[];
}

export function Heatmap({ data }: HeatmapProps) {
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!ref.current) {
      return;
    }
    const chart = echarts.init(ref.current);
    chart.setOption({
      tooltip: {
        formatter: (params: { data: { name: string; value: number } }) =>
          `${params.data.name}<br/>涨跌幅 ${params.data.value.toFixed(2)}%`,
      },
      series: [
        {
          type: "treemap",
          roam: false,
          nodeClick: false,
          breadcrumb: { show: false },
          label: { color: "#ffffff", fontSize: 12 },
          itemStyle: { borderColor: "#f5f7f8", borderWidth: 2 },
          data: data.map((item) => ({
            name: item.name,
            value: Math.max(1, item.turnover || Math.abs(item.change_pct) * 100),
            itemStyle: { color: item.change_pct >= 0 ? "#d64b3f" : "#14845f" },
            children: [],
          })),
        },
      ],
    });
    const handleResize = () => chart.resize();
    window.addEventListener("resize", handleResize);
    return () => {
      window.removeEventListener("resize", handleResize);
      chart.dispose();
    };
  }, [data]);

  return <div className="heatmap-host" ref={ref} />;
}
