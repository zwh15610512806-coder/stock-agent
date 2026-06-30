import { useEffect, useRef } from "react";
import * as echarts from "echarts";
import type { ECBasicOption } from "echarts/types/dist/shared";
import type { MarketHeatItem } from "../lib/types";

export type HeatmapAreaMetric = "turnover" | "net_amount" | "change_pct";

type HeatmapItem = MarketHeatItem & {
  net_amount?: number;
  source?: string;
};

interface HeatmapProps {
  data: HeatmapItem[];
  areaMetric?: HeatmapAreaMetric;
  displayLimit?: number;
}

export function Heatmap({ data, areaMetric = "turnover", displayLimit = data.length }: HeatmapProps) {
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!ref.current) {
      return;
    }
    const chart = echarts.init(ref.current);
    chart.setOption(buildHeatmapOption(data, areaMetric, displayLimit));
    const handleResize = () => chart.resize();
    window.addEventListener("resize", handleResize);
    return () => {
      window.removeEventListener("resize", handleResize);
      chart.dispose();
    };
  }, [areaMetric, data, displayLimit]);

  return <div className="heatmap-host" ref={ref} role="img" aria-label="板块热力图" />;
}

export function buildHeatmapOption(data: HeatmapItem[], areaMetric: HeatmapAreaMetric, displayLimit: number): ECBasicOption {
    const sortedItems = [...data].sort((a, b) => getAreaValue(b, areaMetric) - getAreaValue(a, areaMetric));
    const isCompact = displayLimit >= 120;
    const isDense = displayLimit >= 60;
    const heatmapData = sortedItems
      .map((item, index) => {
        const areaValue = getAreaValue(item, areaMetric);
        const color = colorForChange(item.change_pct);
        const labelColor = Math.abs(item.change_pct) >= 1.75 ? "#ffffff" : "#07111f";
        const mutedColor = Math.abs(item.change_pct) >= 1.75 ? "rgba(255,255,255,0.88)" : "#486079";
        const largeTile = index < (isCompact ? 12 : 10);
        return {
          ...item,
          value: compressAreaValue(areaValue, displayLimit),
          label: {
            color: labelColor,
            formatter: () => formatTileLabel(item, index, displayLimit),
            minMargin: isCompact ? 0 : 1,
            overflow: "break",
            padding: isCompact ? [4, 4, 3, 4] : isDense ? [6, 6, 5, 6] : [9, 8, 8, 8],
            position: "insideTopLeft",
            rich: {
              pct: {
                color: labelColor,
                fontFamily: "JetBrains Mono, Cascadia Mono, Consolas, monospace",
                fontSize: isCompact ? (largeTile ? 13 : 12) : largeTile ? 17 : 13,
                fontWeight: 900,
                lineHeight: isCompact ? 16 : largeTile ? 24 : 18,
              },
              name: {
                color: labelColor,
                fontSize: isCompact ? 11 : largeTile ? 13 : 11,
                fontWeight: 900,
                lineHeight: isCompact ? 14 : 16,
              },
              amount: {
                color: mutedColor,
                fontFamily: "JetBrains Mono, Cascadia Mono, Consolas, monospace",
                fontSize: isDense ? 10 : 11,
                lineHeight: isDense ? 14 : 17,
              },
            },
          },
          itemStyle: {
            color,
            borderColor: "#ffffff",
            borderRadius: isCompact ? 4 : 7,
            borderWidth: isCompact ? 2 : 3,
          },
          children: [],
        };
      });

    return {
      animationDuration: 520,
      animationEasing: "cubicOut" as const,
      tooltip: {
        backgroundColor: "rgba(15, 23, 42, 0.94)",
        borderWidth: 0,
        extraCssText: "border-radius:8px;box-shadow:0 12px 30px rgba(15,23,42,0.18);",
        textStyle: {
          color: "#ffffff",
          fontSize: 12,
        },
        formatter: (params: { data: HeatmapItem & { displayAmount?: string } }) => {
          const item = params.data;
          return [
            `<strong>${escapeHtml(item.name)}</strong>`,
            `涨跌幅 ${formatSignedPct(item.change_pct)}`,
            `成交额 ${escapeHtml(formatHeatAmount(item.turnover))}`,
            item.net_amount === undefined ? "" : `净流入 ${escapeHtml(formatHeatAmount(item.net_amount))}`,
          ]
            .filter(Boolean)
            .join("<br/>");
        },
      },
      series: [
        {
          type: "treemap",
          width: "100%",
          height: "100%",
          top: 0,
          right: 0,
          bottom: 0,
          left: 0,
          roam: false,
          nodeClick: false,
          breadcrumb: { show: false },
          upperLabel: { show: false },
          leafDepth: 1,
          squareRatio: isCompact ? 1.35 : isDense ? 1.28 : 1.18,
          sort: "desc",
          visibleMin: 1,
          label: {
            show: true,
          },
          itemStyle: {
            borderColor: "#ffffff",
            borderRadius: isCompact ? 4 : 7,
            borderWidth: isCompact ? 2 : 3,
            gapWidth: isCompact ? 2 : 3,
          },
          emphasis: {
            focus: "none",
            scale: true,
            scaleSize: isCompact ? 1.2 : 1.6,
            label: {
              opacity: 1,
            },
            itemStyle: {
              borderColor: "#0f172a",
              borderWidth: isCompact ? 3 : 4,
              shadowBlur: 0,
              shadowColor: "transparent",
            },
          },
          blur: {
            itemStyle: {
              opacity: 1,
            },
            label: {
              opacity: 1,
            },
          },
          levels: [
            {
              itemStyle: {
                borderColor: "#ffffff",
                borderRadius: isCompact ? 4 : 7,
                borderWidth: isCompact ? 2 : 3,
                gapWidth: isCompact ? 2 : 3,
              },
            },
          ],
          data: heatmapData,
        },
      ],
    };
}

function getAreaValue(item: HeatmapItem, metric: HeatmapAreaMetric): number {
  if (metric === "net_amount") {
    return Math.max(1, Math.abs(item.net_amount ?? 0));
  }
  if (metric === "change_pct") {
    return Math.max(1, Math.abs(item.change_pct) * 100000000);
  }
  return Math.max(1, item.turnover || Math.abs(item.change_pct) * 100000000);
}

function compressAreaValue(value: number, displayLimit: number): number {
  const exponent = displayLimit >= 60 ? 0.64 : 0.72;
  return Math.max(1, Math.pow(Math.max(value, 1), exponent));
}

function formatTileLabel(item: HeatmapItem, index: number, displayLimit: number): string {
  if (displayLimit >= 120) {
    return `{pct|${formatSignedPct(item.change_pct)}}\n{name|${shortHeatName(item.name, 5)}}`;
  }
  if (displayLimit >= 60 && index >= 30) {
    return `{pct|${formatSignedPct(item.change_pct)}}\n{name|${shortHeatName(item.name, 6)}}`;
  }
  return `{pct|${formatSignedPct(item.change_pct)}}\n{name|${item.name}}\n{amount|${formatHeatAmount(item.turnover)}}`;
}

function shortHeatName(value: string, limit: number): string {
  const normalized = value.trim();
  if (normalized.length <= limit) {
    return normalized;
  }
  return normalized.slice(0, limit);
}

function formatSignedPct(value: number): string {
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}%`;
}

function formatHeatAmount(value: number): string {
  const abs = Math.abs(value || 0);
  if (abs > 0 && abs < 10000000) {
    if (abs >= 10000) {
      return `${trimFixed(value / 10000)}万亿`;
    }
    return `${trimFixed(value)}亿`;
  }
  if (abs >= 1000000000000) {
    return `${trimFixed(value / 1000000000000)}万亿`;
  }
  if (abs >= 100000000) {
    return `${trimFixed(value / 100000000)}亿`;
  }
  if (abs >= 10000) {
    return `${trimFixed(value / 10000)}万`;
  }
  return trimFixed(value);
}

function trimFixed(value: number): string {
  return value.toLocaleString("zh-CN", {
    maximumFractionDigits: 2,
    minimumFractionDigits: 0,
  });
}

function colorForChange(value: number): string {
  if (value === 0) {
    return "#e8edf3";
  }
  const intensity = Math.min(1, Math.abs(value) / 5);
  return value > 0
    ? mixColor("#ffe3e6", "#ff5f6d", intensity)
    : mixColor("#d9fae8", "#43d27f", intensity);
}

function mixColor(from: string, to: string, amount: number): string {
  const start = hexToRgb(from);
  const end = hexToRgb(to);
  const rgb = start.map((channel, index) => Math.round(channel + (end[index] - channel) * amount));
  return `rgb(${rgb[0]}, ${rgb[1]}, ${rgb[2]})`;
}

function hexToRgb(hex: string): [number, number, number] {
  const normalized = hex.replace("#", "");
  return [
    parseInt(normalized.slice(0, 2), 16),
    parseInt(normalized.slice(2, 4), 16),
    parseInt(normalized.slice(4, 6), 16),
  ];
}

function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (char) => {
    const entities: Record<string, string> = {
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    };
    return entities[char];
  });
}
