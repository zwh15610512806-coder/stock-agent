import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { api } from "../lib/api";
import type { CandleSnapshot, EtfSearchResponse, QuoteSnapshot, StockScreenerResponse, SymbolSearchResult } from "../lib/types";
import { StocksPage } from "./StocksPage";

vi.mock("../lib/api", () => ({
  api: {
    quotes: vi.fn(),
    candles: vi.fn(),
    searchSymbols: vi.fn(),
    stockScreener: vi.fn(),
    searchEtfs: vi.fn(),
    etfCandles: vi.fn(),
  },
}));

vi.mock("../components/CandleChart", () => ({
  CandleChart: ({ candles }: { candles: CandleSnapshot[] }) => <div data-testid="candle-chart">candles:{candles.length}</div>,
}));

const quote: QuoteSnapshot = {
  symbol: "600519.SH",
  name: "贵州茅台",
  market: "CN",
  price: 1520.5,
  change: 12.4,
  change_pct: 0.82,
  volume: 123456,
  turnover: 987654321,
  currency: "CNY",
  source: "tencent-free-delayed",
  as_of: "2026-06-23T15:00:00Z",
  delay_label: "免费公开源延迟",
};

const candles: CandleSnapshot[] = [
  {
    symbol: "600519.SH",
    date: "2026-06-23",
    open: 1500,
    high: 1530,
    low: 1490,
    close: 1520.5,
    volume: 100000,
    source: "Yahoo Finance/free delayed fallback",
    delay_label: "免费公开源延迟",
  },
];

const searchResults: SymbolSearchResult[] = [
  { symbol: "600519.SH", name: "贵州茅台", market: "CN", currency: "CNY" },
  { symbol: "00700.HK", name: "腾讯控股", market: "HK", currency: "HKD" },
];

const screenerResponse: StockScreenerResponse = {
  as_of: "2026-06-24T09:30:00Z",
  source: "akshare-a-share-spot",
  status: "live",
  items: [
    {
      symbol: "600519.SH",
      name: "贵州茅台",
      price: 1520.5,
      change_pct: 0.82,
      turnover: 987654321,
      pe: 24.5,
      pb: 8.1,
      market_cap: 1910000000000,
      source: "akshare-a-share-spot",
    },
  ],
};

const etfResponse: EtfSearchResponse = {
  as_of: "2026-06-24T09:30:00Z",
  source: "akshare-etf",
  status: "live",
  items: [
    {
      symbol: "510300",
      name: "沪深300ETF",
      price: 4.12,
      change_pct: 0.42,
      volume: 12345600,
      turnover: 50800000,
      source: "akshare-etf",
    },
  ],
};

function renderStocksPage() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <StocksPage />
    </QueryClientProvider>,
  );
}

describe("StocksPage center", () => {
  it("combines workbench, selector, and ETF entry points without fake ETF data", async () => {
    vi.mocked(api.quotes).mockResolvedValue([quote]);
    vi.mocked(api.candles).mockResolvedValue(candles);
    vi.mocked(api.searchSymbols).mockResolvedValue(searchResults);
    vi.mocked(api.stockScreener).mockResolvedValue(screenerResponse);
    vi.mocked(api.searchEtfs).mockResolvedValue(etfResponse);
    vi.mocked(api.etfCandles).mockResolvedValue(candles);

    renderStocksPage();

    expect(screen.getByRole("heading", { name: "选股中心" })).toBeTruthy();
    expect(screen.getByText("在工作台查看股票详情并管理自选，使用选股器进行多指标筛选，或用 ETF 视角观察资产包。")).toBeTruthy();
    expect(screen.getByRole("tab", { name: /工作台/ })).toBeTruthy();
    expect(screen.getByRole("tab", { name: /选股器/ })).toBeTruthy();
    expect(screen.getByRole("tab", { name: /ETF/ })).toBeTruthy();

    expect(await screen.findByText("贵州茅台")).toBeTruthy();
    expect((await screen.findByTestId("candle-chart")).textContent).toBe("candles:1");

    fireEvent.click(screen.getByRole("tab", { name: /选股器/ }));

    expect(await screen.findByText("贵州茅台")).toBeTruthy();
    expect(screen.getByText("24.50")).toBeTruthy();
    expect(screen.getByText(/akshare-a-share-spot/)).toBeTruthy();
    expect(api.stockScreener).toHaveBeenCalledWith(expect.objectContaining({ query: "茅台", limit: 30 }));

    fireEvent.click(screen.getByRole("tab", { name: /ETF/ }));

    expect(await screen.findByText("沪深300ETF")).toBeTruthy();
    expect(screen.getByText(/akshare-etf/)).toBeTruthy();
    expect((await screen.findByTestId("candle-chart")).textContent).toBe("candles:1");
    expect(screen.queryByText("ETF 真实数据暂不可用")).toBeNull();
  });
});
