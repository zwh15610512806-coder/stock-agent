import type {
  AiReportResponse,
  AiReportAnalysisSkill,
  CandleSnapshot,
  EtfCandlesResponse,
  EtfSearchResponse,
  MacroDashboardResponse,
  MarketDashboardResponse,
  MarketCode,
  MarketOverviewResponse,
  PortfolioAnalysis,
  PortfolioPosition,
  QuoteSnapshot,
  StockScreenerResponse,
  SymbolSearchResult,
} from "./types";

const API_BASE = import.meta.env.VITE_API_BASE || "";

async function requestJson<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "content-type": "application/json",
      ...(options?.headers || {}),
    },
  });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  marketOverview: (markets: MarketCode[] = ["CN", "HK", "US"]) =>
    requestJson<MarketOverviewResponse>(`/api/market/overview?markets=${markets.join(",")}`),
  marketDashboard: (markets: MarketCode[] = ["CN", "HK", "US"], period = "daily") =>
    requestJson<MarketDashboardResponse>(`/api/market/dashboard?markets=${markets.join(",")}&period=${period}`),
  macroDashboard: () => requestJson<MacroDashboardResponse>("/api/macro/dashboard"),
  quotes: (symbols: string[]) =>
    requestJson<QuoteSnapshot[]>(`/api/market/quotes?symbols=${encodeURIComponent(symbols.join(","))}`),
  candles: (symbol: string, period = "daily", limit = 120) =>
    requestJson<CandleSnapshot[]>(
      `/api/market/candles?symbol=${encodeURIComponent(symbol)}&period=${period}&limit=${limit}`,
    ),
  searchSymbols: (q: string, markets: MarketCode[] = ["CN", "HK", "US"]) =>
    requestJson<SymbolSearchResult[]>(
      `/api/symbols/search?q=${encodeURIComponent(q)}&markets=${markets.join(",")}`,
    ),
  stockScreener: (params: {
    query?: string;
    min_change_pct?: number;
    max_change_pct?: number;
    min_turnover?: number;
    min_market_cap?: number;
    max_pe?: number;
    max_pb?: number;
    limit?: number;
  }) => {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") {
        query.set(key, String(value));
      }
    });
    return requestJson<StockScreenerResponse>(`/api/stocks/screener?${query.toString()}`);
  },
  searchEtfs: (q = "", limit = 20) =>
    requestJson<EtfSearchResponse>(`/api/etfs/search?q=${encodeURIComponent(q)}&limit=${limit}`),
  etfCandles: (symbol: string, period = "daily", limit = 120) =>
    requestJson<EtfCandlesResponse>(
      `/api/etfs/candles?symbol=${encodeURIComponent(symbol)}&period=${period}&limit=${limit}`,
    ),
  analyzePortfolio: (positions: PortfolioPosition[]) =>
    requestJson<PortfolioAnalysis>("/api/portfolio/analyze", {
      method: "POST",
      body: JSON.stringify({ positions }),
    }),
  uploadOcr: async (file: File) => {
    const form = new FormData();
    form.append("file", file);
    const response = await fetch(`${API_BASE}/api/ocr/positions`, {
      method: "POST",
      body: form,
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    return response.json() as Promise<{ status: string; positions: PortfolioPosition[]; message: string }>;
  },
  createAiReport: (payload: {
    symbol: string;
    market: MarketCode;
    analysis_skill?: AiReportAnalysisSkill;
    quote: QuoteSnapshot | null;
    candles: CandleSnapshot[];
    portfolio_positions: PortfolioPosition[];
    horizon: string;
    risk_profile: string;
  }) =>
    requestJson<AiReportResponse>("/api/ai/reports", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};
