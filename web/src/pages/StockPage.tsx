import { FormEvent, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { CandleChart } from "../components/CandleChart";
import { EmptyState } from "../components/EmptyState";
import { MetricCard } from "../components/MetricCard";
import { api } from "../lib/api";
import { formatCompact, formatNumber, toneForPct } from "../lib/format";
import type { MarketCode } from "../lib/types";

export function StockPage() {
  const [symbol, setSymbol] = useState("600519.SH");
  const [querySymbol, setQuerySymbol] = useState("600519.SH");
  const [market, setMarket] = useState<MarketCode>("CN");
  const quoteQuery = useQuery({
    queryKey: ["quote", querySymbol],
    queryFn: async () => (await api.quotes([querySymbol]))[0],
  });
  const candles = useQuery({
    queryKey: ["candles", querySymbol],
    queryFn: () => api.candles(querySymbol, "daily", 120),
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    setQuerySymbol(symbol.trim().toUpperCase());
  }

  const quote = quoteQuery.data;

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

      {quoteQuery.isError ? <EmptyState title="个股加载失败" body="检查代码格式或后端 API 状态。" /> : null}

      <div className="metric-grid">
        <MetricCard label={quote?.name || querySymbol} value={formatNumber(quote?.price || 0)} detail={quote?.symbol} />
        <MetricCard
          label="涨跌幅"
          value={`${formatNumber(quote?.change_pct || 0)}%`}
          detail={quote?.delay_label}
          tone={toneForPct(quote?.change_pct || 0)}
        />
        <MetricCard label="成交量" value={formatCompact(quote?.volume || 0)} detail={quote?.source} />
        <MetricCard label="成交额估算" value={formatCompact(quote?.turnover || 0)} detail={quote?.currency} />
      </div>

      <section className="data-panel">
        <div className="panel-head">
          <div>
            <h3>{quote?.name || querySymbol} K线</h3>
            <span>{candles.data?.[0]?.delay_label || "加载中"}</span>
          </div>
        </div>
        {candles.data?.length ? <CandleChart candles={candles.data} /> : <div className="chart-skeleton" />}
      </section>
    </div>
  );
}
