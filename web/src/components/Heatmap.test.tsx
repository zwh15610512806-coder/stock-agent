import { describe, expect, it } from "vitest";
import { buildHeatmapOption } from "./Heatmap";
import type { DashboardHeatItem } from "../lib/types";

const sampleData: DashboardHeatItem[] = [
  { name: "半导体", change_pct: -0.88, turnover: 520926000000, net_amount: -100, direction: "down", source: "test" },
  { name: "通信设备", change_pct: -5.07, turnover: 229588000000, net_amount: -90, direction: "down", source: "test" },
  { name: "银行", change_pct: -1.11, turnover: 1200000000, net_amount: -50, direction: "down", source: "test" },
];

describe("Heatmap option", () => {
  it("highlights hovered tiles without blurring the rest of the treemap", () => {
    const option = buildHeatmapOption(sampleData, "turnover", 60);
    const series = Array.isArray(option.series) ? option.series[0] : undefined;

    expect(series?.emphasis?.focus).toBe("none");
    expect(series?.blur).toEqual({ itemStyle: { opacity: 1 }, label: { opacity: 1 } });
    expect(series?.emphasis?.itemStyle?.borderColor).toBe("#0f172a");
    expect(series?.emphasis?.scale).toBe(true);
  });

  it("keeps readable labels on dense small tiles", () => {
    const option = buildHeatmapOption(sampleData, "turnover", 120);
    const series = Array.isArray(option.series) ? option.series[0] : undefined;
    const thirdTile = series?.data?.[2];
    const label = thirdTile?.label?.formatter();

    expect(label).toContain("银行");
    expect(label).toContain("-1.11%");
    expect(label).not.toContain("...");
    expect(thirdTile?.label?.rich?.name?.fontSize).toBeGreaterThanOrEqual(11);
  });
});
