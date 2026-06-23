import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { api } from "../lib/api";
import type { MarketDashboardResponse } from "../lib/types";
import { MarketPage } from "./MarketPage";

vi.mock("../lib/api", () => ({
  api: {
    marketDashboard: vi.fn(),
  },
}));

vi.mock("../components/CandleChart", () => ({
  CandleChart: ({ candles }: { candles: unknown[] }) => <div data-testid="candle-chart">candles:{candles.length}</div>,
}));

vi.mock("../components/Heatmap", () => ({
  Heatmap: ({ data }: { data: unknown[] }) => <div data-testid="heatmap">heat:{data.length}</div>,
}));

const dashboard: MarketDashboardResponse = {
  as_of: "2026-06-23T15:00:00Z",
  cache_status: "stale",
  source_status: [
    { name: "a_share_activity", status: "live", source: "legulegu-market-activity", detail: "", as_of: "2026-06-23T15:00:00Z" },
    { name: "region_heatmap", status: "stale", source: "eastmoney-sector-fund-flow", detail: "source down", as_of: "2026-06-23T14:40:00Z" },
  ],
  primary_quote: {
    symbol: "000001.SH",
    name: "上证指数",
    market: "CN",
    price: 3011.05,
    change: -18.6,
    change_pct: -0.61,
    volume: 100,
    turnover: 416310000000,
    currency: "CNY",
    source: "tencent-free-delayed",
    as_of: "2026-06-23T15:00:00Z",
    delay_label: "免费公开源",
  },
  primary_candles: [
    {
      symbol: "000001.SH",
      date: "2026-06-23",
      open: 3000,
      high: 3020,
      low: 2980,
      close: 3011.05,
      volume: 100000,
      source: "Yahoo Finance/free delayed fallback",
      delay_label: "免费公开源",
    },
  ],
  markets: [
    {
      market: "CN",
      label: "A股",
      indices: [
        {
          symbol: "000001.SH",
          name: "上证指数",
          market: "CN",
          price: 3011.05,
          change: -18.6,
          change_pct: -0.61,
          volume: 100,
          turnover: 416310000000,
          currency: "CNY",
          source: "tencent-free-delayed",
          as_of: "2026-06-23T15:00:00Z",
          delay_label: "免费公开源",
        },
      ],
      turnover: 4163.1,
      sentiment: 57.7,
      breadth: { advances: 2600, declines: 2300, unchanged: 120, limit_up: 88, limit_down: 12 },
      heatmap: [],
      source: "tencent-free-delayed",
      delay_label: "免费公开源",
      as_of: "2026-06-23T15:00:00Z",
    },
  ],
  a_share_activity: {
    advances: 2600,
    declines: 2300,
    unchanged: 120,
    limit_up: 88,
    limit_down: 12,
    suspended: 14,
    sentiment: 57.7,
    source: "legulegu-market-activity",
    as_of: "2026-06-23T15:00:00Z",
  },
  fund_flow_summary: {
    top_inflows: [{ symbol: "600519", name: "贵州茅台", change_pct: 1.2, net_amount: 346000000, turnover: 4020000000, source: "ths-fund-flow" }],
    top_outflows: [{ symbol: "300750", name: "宁德时代", change_pct: -0.5, net_amount: -20464500, turnover: 3200000000, source: "ths-fund-flow" }],
    net_amount: 325535500,
    source: "ths-fund-flow",
    as_of: "2026-06-23T15:00:00Z",
  },
  industry_heatmap: [{ name: "银行", change_pct: 1.12, turnover: 21850000000, net_amount: 2250000000, direction: "up", source: "ths-fund-flow" }],
  concept_heatmap: [{ name: "人工智能", change_pct: 2.35, turnover: 39000000000, net_amount: 3000000000, direction: "up", source: "ths-fund-flow" }],
  region_heatmap: [{ name: "上海", change_pct: 0.92, turnover: 33330000000, net_amount: 1220000000, direction: "up", source: "eastmoney-sector-fund-flow" }],
  disclaimer: "免费公开源可能延迟、缺失或被缓存。",
};

function renderMarketPage() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MarketPage />
    </QueryClientProvider>,
  );
}

describe("MarketPage dashboard", () => {
  it("renders the broker-style dashboard from real dashboard data", async () => {
    vi.mocked(api.marketDashboard).mockResolvedValue(dashboard);

    renderMarketPage();

    expect(await screen.findByText("大盘趋势")).toBeTruthy();
    expect(screen.getByText("市场情绪")).toBeTruthy();
    expect(await screen.findByText("贵州茅台")).toBeTruthy();
    expect(screen.getAllByText("57.7")).toHaveLength(2);
    expect(screen.getByText("上证指数")).toBeTruthy();
    expect(screen.getByText(/银行/)).toBeTruthy();
    expect(screen.getByText(/人工智能/)).toBeTruthy();
    expect(screen.getByText(/上海/)).toBeTruthy();
    expect(screen.getAllByText(/缓存/).length).toBeGreaterThan(0);
    expect(screen.getByTestId("candle-chart").textContent).toContain("candles:1");
  });

  it("shows unavailable modules without fake data", async () => {
    vi.mocked(api.marketDashboard).mockResolvedValue({
      ...dashboard,
      cache_status: "partial",
      a_share_activity: null,
      fund_flow_summary: null,
      industry_heatmap: [],
      concept_heatmap: [],
      region_heatmap: [],
      source_status: [
        { name: "industry_heatmap", status: "unavailable", source: "ths-fund-flow", detail: "source down", as_of: null },
      ],
    });

    renderMarketPage();

    expect(await screen.findByText("数据源暂不可用")).toBeTruthy();
    expect(screen.queryByText("样例")).toBeNull();
  });
});
