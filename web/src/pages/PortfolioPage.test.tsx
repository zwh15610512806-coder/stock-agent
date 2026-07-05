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

  it("removes CSV import and keeps screenshot OCR as the only top import action", () => {
    const { container } = renderPortfolioPage();

    expect(screen.queryByText("CSV")).toBeNull();
    expect(screen.getByText("截图AI识别")).toBeTruthy();
    expect(container.querySelector('input[accept=".csv,text/csv"]')).toBeNull();
  });

  it("shows screenshot-first metrics after importing watchlist OCR rows", async () => {
    vi.mocked(api.uploadOcr).mockResolvedValue({
      status: "completed",
      positions: [
        {
          symbol: "600460.SH",
          name: "士兰微",
          market: "CN",
          quantity: 0,
          cost_price: 44.8,
          current_price: 44.8,
          currency: "CNY",
          source: "ocr-watchlist",
          raw_fields: { 识别类型: "自选/行情列表", 涨幅: "+7.10%" },
        },
        {
          symbol: "300185.SZ",
          name: "通裕重工",
          market: "CN",
          quantity: 0,
          cost_price: 3.01,
          current_price: 3.01,
          currency: "CNY",
          source: "ocr-watchlist",
          raw_fields: { 识别类型: "自选/行情列表", 涨幅: "-2.43%" },
        },
      ],
      message: "截图缺少持仓数量和成本价。",
    });

    const { container } = renderPortfolioPage();
    uploadScreenshot(container);

    expect(await screen.findByText("识别股票")).toBeTruthy();
    expect(screen.getByText("2")).toBeTruthy();
    expect(screen.getByText("最新价合计")).toBeTruthy();
    expect(screen.getByText("47.81")).toBeTruthy();
    expect(screen.getByText("上涨/下跌")).toBeTruthy();
    expect(screen.getByText("1 / 1")).toBeTruthy();
    expect(screen.getByText("数据完整度")).toBeTruthy();
    expect(screen.getByText("行情列表")).toBeTruthy();
    expect(screen.getByText(/缺少数量\/成本/)).toBeTruthy();
    expect(container.querySelector(".portfolio-main-workspace")).toBeTruthy();
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

  it("places holdings, manual entry, and risk panels inside the primary workspace", async () => {
    usePortfolioStore.setState({ positions: [parsedPosition] });

    const { container } = renderPortfolioPage();
    const workspace = container.querySelector(".portfolio-main-workspace");

    expect(workspace).toBeTruthy();
    expect(workspace?.textContent).toContain("持仓明细");
    expect(workspace?.textContent).toContain("新增持仓");
    expect(workspace?.textContent).toContain("风险提示");
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

  it("opens stock insight inline for an OCR watchlist holding row", async () => {
    const ocrPosition: PortfolioPosition = {
      symbol: "600460.SH",
      name: "士兰微",
      market: "CN",
      quantity: 0,
      cost_price: 44.8,
      current_price: 44.8,
      currency: "CNY",
      source: "ocr-watchlist",
      raw_fields: { 涨幅: "+7.10%" },
    };
    vi.mocked(api.stockInsight).mockResolvedValue({
      status: "partial",
      symbol: "600460.SH",
      market: "CN",
      as_of: "2026-06-28T00:00:00Z",
      quote: null,
      candles: [],
      summary: "本地行情分析：截图识别到士兰微最新价 44.80。",
      trend: ["截图涨幅 +7.10%"],
      financials: [],
      events: [],
      risks: ["缺少数量和成本，无法计算仓位盈亏"],
      citations: [],
      data_warnings: ["missing OPENAI_API_KEY/NEWS_SEARCH_API_KEY", "position quantity/cost missing"],
      model: "local-market",
      disclaimer: "仅供研究参考",
    });
    usePortfolioStore.setState({ positions: [ocrPosition] });

    const { container } = renderPortfolioPage();
    fireEvent.click(await screen.findByLabelText("AI分析 士兰微"));

    const inlinePanel = await screen.findByTestId("portfolio-inline-insight");
    const activeRow = container.querySelector('tr[data-insight-active="true"]');

    expect(inlinePanel.textContent).toContain("本地行情分析");
    expect(inlinePanel.textContent).toContain("missing OPENAI_API_KEY/NEWS_SEARCH_API_KEY");
    expect(activeRow?.textContent).toContain("600460.SH");
    expect(container.querySelector(".portfolio-insight-panel")).toBeNull();
    expect(api.stockInsight).toHaveBeenCalledWith({ position: ocrPosition, horizon_days: 30 });
  });
});
