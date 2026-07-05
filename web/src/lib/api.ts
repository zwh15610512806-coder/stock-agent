import type {
  AiReportResponse,
  AiReportAnalysisSkill,
  CandleSnapshot,
  CompatQuotesResponse,
  CompatQuoteSeriesResponse,
  EtfCandlesResponse,
  EtfSearchResponse,
  MacroDashboardResponse,
  MacroTimeseriesResponse,
  MacroXrayResponse,
  MacroXrayTargetsResponse,
  MarketDashboardResponse,
  MarketDashboardRealtimeResponse,
  MarketDateSnapshotResponse,
  MarketCode,
  MarketIntradayResponse,
  MarketNewsResponse,
  MarketOverviewResponse,
  MarketStatusResponse,
  PortfolioAnalysis,
  PortfolioPosition,
  QuoteSnapshot,
  OcrPositionsResponse,
  SourcesStatusResponse,
  StockInsightResponse,
  StockScreenerResponse,
  SymbolSearchResult,
  TopTurnoverResponse,
} from "./types";

const API_BASE = import.meta.env.VITE_API_BASE || "";

export type ApiErrorKind = "network" | "http" | "parse";

export class ApiError extends Error {
  kind: ApiErrorKind;
  status?: number;
  body?: string;

  constructor(message: string, kind: ApiErrorKind, options: { status?: number; body?: string; cause?: unknown } = {}) {
    super(message);
    this.name = "ApiError";
    this.kind = kind;
    this.status = options.status;
    this.body = options.body;
    if (options.cause !== undefined) {
      this.cause = options.cause;
    }
  }
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}

export function getApiErrorKind(error: unknown): ApiErrorKind | "unknown" {
  return isApiError(error) ? error.kind : "unknown";
}

export function apiFailureMessage(error: unknown, label = "数据"): string {
  if (isApiError(error)) {
    if (error.kind === "network") {
      return `${label}后端未连接；请确认 FastAPI 已在 127.0.0.1:8000 运行。`;
    }
    if (error.kind === "http") {
      return `${label}请求失败：HTTP ${error.status ?? "--"}。`;
    }
    if (error.kind === "parse") {
      return `${label}返回格式异常；请检查后端日志。`;
    }
  }
  return `${label}暂不可用；请检查后端服务、网络连接和免费源状态。`;
}

async function requestJson<T>(path: string, options?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers: {
        "content-type": "application/json",
        ...(options?.headers || {}),
      },
    });
  } catch (error) {
    throw new ApiError("Backend API is unreachable", "network", { cause: error });
  }
  return parseJsonResponse<T>(response);
}

async function parseJsonResponse<T>(response: Response): Promise<T> {
  const body = await response.text();
  if (!response.ok) {
    throw new ApiError(`HTTP ${response.status}`, "http", { status: response.status, body });
  }
  try {
    return (body ? JSON.parse(body) : null) as T;
  } catch (error) {
    throw new ApiError("Backend returned invalid JSON", "parse", { body, cause: error });
  }
}

export const api = {
  health: () => requestJson<{ status: string }>("/healthz"),
  sourcesStatus: () => requestJson<SourcesStatusResponse>("/api/sources/status"),
  marketOverview: (markets: MarketCode[] = ["CN", "HK", "US", "KR", "JP"]) =>
    requestJson<MarketOverviewResponse>(`/api/market/overview?markets=${markets.join(",")}`),
  marketDashboard: (markets: MarketCode[] = ["CN", "HK", "US", "KR", "JP"], period = "daily") =>
    requestJson<MarketDashboardResponse>(`/api/market/dashboard?markets=${markets.join(",")}&period=${period}`),
  marketStatus: () => requestJson<MarketStatusResponse>("/api/market/status"),
  marketDashboardRealtime: () => requestJson<MarketDashboardRealtimeResponse>("/api/market/dashboard/realtime"),
  marketIntraday: (groups: string[] = ["indices-cn"]) =>
    requestJson<MarketIntradayResponse>(`/api/market/dashboard/intraday?groups=${encodeURIComponent(groups.join(","))}`),
  marketNews: (limit = 120, offset = 0) =>
    requestJson<MarketNewsResponse>(`/api/market/news?limit=${limit}&offset=${offset}`),
  marketTopTurnover: (market = "cn", limit = 10, date?: string) => {
    const query = new URLSearchParams();
    query.set("market", market);
    query.set("limit", String(limit));
    if (date) {
      query.set("date", date);
    }
    return requestJson<TopTurnoverResponse>(`/api/market/stocks/top-turnover?${query.toString()}`);
  },
  marketDateSnapshot: (date?: string) =>
    requestJson<MarketDateSnapshotResponse>(`/api/market${date ? `?date=${encodeURIComponent(date)}` : ""}`),
  macroDashboard: () => requestJson<MacroDashboardResponse>("/api/macro/dashboard"),
  macroTimeseries: (params: { series_ids: string[]; start?: string; end?: string; max_points?: number }) => {
    const query = new URLSearchParams();
    query.set("series_ids", params.series_ids.join(","));
    if (params.start) {
      query.set("start", params.start);
    }
    if (params.end) {
      query.set("end", params.end);
    }
    if (params.max_points) {
      query.set("max_points", String(params.max_points));
    }
    return requestJson<MacroTimeseriesResponse>(`/api/market/macro-timeseries?${query.toString()}`);
  },
  macroXray: (params: {
    universe_type?: string;
    universe_code?: string;
    scope?: string;
    period?: string;
    quarters?: number;
    lookback?: number;
  }) => {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") {
        query.set(key, String(value));
      }
    });
    return requestJson<MacroXrayResponse>(`/api/market/macro-xray?${query.toString()}`);
  },
  macroXrayTargets: (params: { universe_type?: string; lookback?: number; target_source?: string } = {}) => {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") {
        query.set(key, String(value));
      }
    });
    return requestJson<MacroXrayTargetsResponse>(`/api/market/macro-xray/targets?${query.toString()}`);
  },
  quotes: (symbols: string[]) =>
    requestJson<QuoteSnapshot[]>(`/api/market/quotes?symbols=${encodeURIComponent(symbols.join(","))}`),
  candles: (symbol: string, period = "daily", limit = 120) =>
    requestJson<CandleSnapshot[]>(
      `/api/market/candles?symbol=${encodeURIComponent(symbol)}&period=${period}&limit=${limit}`,
    ),
  compatQuotes: (symbols: string[], type = "realtime") =>
    requestJson<CompatQuotesResponse>(
      `/api/quotes?type=${encodeURIComponent(type)}&symbols=${encodeURIComponent(symbols.join(","))}`,
    ),
  compatDailySeries: (symbols: string[], limit = 120) =>
    requestJson<CompatQuoteSeriesResponse>(
      `/api/quotes?type=daily&symbols=${encodeURIComponent(symbols.join(","))}&limit=${limit}`,
    ),
  searchSymbols: (q: string, markets: MarketCode[] = ["CN", "HK", "US", "KR", "JP"]) =>
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
    let response: Response;
    try {
      response = await fetch(`${API_BASE}/api/ocr/positions`, {
        method: "POST",
        body: form,
      });
    } catch (error) {
      throw new ApiError("Backend API is unreachable", "network", { cause: error });
    }
    return parseJsonResponse<OcrPositionsResponse>(response);
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
  stockInsight: (payload: { position: PortfolioPosition; horizon_days: number }) =>
    requestJson<StockInsightResponse>("/api/ai/stock-insights", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};
