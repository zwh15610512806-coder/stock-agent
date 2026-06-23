import { FormEvent, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { BarChart3, Briefcase, Filter, PackageOpen, Search, Star } from "lucide-react";
import { CandleChart } from "../components/CandleChart";
import { EmptyState } from "../components/EmptyState";
import { MetricCard } from "../components/MetricCard";
import { api } from "../lib/api";
import { formatCompact, formatNumber, toneForPct } from "../lib/format";
import type { MarketCode } from "../lib/types";

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

  const results = useQuery({
    queryKey: ["stocks-center-symbol-search", activeQuery],
    queryFn: () => api.searchSymbols(activeQuery, ["CN", "HK", "US"]),
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
          <span>先用代码和公司名称检索，后续接入财务、估值和技术指标筛选。</span>
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
      <div className="quote-list stocks-selector-results">
        {results.data?.map((item) => (
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
      {!results.isPending && !results.data?.length ? (
        <EmptyState title="暂无匹配股票" body="调整关键词后重新搜索，页面不会展示模拟证券。" />
      ) : null}
    </section>
  );
}

function EtfPanel() {
  return (
    <section className="data-panel stocks-etf-panel">
      <div className="panel-head">
        <div>
          <h3>ETF 资产包</h3>
          <span>净值、持仓、折溢价与行业权重</span>
        </div>
        <BarChart3 size={18} />
      </div>
      <EmptyState
        title="ETF 真实数据暂不可用"
        body="接入 ETF 净值、持仓和折溢价数据源后，这里会展示资产包视角；当前不展示样例或模拟数据。"
      />
    </section>
  );
}
