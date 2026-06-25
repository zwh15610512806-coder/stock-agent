import { FormEvent, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { BarChart3, Briefcase, Filter, PackageOpen, Search, Star } from "lucide-react";
import { CandleChart } from "../components/CandleChart";
import { EmptyState } from "../components/EmptyState";
import { MetricCard } from "../components/MetricCard";
import { api, apiFailureMessage } from "../lib/api";
import { formatCompact, formatNumber, toneForPct } from "../lib/format";
import type {
  CandleSnapshot,
  EtfCandleSnapshot,
  MarketCode,
  StockScreenerItem,
  StockScreenerResponse,
  SymbolSearchResult,
} from "../lib/types";

type StocksTab = "workbench" | "selector" | "etf";

const tabs: Array<{ id: StocksTab; label: string; icon: typeof Briefcase }> = [
  { id: "workbench", label: "工作台", icon: Briefcase },
  { id: "selector", label: "选股器", icon: Filter },
  { id: "etf", label: "ETF", icon: PackageOpen },
];

export function StocksPage() {
  const [activeTab, setActiveTab] = useState<StocksTab>("workbench");

  return (
    <div className="page-stack stocks-center-page">
      <section className="section-head stocks-hero">
        <div>
          <div className="eyebrow">STOCKS CENTER</div>
          <h2>选股中心</h2>
          <p>在工作台查看股票详情并管理自选，使用选股器进行多指标筛选，或用 ETF 视角观察资产包。</p>
        </div>
        <div className="terminal-search stocks-tabs" role="tablist" aria-label="选股中心视图">
          {tabs.map((tab) => (
            <button
              aria-selected={activeTab === tab.id}
              className={`terminal-button stocks-tab${activeTab === tab.id ? " active" : ""}`}
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              role="tab"
              type="button"
            >
              <tab.icon size={16} />
              {tab.label}
            </button>
          ))}
        </div>
      </section>

      {activeTab === "workbench" ? <WorkbenchPanel /> : null}
      {activeTab === "selector" ? <SelectorPanel /> : null}
      {activeTab === "etf" ? <EtfPanel /> : null}
    </div>
  );
}

function WorkbenchPanel() {
  const [symbol, setSymbol] = useState("600519.SH");
  const [querySymbol, setQuerySymbol] = useState("600519.SH");
  const [market, setMarket] = useState<MarketCode>("CN");

  const quoteQuery = useQuery({
    queryKey: ["stocks-center-quote", querySymbol],
    queryFn: () => api.compatQuotes([querySymbol]),
    enabled: querySymbol.length > 0,
  });

  const candles = useQuery({
    queryKey: ["stocks-center-candles", querySymbol],
    queryFn: () => api.compatDailySeries([querySymbol], 120),
    enabled: querySymbol.length > 0,
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    const nextSymbol = symbol.trim().toUpperCase();
    if (nextSymbol) {
      setQuerySymbol(nextSymbol);
    }
  }

  const quote = quoteQuery.data?.items[0];
  const chartCandles = candles.data?.series[0]?.items || [];

  return (
    <>
      <section className="section-head stocks-workbench-head">
        <div>
          <div className="eyebrow">WORKBENCH</div>
          <h3>股票工作台</h3>
          <p>输入 A 股、港股或美股代码，查看实时可用的报价、走势和成交信息。</p>
        </div>
        <form className="terminal-search" onSubmit={submit}>
          <select value={market} onChange={(event) => setMarket(event.target.value as MarketCode)} aria-label="市场">
            <option value="CN">A股</option>
            <option value="HK">港股</option>
            <option value="US">美股</option>
          </select>
          <input
            aria-label="股票代码"
            value={symbol}
            onChange={(event) => setSymbol(event.target.value)}
            placeholder="600519.SH / 00700.HK / AAPL"
          />
          <button className="terminal-button" type="submit">
            <Search size={16} />
            查询
          </button>
        </form>
      </section>

      {quoteQuery.isError ? <EmptyState title="股票加载失败" body={apiFailureMessage(quoteQuery.error, "股票报价")} /> : null}
      {!quoteQuery.isPending && !quoteQuery.isError && quoteQuery.data?.status === "unavailable" ? (
        <EmptyState title="股票报价暂不可用" body={quoteQuery.data.detail || "免费行情源暂时无法返回真实报价。"} />
      ) : null}

      <div className="metric-grid">
        <MetricCard label={quote?.name || querySymbol} value={formatOptionalNumber(quote?.price)} detail={quote?.symbol || "等待报价"} />
        <MetricCard
          label="涨跌幅"
          value={formatOptionalPct(quote?.change_pct)}
          detail={quote?.delay_label || "等待行情源"}
          tone={toneForPct(quote?.change_pct ?? 0)}
        />
        <MetricCard label="成交量" value={formatOptionalCompact(quote?.volume)} detail={quote?.source || "真实数据源"} />
        <MetricCard label="成交额估算" value={formatOptionalCompact(quote?.turnover)} detail={quote?.currency || market} />
      </div>

      <section className="data-panel stocks-selector-panel">
        <div className="panel-head">
          <div>
            <h3>{quote?.name || querySymbol} K线</h3>
            <span>{chartCandles[0]?.delay_label || candles.data?.detail || "加载中"}</span>
          </div>
          <button className="terminal-button soft" type="button">
            <Star size={15} />
            加入自选
          </button>
        </div>
        {candles.isError ? <EmptyState title="K 线加载失败" body={apiFailureMessage(candles.error, "股票 K 线")} /> : null}
        {!candles.isPending && !candles.isError && candles.data?.status === "unavailable" ? (
          <EmptyState title="K 线暂不可用" body={candles.data.detail || "免费历史行情源暂时无法返回真实 K 线。"} />
        ) : null}
        {!candles.isPending && !candles.isError && chartCandles.length ? <CandleChart candles={chartCandles} /> : null}
        {candles.isPending ? <div className="chart-skeleton" /> : null}
      </section>
    </>
  );
}

function SelectorPanel() {
  const [query, setQuery] = useState("茅台");
  const [activeQuery, setActiveQuery] = useState("茅台");
  const [market, setMarket] = useState<MarketCode>("CN");

  const screener = useQuery<StockScreenerResponse | SymbolSearchResult[]>({
    queryKey: ["stocks-center-screener", market, activeQuery],
    queryFn: () =>
      market === "CN"
        ? api.stockScreener({ query: activeQuery, limit: 30 })
        : api.searchSymbols(activeQuery, [market]),
    enabled: activeQuery.length > 0,
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    setActiveQuery(query.trim());
  }

  return (
    <section className="data-panel">
      <div className="panel-head">
        <div>
          <h3>选股器</h3>
          <span>{market === "CN" ? "A 股真实股票池与估值/成交指标筛选。" : "港美股暂保留基础代码检索。"}</span>
        </div>
      </div>
      <form className="terminal-search" onSubmit={submit}>
        <select value={market} onChange={(event) => setMarket(event.target.value as MarketCode)} aria-label="筛选市场">
          <option value="CN">A股</option>
          <option value="HK">港股</option>
          <option value="US">美股</option>
        </select>
        <input
          aria-label="搜索股票"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="输入代码或公司名称"
        />
        <button className="terminal-button" type="submit">
          <Search size={16} />
          搜索
        </button>
      </form>
      {market === "CN" ? (
        <ScreenerTable
          items={(screener.data as { items?: StockScreenerItem[] } | undefined)?.items || []}
          source={(screener.data as { source?: string } | undefined)?.source}
        />
      ) : (
        <div className="quote-list stocks-selector-results">
          {(screener.data as Array<{ symbol: string; name: string; market: string; currency: string }> | undefined)?.map((item) => (
            <div className="quote-row" key={item.symbol}>
              <div>
                <strong>{item.name}</strong>
                <span>{item.symbol}</span>
              </div>
              <div className="quote-price">
                <strong>{item.market}</strong>
                <span>{item.currency}</span>
              </div>
            </div>
          ))}
        </div>
      )}
      {screener.isError ? <EmptyState title="选股器加载失败" body={apiFailureMessage(screener.error, "选股器")} /> : null}
      {market === "CN" &&
      !screener.isPending &&
      !screener.isError &&
      (screener.data as { status?: string; detail?: string } | undefined)?.status === "unavailable" ? (
        <EmptyState
          title="选股器数据源不可用"
          body={(screener.data as { detail?: string } | undefined)?.detail || "免费 A 股筛选源暂时不可用，页面不会展示模拟数据。"}
        />
      ) : null}
      {!screener.isPending &&
      !screener.isError &&
      (market !== "CN" || (screener.data as { status?: string } | undefined)?.status !== "unavailable") &&
      (market === "CN"
        ? !((screener.data as { items?: StockScreenerItem[] } | undefined)?.items || []).length
        : !(screener.data as unknown[] | undefined)?.length) ? (
        <EmptyState title="暂无匹配股票" body="调整关键词后重新搜索，页面不会展示模拟证券。" />
      ) : null}
    </section>
  );
}

function ScreenerTable({ items, source }: { items: StockScreenerItem[]; source?: string }) {
  return (
    <div className="table-wrap portfolio-table-wrap stocks-screener-table">
      <table className="portfolio-table">
        <thead>
          <tr>
            <th>股票</th>
            <th>价格</th>
            <th>涨跌幅</th>
            <th>成交额</th>
            <th>PE</th>
            <th>PB</th>
            <th>来源</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.symbol}>
              <td>
                <strong>{item.name}</strong>
                <span>{item.symbol}</span>
              </td>
              <td>{formatOptionalNumber(item.price, 2)}</td>
              <td className={`tone-text ${toneForPct(item.change_pct ?? 0)}`}>{formatOptionalPct(item.change_pct)}</td>
              <td>{formatOptionalCompact(item.turnover)}</td>
              <td>{item.pe === null || item.pe === undefined ? "--" : formatNumber(item.pe, 2)}</td>
              <td>{item.pb === null || item.pb === undefined ? "--" : formatNumber(item.pb, 2)}</td>
              <td>{item.source || source || "--"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function EtfPanel() {
  const [query, setQuery] = useState("沪深300");
  const [activeQuery, setActiveQuery] = useState("沪深300");
  const [selectedSymbol, setSelectedSymbol] = useState("");
  const etfs = useQuery({
    queryKey: ["stocks-center-etfs", activeQuery],
    queryFn: () => api.searchEtfs(activeQuery, 20),
  });
  const symbol = selectedSymbol || etfs.data?.items[0]?.symbol || "";
  const candles = useQuery({
    queryKey: ["stocks-center-etf-candles", symbol],
    queryFn: () => api.etfCandles(symbol, "daily", 120),
    enabled: symbol.length > 0,
  });
  const chartCandles = (candles.data?.items || []).map((item) => toChartCandle(item, candles.data?.source || "akshare-etf"));

  function submit(event: FormEvent) {
    event.preventDefault();
    setSelectedSymbol("");
    setActiveQuery(query.trim());
  }

  return (
    <section className="data-panel stocks-etf-panel">
      <div className="panel-head">
        <div>
          <h3>ETF 资产包</h3>
          <span>{etfs.data?.source || "akshare-etf"}</span>
        </div>
        <BarChart3 size={18} />
      </div>
      <form className="terminal-search" onSubmit={submit}>
        <input aria-label="搜索 ETF" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="沪深300 / 510300" />
        <button className="terminal-button" type="submit">
          <Search size={16} />
          搜索
        </button>
      </form>
      <div className="quote-list stocks-selector-results">
        {etfs.data?.items.map((item) => (
          <button
            className={`quote-row stocks-etf-row${symbol === item.symbol ? " active" : ""}`}
            key={item.symbol}
            onClick={() => setSelectedSymbol(item.symbol)}
            type="button"
          >
            <div>
              <strong>{item.name}</strong>
              <span>{item.symbol}</span>
            </div>
            <div className="quote-price">
              <strong>{formatOptionalNumber(item.price, 2)}</strong>
              <span className={`tone-text ${toneForPct(item.change_pct ?? 0)}`}>{formatOptionalPct(item.change_pct)}</span>
            </div>
          </button>
        ))}
      </div>
      {etfs.isError ? <EmptyState title="ETF 加载失败" body={apiFailureMessage(etfs.error, "ETF 列表")} /> : null}
      {!etfs.isPending && !etfs.isError && etfs.data?.status === "unavailable" ? (
        <EmptyState title="ETF 数据源不可用" body={etfs.data.detail || "免费 ETF 源暂时无法返回真实数据。"} />
      ) : null}
      {!etfs.isPending && !etfs.isError && etfs.data?.status !== "unavailable" && !etfs.data?.items.length ? (
        <EmptyState title="暂无匹配 ETF" body="调整关键词后重新搜索。" />
      ) : null}
      <div className="stocks-etf-chart">
        {candles.isPending && symbol ? <div className="chart-skeleton" /> : null}
        {candles.isError ? <EmptyState title="ETF K 线加载失败" body={apiFailureMessage(candles.error, "ETF K 线")} /> : null}
        {!candles.isPending && !candles.isError && chartCandles.length ? <CandleChart candles={chartCandles} /> : null}
        {!candles.isPending && !candles.isError && symbol && !chartCandles.length ? (
          <EmptyState title="ETF K 线暂不可用" body={candles.data?.detail || "免费 ETF 历史源暂时无法返回真实数据。"} />
        ) : null}
      </div>
    </section>
  );
}

function formatOptionalNumber(value: number | null | undefined, digits = 2): string {
  return value === null || value === undefined ? "--" : formatNumber(value, digits);
}

function formatOptionalCompact(value: number | null | undefined): string {
  return value === null || value === undefined ? "--" : formatCompact(value);
}

function formatOptionalPct(value: number | null | undefined): string {
  return value === null || value === undefined ? "--" : `${formatNumber(value, 2)}%`;
}

function toChartCandle(item: EtfCandleSnapshot, source: string): CandleSnapshot {
  return {
    symbol: item.symbol,
    date: item.date,
    open: item.open,
    high: item.high,
    low: item.low,
    close: item.close,
    volume: item.volume || 0,
    source: item.source || source,
    delay_label: source,
  };
}
