import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../lib/api";
import { usePortfolioStore } from "../lib/store";
import type { PortfolioAnalysis, PortfolioPosition } from "../lib/types";
import { PortfolioPage } from "./PortfolioPage";

vi.mock("../lib/api", () => ({
  api: {
    analyzePortfolio: vi.fn(),
    uploadOcr: vi.fn(),
    stockInsight: vi.fn(),
  },
  apiFailureMessage: (_error: unknown, label: string) => `${label}暂不可用`,
}));

const emptyAnalysis: PortfolioAnalysis = {
  total_value: 0,
  total_cost: 0,
  pnl: 0,
  pnl_pct: 0,
  positions: [],
  weights: [],
  risks: [],
  suggestions: [],
  quote_status: [],
  data_warnings: [],
  disclaimer: "仅供研究参考",
};

const parsedPosition: PortfolioPosition = {
  symbol: "600519.SH",
  name: "贵州茅台",
  market: "CN",
  quantity: 10,
  cost_price: 1000,
  current_price: 1200,
  currency: "CNY",
};

const richParsedPosition: PortfolioPosition = {
  ...parsedPosition,
  quantity: 12,
  available_quantity: 8,
  cost_price: 1000,
  current_price: 1200,
  market_value: 14400,
  pnl: 2400,
  pnl_pct: 0.2,
  source: "ocr",
};

function renderPortfolioPage() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <PortfolioPage />
    </QueryClientProvider>,
  );
}

function uploadScreenshot(container: HTMLElement) {
  const input = container.querySelector('input[accept="image/*"]');
  if (!(input instanceof HTMLInputElement)) {
    throw new Error("OCR file input not found");
  }
  const file = new File(["image"], "positions.png", { type: "image/png" });
  fireEvent.change(input, { target: { files: [file] } });
}

describe("PortfolioPage OCR upload", () => {
  beforeEach(() => {
    vi.mocked(api.analyzePortfolio).mockResolvedValue(emptyAnalysis);
    vi.mocked(api.uploadOcr).mockReset();
    vi.mocked(api.stockInsight).mockReset();
    usePortfolioStore.setState({ positions: [] });
  });

  it("shows a visible error when OCR upload request fails", async () => {
    vi.mocked(api.uploadOcr).mockRejectedValue(new Error("HTTP 500"));

    const { container } = renderPortfolioPage();
    uploadScreenshot(container);

    expect(await screen.findByText("OCR 识别暂不可用")).toBeTruthy();
  });

  it("syncs OCR positions by symbol and keeps local positions outside the screenshot", async () => {
    const localOnly: PortfolioPosition = {
      symbol: "000001.SZ",
      name: "平安银行",
      market: "CN",
      quantity: 100,
      cost_price: 10,
      current_price: 11,
      currency: "CNY",
    };
    const newPosition: PortfolioPosition = {
      symbol: "300750.SZ",
      name: "宁德时代",
      market: "CN",
      quantity: 5,
      cost_price: 200,
      current_price: 210,
      currency: "CNY",
    };
    usePortfolioStore.setState({ positions: [{ ...parsedPosition, quantity: 1 }, localOnly] });
    vi.mocked(api.uploadOcr).mockResolvedValue({
      status: "completed",
      positions: [richParsedPosition, newPosition],
      message: "",
    });

    const { container } = renderPortfolioPage();
    uploadScreenshot(container);

    expect(await screen.findByText("已同步 2 条持仓，更新 1 条，新增 1 条，保留 1 条本地持仓。")).toBeTruthy();
    await waitFor(() => {
      expect(usePortfolioStore.getState().positions).toEqual([richParsedPosition, newPosition, localOnly]);
    });
    expect(screen.getByText("可用")).toBeTruthy();
    expect(screen.getByText("市值")).toBeTruthy();
    expect(screen.getByText("浮盈")).toBeTruthy();
    expect(screen.getByText("盈亏率")).toBeTruthy();
    expect(screen.getByText("14,400.00")).toBeTruthy();
    expect(screen.getByText("20.00%")).toBeTruthy();
  });

  it("shows raw OCR text when OCR returns no usable positions", async () => {
    vi.mocked(api.uploadOcr).mockResolvedValue({
      status: "completed",
      positions: [],
      message: "AI 已返回识别结果，但未提取到可用持仓行。",
      raw_lines: ["| 代码 | 名称 | 持仓 |", "| 600519 | 贵州茅台 | -- |"],
    });

    const { container } = renderPortfolioPage();
    uploadScreenshot(container);

    expect(await screen.findByText("AI 已返回识别结果，但未提取到可用持仓行。")).toBeTruthy();
    expect(screen.getByText("AI 原始识别结果")).toBeTruthy();
    expect(screen.getByText(/600519/)).toBeTruthy();
    expect(usePortfolioStore.getState().positions).toEqual([]);
  });

  it("shows quote source warnings returned by portfolio analysis", async () => {
    vi.mocked(api.analyzePortfolio).mockResolvedValue({
      ...emptyAnalysis,
      total_value: 12000,
      positions: [{ ...parsedPosition, market_value: 12000, cost_value: 10000, pnl: 2000, pnl_pct: 0.2 }],
      weights: [{ symbol: "600519.SH", name: "贵州茅台", market: "CN", value: 12000, weight: 1 }],
      quote_status: [
        {
          symbol: "600519.SH",
          status: "unavailable",
          source: "sample fallback",
          detail: "sample fallback rejected; kept local current_price",
          as_of: null,
        },
      ],
      data_warnings: ["600519.SH 行情不可用，已保留本地现价。"],
    });
    usePortfolioStore.setState({ positions: [parsedPosition] });

    renderPortfolioPage();

    expect(await screen.findByText("600519.SH 行情不可用，已保留本地现价。")).toBeTruthy();
    expect(screen.getByText(/sample fallback rejected/)).toBeTruthy();
  });

  it("shows a visible backend error when portfolio analysis fails", async () => {
    vi.mocked(api.analyzePortfolio).mockRejectedValue(new Error("offline"));
    usePortfolioStore.setState({ positions: [parsedPosition] });

    renderPortfolioPage();

    expect(await screen.findByText("持仓分析暂不可用")).toBeTruthy();
  });

  it("loads AI stock insight for a holding row", async () => {
    vi.mocked(api.stockInsight).mockResolvedValue({
      status: "completed",
      symbol: "600519.SH",
      market: "CN",
      as_of: "2026-06-28T00:00:00Z",
      quote: null,
      candles: [],
      summary: "近30日震荡上行，财报保持稳健。",
      trend: ["30日收盘价上行"],
      financials: ["最新财报收入同比增长"],
      events: ["披露股东大会公告"],
      risks: ["白酒需求波动"],
      citations: [{ title: "贵州茅台公告", url: "https://example.com/report", source: "交易所公告" }],
      data_warnings: [],
      model: "gpt-4.1-mini",
      disclaimer: "仅供研究参考，不构成任何证券买卖建议。",
    });
    usePortfolioStore.setState({ positions: [parsedPosition] });

    renderPortfolioPage();
    fireEvent.click(await screen.findByLabelText("AI分析 贵州茅台"));

    expect(await screen.findByText("近30日震荡上行，财报保持稳健。")).toBeTruthy();
    expect(screen.getByText("30日收盘价上行")).toBeTruthy();
    expect(screen.getByText("最新财报收入同比增长")).toBeTruthy();
    expect(screen.getByText("贵州茅台公告").getAttribute("href")).toBe("https://example.com/report");
    expect(api.stockInsight).toHaveBeenCalledWith({ position: parsedPosition, horizon_days: 30 });
  });
});
