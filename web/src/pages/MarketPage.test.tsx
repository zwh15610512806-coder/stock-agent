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

vi.mock("../components/Heatmap", () => ({
  Heatmap: ({ data }: { data: unknown[] }) => <div data-testid="heatmap">heat:{data.length}</div>,
}));

const dashboard: MarketDashboardResponse = {
  as_of: "2026-06-23T15:00:00Z",
  cache_status: "stale",
  source_status: [
    { name: "a_share_activity", status: "live", source: "legulegu-market-activity", detail: "", as_of: "2026-06-23T15:00:00Z" },
    { name: "region_heatmap", status: "stale", source: "eastmoney-sector-fund-flow", detail: "source down", as_of: "2026-06-23T14:40:00Z" },
    { name: "market_news", status: "live", source: "cls-telegraph", detail: "", as_of: "2026-06-23T14:57:00Z" },
    { name: "commodity_quotes", status: "live", source: "akshare-commodity", detail: "", as_of: "2026-06-23T14:57:00Z" },
    { name: "dragon_tiger", status: "live", source: "eastmoney-lhb", detail: "", as_of: "2026-06-23T15:00:00Z" },
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
  a_share_turnover: {
    value: 1024300000000,
    source: "sse-szse-summary",
    status: "live",
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
  market_news: [
    {
      title: "央行开展公开市场操作",
      content: "维护银行体系流动性合理充裕",
      published_at: "2026-06-23T14:57:00+08:00",
      source: "cls-telegraph",
      url: "",
    },
  ],
  commodity_quotes: [
    {
      symbol: "Au99.99",
      name: "黄金连续",
      price: 917.84,
      change: 0.37,
      change_pct: 0.04,
      unit: "CNY/g",
      source: "sge-spot",
      as_of: "2026-06-23T14:57:00+08:00",
      sparkline: [917.84, 918.21],
    },
  ],
  dragon_tiger: [
    {
      symbol: "002765",
      name: "蓝黛科技",
      trade_date: "2026-06-23",
      close: 110.43,
      change_pct: 30,
      net_amount: 220000000,
      buy_amount: 350000000,
      sell_amount: 130000000,
      reason: "日涨幅偏离值达7%",
      source: "eastmoney-lhb",
    },
  ],
  index_sparklines: {
    "000001.SH": [3001, 3008, 3011],
  },
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
  it("shows a loading state while the dashboard request is still pending", () => {
    vi.mocked(api.marketDashboard).mockReturnValue(new Promise(() => {}));

    renderMarketPage();

    expect(screen.getByText("正在加载真实市场数据")).toBeTruthy();
    expect(screen.getAllByText("正在连接免费行情源和本地 SQLite 缓存。").length).toBeGreaterThan(0);
    expect(screen.queryByText("不可用")).toBeNull();
    expect(screen.queryByText("暂无真实指数行情")).toBeNull();
  });

  it("renders the reference-style market overview from real dashboard data", async () => {
    vi.mocked(api.marketDashboard).mockResolvedValue(dashboard);

    renderMarketPage();

    expect(await screen.findByText("市场全景")).toBeTruthy();
    expect(screen.getByText("全球指数")).toBeTruthy();
    expect(screen.getByText("市场脉搏")).toBeTruthy();
    expect(await screen.findByText("1.02万亿")).toBeTruthy();
    expect(screen.getByText("7x24快讯")).toBeTruthy();
    expect(screen.getByText("板块热力图")).toBeTruthy();
    expect(screen.getByText("大宗商品")).toBeTruthy();
    expect(screen.getByText("龙虎榜")).toBeTruthy();
    expect(await screen.findByText("贵州茅台")).toBeTruthy();
    expect(screen.getByText("上证指数")).toBeTruthy();
    expect(screen.getAllByText(/银行/).length).toBeGreaterThan(0);
    expect(screen.getByText(/人工智能/)).toBeTruthy();
    expect(screen.getByText("央行开展公开市场操作")).toBeTruthy();
    expect(screen.getByText("黄金连续")).toBeTruthy();
    expect(screen.getByText("蓝黛科技")).toBeTruthy();
    expect(screen.getAllByText(/缓存/).length).toBeGreaterThan(0);
    expect(screen.queryByText("大盘趋势")).toBeNull();
    expect(screen.queryByText("市场情绪")).toBeNull();
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
      market_news: [],
      commodity_quotes: [],
      dragon_tiger: [],
      index_sparklines: {},
      source_status: [
        { name: "industry_heatmap", status: "unavailable", source: "ths-fund-flow", detail: "source down", as_of: null },
      ],
    });

    renderMarketPage();

    expect(await screen.findByText(/数据源暂不可用/)).toBeTruthy();
    expect(screen.getByText("暂无真实快讯")).toBeTruthy();
    expect(screen.getByText("暂无真实商品行情")).toBeTruthy();
    expect(screen.getByText("暂无真实龙虎榜")).toBeTruthy();
    expect(screen.queryByText("样例")).toBeNull();
  });
});
