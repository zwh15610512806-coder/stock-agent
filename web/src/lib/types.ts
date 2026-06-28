export type MarketCode = "CN" | "HK" | "US";
export type AiReportAnalysisSkill = "standard" | "serenity";

export interface QuoteSnapshot {
  symbol: string;
  name: string;
  market: MarketCode;
  price: number;
  change: number;
  change_pct: number;
  volume: number;
  turnover: number;
  currency: string;
  source: string;
  as_of: string;
  delay_label: string;
}

export interface CandleSnapshot {
  symbol: string;
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  source: string;
  delay_label: string;
}

export interface MarketHeatItem {
  name: string;
  change_pct: number;
  turnover: number;
  direction: "up" | "down" | "flat";
}

export interface MarketOverviewItem {
  market: MarketCode;
  label: string;
  indices: QuoteSnapshot[];
  turnover: number;
  sentiment: number;
  breadth: {
    advances: number;
    declines: number;
    unchanged: number;
    limit_up: number;
    limit_down: number;
  };
  heatmap: MarketHeatItem[];
  source: string;
  delay_label: string;
  as_of: string;
}

export interface MarketOverviewResponse {
  markets: MarketOverviewItem[];
  disclaimer: string;
}

export type DashboardCacheStatus = "live" | "stale" | "partial" | "unavailable";
export type DashboardSourceState = "live" | "stale" | "unavailable";

export interface DashboardSourceStatus {
  name: string;
  status: DashboardSourceState;
  source: string;
  detail: string;
  as_of: string | null;
}

export interface AShareActivity {
  advances: number;
  declines: number;
  unchanged: number;
  limit_up: number;
  limit_down: number;
  suspended: number;
  sentiment: number;
  source: string;
  as_of: string | null;
}

export interface DashboardHeatItem {
  name: string;
  change_pct: number;
  turnover: number;
  net_amount: number;
  direction: "up" | "down" | "flat";
  source: string;
}

export interface FundFlowItem {
  symbol: string;
  name: string;
  change_pct: number;
  net_amount: number;
  turnover: number;
  source: string;
}

export interface FundFlowSummary {
  top_inflows: FundFlowItem[];
  top_outflows: FundFlowItem[];
  net_amount: number;
  source: string;
  as_of: string | null;
}

export interface MarketNewsItem {
  title: string;
  content: string;
  published_at: string | null;
  source: string;
  url: string;
}

export interface CommodityQuote {
  symbol: string;
  name: string;
  price: number;
  change: number;
  change_pct: number;
  unit: string;
  source: string;
  as_of: string | null;
  sparkline: number[];
}

export interface DragonTigerItem {
  symbol: string;
  name: string;
  trade_date: string;
  close: number;
  change_pct: number;
  turnover: number;
  sector: string;
  mini_candles: CandleSnapshot[];
  net_amount: number;
  buy_amount: number;
  sell_amount: number;
  reason: string;
  source: string;
}

export interface MarketDashboardResponse {
  as_of: string;
  cache_status: DashboardCacheStatus;
  source_status: DashboardSourceStatus[];
  primary_quote: QuoteSnapshot | null;
  primary_candles: CandleSnapshot[];
  markets: MarketOverviewItem[];
  a_share_turnover?: {
    value: number;
    source: string;
    status: DashboardSourceState;
    as_of: string | null;
  } | null;
  a_share_activity: AShareActivity | null;
  fund_flow_summary: FundFlowSummary | null;
  etf_heatmap: DashboardHeatItem[];
  industry_heatmap: DashboardHeatItem[];
  sector_heatmap: DashboardHeatItem[];
  concept_heatmap: DashboardHeatItem[];
  region_heatmap: DashboardHeatItem[];
  market_news: MarketNewsItem[];
  commodity_quotes: CommodityQuote[];
  dragon_tiger: DragonTigerItem[];
  index_sparklines: Record<string, number[]>;
  disclaimer: string;
}

export interface SymbolSearchResult {
  symbol: string;
  name: string;
  market: MarketCode;
  currency: string;
  type?: string;
  source?: string;
  exchange?: string;
}

export interface SourceMetric {
  name: string;
  value: number | null;
  unit: string;
  as_of: string | null;
  source: string;
  status: DashboardSourceState;
}

export interface MacroDashboardResponse {
  as_of: string;
  cache_status: DashboardCacheStatus;
  source_status: DashboardSourceStatus[];
  rates: SourceMetric[];
  indicators: SourceMetric[];
  bond_yields: SourceMetric[];
  fx_rates: SourceMetric[];
  disclaimer: string;
}

export interface StockScreenerItem {
  symbol: string;
  name: string;
  price: number | null;
  change_pct: number | null;
  turnover: number | null;
  volume?: number | null;
  pe?: number | null;
  pb?: number | null;
  market_cap?: number | null;
  source: string;
}

export interface StockScreenerResponse {
  as_of: string | null;
  source: string;
  status: DashboardSourceState;
  items: StockScreenerItem[];
  detail?: string;
}

export interface EtfSnapshot {
  symbol: string;
  name: string;
  price: number | null;
  change_pct: number | null;
  volume: number | null;
  turnover: number | null;
  source: string;
  as_of?: string | null;
}

export interface EtfSearchResponse {
  as_of: string | null;
  source: string;
  status: DashboardSourceState;
  items: EtfSnapshot[];
  detail?: string;
}

export interface EtfCandleSnapshot {
  symbol: string;
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number | null;
  turnover?: number | null;
  source: string;
}

export interface EtfCandlesResponse {
  items: EtfCandleSnapshot[];
  source: string;
  as_of: string | null;
  status: DashboardSourceState;
  detail?: string;
}

export interface CompatQuotesResponse {
  type: string;
  group: string;
  status: DashboardCacheStatus;
  source: string;
  as_of: string;
  items: QuoteSnapshot[];
  detail?: string;
}

export interface CompatQuoteSeriesItem {
  symbol: string;
  items: CandleSnapshot[];
  source: string;
}

export interface CompatQuoteSeriesResponse {
  type: string;
  group: string;
  status: DashboardCacheStatus;
  source: string;
  as_of: string;
  series: CompatQuoteSeriesItem[];
  detail?: string;
}

export interface PortfolioPosition {
  symbol: string;
  name: string;
  market: MarketCode;
  quantity: number;
  cost_price: number;
  current_price: number;
  currency: string;
  available_quantity?: number | null;
  market_value?: number | null;
  cost_value?: number | null;
  pnl?: number | null;
  pnl_pct?: number | null;
  source?: string | null;
  source_snapshot_at?: string | null;
  raw_fields?: Record<string, string>;
}

export interface PortfolioAnalysis {
  total_value: number;
  total_cost: number;
  pnl: number;
  pnl_pct: number;
  positions: Array<PortfolioPosition & {
    market_value: number;
    cost_value: number;
    pnl: number;
    pnl_pct: number;
  }>;
  weights: Array<{
    symbol: string;
    name: string;
    market: MarketCode;
    value: number;
    weight: number;
  }>;
  risks: Array<{
    level: "low" | "medium" | "high";
    title: string;
    detail: string;
  }>;
  suggestions: string[];
  quote_status?: Array<{
    symbol: string;
    status: DashboardSourceState;
    source: string;
    detail: string;
    as_of: string | null;
  }>;
  data_warnings?: string[];
  disclaimer: string;
}

export interface SourceKeyStatus {
  name: string;
  configured: boolean;
  detail: string;
}

export interface SourceCacheStatus {
  path: string;
  exists: boolean;
  writable: boolean;
  detail: string;
}

export interface FreeDataSource {
  name: string;
  category: string;
  source: string;
  detail: string;
}

export interface SourcesStatusResponse {
  key_status: SourceKeyStatus[];
  cache: SourceCacheStatus;
  free_data_sources: FreeDataSource[];
  disclaimer: string;
}

export interface OcrPositionsResponse {
  status: string;
  positions: PortfolioPosition[];
  message: string;
  raw_lines?: string[];
}

export interface AiReportResponse {
  status: "completed" | "unavailable" | "failed";
  symbol: string;
  market: MarketCode;
  summary: string;
  sections: Array<{ title: string; body: string }>;
  watch_metrics: string[];
  risks: string[];
  model: string;
  metadata?: {
    source?: string;
    analysis_skill?: AiReportAnalysisSkill;
    skill_label?: string;
    [key: string]: unknown;
  };
  disclaimer: string;
}

export interface StockInsightCitation {
  title: string;
  url: string;
  source: string;
  published_at?: string | null;
}

export interface StockInsightResponse {
  status: "completed" | "partial" | "unavailable" | "failed";
  symbol: string;
  market: MarketCode;
  as_of: string;
  quote: QuoteSnapshot | null;
  candles: CandleSnapshot[];
  summary: string;
  trend: string[];
  financials: string[];
  events: string[];
  risks: string[];
  citations: StockInsightCitation[];
  data_warnings: string[];
  model: string;
  disclaimer: string;
}
