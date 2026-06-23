import { FormEvent, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { BarChart3, Briefcase, Filter, PackageOpen, Search, Star } from "lucide-react";
import { CandleChart } from "../components/CandleChart";
import { EmptyState } from "../components/EmptyState";
import { MetricCard } from "../components/MetricCard";
import { api } from "../lib/api";
import { formatCompact, formatNumber, toneForPct } from "../lib/format";
import type { MarketCode, StockScreenerItem, StockScreenerResponse, SymbolSearchResult } from "../lib/types";

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
    queryFn: async () => (await api.quotes([querySymbol]))[0],
    enabled: querySymbol.length > 0,
  });

  const candles = useQuery({
    queryKey: ["stocks-center-candles", querySymbol],
    queryFn: () => api.candles(querySymbol, "daily", 120),
    enabled: querySymbol.length > 0,
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    const nextSymbol = symbol.trim().toUpperCase();
    if (nextSymbol) {
      setQuerySymbol(nextSymbol);
    }
  }

  const quote = quoteQuery.data;

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

      {quoteQuery.isError ? <EmptyState title="股票加载失败" body="检查代码格式或后端 API 状态。" /> : null}

      <div className="metric-grid">
        <MetricCard label={quote?.name || querySymbol} value={formatNumber(quote?.price || 0)} detail={quote?.symbol || "等待报价"} />
        <MetricCard
          label="涨跌幅"
          value={`${formatNumber(quote?.change_pct || 0)}%`}
          detail={quote?.delay_label || "等待行情源"}
          tone={toneForPct(quote?.change_pct || 0)}
        />
        <MetricCard label="成交量" value={formatCompact(quote?.volume || 0)} detail={quote?.source || "真实数据源"} />
        <MetricCard label="成交额估算" value={formatCompact(quote?.turnover || 0)} detail={quote?.currency || market} />
      </div>

      <section className="data-panel stocks-selector-panel">
        <div className="panel-head">
          <div>
            <h3>{quote?.name || querySymbol} K线</h3>
            <span>{candles.data?.[0]?.delay_label || "加载中"}</span>
          </div>
          <button className="terminal-button soft" type="button">
            <Star size={15} />
            加入自选
          </button>
        </div>
        {candles.data?.length ? <CandleChart candles={candles.data} /> : <div className="chart-skeleton" />}
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
      {!screener.isPending &&
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
              <td>{formatNumber(item.price, 2)}</td>
              <td className={`tone-text ${toneForPct(item.change_pct)}`}>{formatNumber(item.change_pct, 2)}%</td>
              <td>{formatCompact(item.turnover)}</td>
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
              <strong>{formatNumber(item.price, 2)}</strong>
              <span className={`tone-text ${toneForPct(item.change_pct)}`}>{formatNumber(item.change_pct, 2)}%</span>
            </div>
          </button>
        ))}
      </div>
      {etfs.isError ? <EmptyState title="ETF 数据源不可用" body="免费 ETF 源暂时无法返回真实数据。" /> : null}
      {!etfs.isPending && !etfs.data?.items.length ? <EmptyState title="暂无匹配 ETF" body="调整关键词后重新搜索。" /> : null}
      <div className="stocks-etf-chart">
        {candles.data?.length ? <CandleChart candles={candles.data} /> : <div className="chart-skeleton" />}
      </div>
    </section>
  );
}
