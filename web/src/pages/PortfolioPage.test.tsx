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
  },
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
    usePortfolioStore.setState({ positions: [] });
  });

  it("shows a visible error when OCR upload request fails", async () => {
    vi.mocked(api.uploadOcr).mockRejectedValue(new Error("HTTP 500"));

    const { container } = renderPortfolioPage();
    uploadScreenshot(container);

    expect(await screen.findByText("OCR 上传失败，请检查后端服务或网络连接。")).toBeTruthy();
  });

  it("shows a visible import result when OCR returns positions", async () => {
    vi.mocked(api.uploadOcr).mockResolvedValue({
      status: "completed",
      positions: [parsedPosition],
      message: "",
    });

    const { container } = renderPortfolioPage();
    uploadScreenshot(container);

    expect(await screen.findByText("OCR 已导入 1 条持仓草稿。")).toBeTruthy();
    await waitFor(() => {
      expect(usePortfolioStore.getState().positions).toEqual([parsedPosition]);
    });
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
});
