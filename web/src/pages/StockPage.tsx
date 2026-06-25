import { FormEvent, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { CandleChart } from "../components/CandleChart";
import { EmptyState } from "../components/EmptyState";
import { MetricCard } from "../components/MetricCard";
import { api, apiFailureMessage } from "../lib/api";
import { formatCompact, formatNumber, toneForPct } from "../lib/format";
import type { MarketCode } from "../lib/types";

export function StockPage() {
  const [symbol, setSymbol] = useState("600519.SH");
  const [querySymbol, setQuerySymbol] = useState("600519.SH");
  const [market, setMarket] = useState<MarketCode>("CN");
  const quoteQuery = useQuery({
    queryKey: ["quote", querySymbol],
    queryFn: () => api.compatQuotes([querySymbol]),
  });
  const candles = useQuery({
    queryKey: ["candles", querySymbol],
    queryFn: () => api.compatDailySeries([querySymbol], 120),
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    setQuerySymbol(symbol.trim().toUpperCase());
  }

  const quote = quoteQuery.data?.items[0];
  const chartCandles = candles.data?.series[0]?.items || [];

  return (
    <div className="page-stack">
      <section className="section-head">
        <div>
          <div className="eyebrow">SINGLE NAME</div>
          <h2>个股行情</h2>
          <p>支持 A股、港股、美股代码查询。图表仅展示走势、K线和成交量。</p>
        </div>
        <form className="terminal-search" onSubmit={submit}>
          <select value={market} onChange={(event) => setMarket(event.target.value as MarketCode)}>
            <option value="CN">A股</option>
            <option value="HK">港股</option>
            <option value="US">美股</option>
          </select>
          <input value={symbol} onChange={(event) => setSymbol(event.target.value)} placeholder="600519.SH / 00700.HK / AAPL" />
          <button className="terminal-button" type="submit">
            <Search size={16} />
            查询
          </button>
        </form>
      </section>

      {quoteQuery.isError ? <EmptyState title="个股加载失败" body={apiFailureMessage(quoteQuery.error, "个股报价")} /> : null}
      {!quoteQuery.isPending && !quoteQuery.isError && quoteQuery.data?.status === "unavailable" ? (
        <EmptyState title="个股报价暂不可用" body={quoteQuery.data.detail || "免费行情源暂时无法返回真实报价。"} />
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

      <section className="data-panel">
        <div className="panel-head">
          <div>
            <h3>{quote?.name || querySymbol} K线</h3>
            <span>{chartCandles[0]?.delay_label || candles.data?.detail || "加载中"}</span>
          </div>
        </div>
        {candles.isError ? <EmptyState title="K 线加载失败" body={apiFailureMessage(candles.error, "个股 K 线")} /> : null}
        {!candles.isPending && !candles.isError && candles.data?.status === "unavailable" ? (
          <EmptyState title="K 线暂不可用" body={candles.data.detail || "免费历史行情源暂时无法返回真实 K 线。"} />
        ) : null}
        {!candles.isPending && !candles.isError && chartCandles.length ? <CandleChart candles={chartCandles} /> : null}
        {candles.isPending ? <div className="chart-skeleton" /> : null}
      </section>
    </div>
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
