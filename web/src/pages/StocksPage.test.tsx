import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { api } from "../lib/api";
import type { CandleSnapshot, QuoteSnapshot, SymbolSearchResult } from "../lib/types";
import { StocksPage } from "./StocksPage";

vi.mock("../lib/api", () => ({
  api: {
    quotes: vi.fn(),
    candles: vi.fn(),
    searchSymbols: vi.fn(),
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

    renderStocksPage();

    expect(screen.getByRole("heading", { name: "选股中心" })).toBeTruthy();
    expect(screen.getByText("在工作台查看股票详情并管理自选，使用选股器进行多指标筛选，或用 ETF 视角观察资产包。")).toBeTruthy();
    expect(screen.getByRole("tab", { name: /工作台/ })).toBeTruthy();
    expect(screen.getByRole("tab", { name: /选股器/ })).toBeTruthy();
    expect(screen.getByRole("tab", { name: /ETF/ })).toBeTruthy();

    expect(await screen.findByText("贵州茅台")).toBeTruthy();
    expect(screen.getByTestId("candle-chart").textContent).toBe("candles:1");

    fireEvent.click(screen.getByRole("tab", { name: /选股器/ }));
    fireEvent.click(screen.getByRole("button", { name: "搜索" }));

    expect(await screen.findByText("腾讯控股")).toBeTruthy();
    expect(api.searchSymbols).toHaveBeenCalledWith("茅台", ["CN", "HK", "US"]);

    fireEvent.click(screen.getByRole("tab", { name: /ETF/ }));

    expect(screen.getByText("ETF 真实数据暂不可用")).toBeTruthy();
    expect(screen.getByText("接入 ETF 净值、持仓和折溢价数据源后，这里会展示资产包视角；当前不展示样例或模拟数据。")).toBeTruthy();
  });
});
