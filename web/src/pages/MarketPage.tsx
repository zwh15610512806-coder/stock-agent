import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  BarChart3,
  Flame,
  Newspaper,
  PackageOpen,
  RefreshCw,
  Trophy,
} from "lucide-react";
import { Heatmap } from "../components/Heatmap";
import { SourceStatusBadge } from "../components/SourceStatusBadge";
import { api } from "../lib/api";
import { formatCompact, formatMoney, formatNumber, toneForPct } from "../lib/format";
import type {
  AShareActivity,
  CommodityQuote,
  DragonTigerItem,
  DashboardCacheStatus,
  DashboardSourceStatus,
  FundFlowSummary,
  MarketNewsItem,
  QuoteSnapshot,
} from "../lib/types";

export function MarketPage() {
  const dashboard = useQuery({
    queryKey: ["market-dashboard", "reference-overview"],
    queryFn: () => api.marketDashboard(["CN", "HK", "US"], "daily"),
  });
  const data = dashboard.data;
  const isInitialLoading = dashboard.isPending && !data;
  const indexQuotes = data?.markets.flatMap((market) => market.indices) || [];
  const aShare = data?.markets.find((market) => market.market === "CN");
  const aShareTurnover = data?.a_share_turnover;
  const heatmapData = [
    ...(data?.industry_heatmap || []),
    ...(data?.concept_heatmap || []),
    ...(data?.region_heatmap || []),
  ];
  const sourceWarning = isInitialLoading
    ? ""
    : marketSourceWarning(dashboard.isError, data?.cache_status, data?.source_status || []);

  return (
    <div className="market-overview-board">
      <section className="market-hero-strip">
        <div>
          <span className="market-kicker">进入资金信号沙盘</span>
          <h2>市场全景</h2>
          <p>聚合全球指数、A股脉搏、快讯、板块资金、大宗商品和龙虎榜，所有模块仅展示真实源或缓存。</p>
        </div>
        <div className="market-hero-actions">
          <span className="market-clock">更新 {isInitialLoading ? "加载中" : formatDateTime(data?.as_of)}</span>
          <SourceStatusBadge status={isInitialLoading ? "loading" : data?.cache_status || "unavailable"} />
          <button className="terminal-button soft market-refresh" onClick={() => dashboard.refetch()} type="button">
            <RefreshCw size={15} />
            刷新
          </button>
        </div>
      </section>

      {isInitialLoading ? (
        <div className="source-loading-banner">
          <strong>正在加载真实市场数据</strong>
          <span>正在连接免费行情源和本地 SQLite 缓存。</span>
        </div>
      ) : null}

      {sourceWarning ? <div className="source-warning">{sourceWarning}</div> : null}

      <section className="market-block">
        <SectionTitle icon={BarChart3} title="全球指数" subtitle="A股、港股、美股核心指数与短线轨迹" />
        {isInitialLoading ? (
          <MarketLoading title="正在加载指数行情" />
        ) : indexQuotes.length ? (
          <div className="index-card-grid">
            {indexQuotes.map((quote) => (
              <IndexCard key={quote.symbol} quote={quote} values={data?.index_sparklines[quote.symbol] || []} />
            ))}
          </div>
        ) : (
          <MarketEmpty title="暂无真实指数行情" />
        )}
      </section>

      <section className="market-block">
        <SectionTitle icon={Activity} title="市场脉搏" subtitle="成交、涨跌家数、赚钱效应与资金流" />
        <div className="pulse-grid">
          <PulseMetric
            label="两市成交额"
            value={isInitialLoading ? "加载中" : aShareTurnover?.value ? formatTrillion(aShareTurnover.value) : "--"}
            detail={aShareTurnover?.source || "交易所总貌口径"}
          />
          <PulseMetric
            label="涨 / 跌"
            value={isInitialLoading ? "加载中" : formatBreadth(data?.a_share_activity)}
            detail={`平盘 ${data?.a_share_activity?.unchanged ?? "--"}`}
            tone="split"
          />
          <PulseMetric label="情绪温度" value={isInitialLoading ? "加载中" : data?.a_share_activity ? formatNumber(data.a_share_activity.sentiment, 1) : "--"} detail="中性线 50" />
          <PulseMetric
            label="主力净流入"
            value={isInitialLoading ? "加载中" : data?.fund_flow_summary ? formatMoney(data.fund_flow_summary.net_amount) : "--"}
            detail={isInitialLoading ? "等待资金流真实源" : data?.fund_flow_summary?.source || "无可用真实源"}
            tone={(data?.fund_flow_summary?.net_amount || 0) >= 0 ? "up" : "down"}
          />
        </div>
        {isInitialLoading ? <MarketLoading title="正在加载涨跌家数" compact /> : <BreadthBar activity={data?.a_share_activity || null} />}
        {isInitialLoading ? <MarketLoading title="正在加载资金流" compact /> : <FundFlowStrip summary={data?.fund_flow_summary || null} />}
      </section>

      <section className="market-block news-block">
        <SectionTitle icon={Newspaper} title="7x24快讯" subtitle="全局财经快讯，按发布时间倒序" />
        {isInitialLoading ? <MarketLoading title="正在加载真实快讯" /> : <NewsTimeline news={data?.market_news || []} />}
      </section>

      <section className="market-block heatmap-board">
        <SectionTitle icon={Flame} title="板块热力图" subtitle="行业、概念、地域资金流合并视图" />
        {isInitialLoading ? (
          <MarketLoading title="正在加载板块热力" />
        ) : heatmapData.length ? (
          <>
            <Heatmap data={heatmapData} />
            <div className="heat-chip-row">
              {heatmapData.slice(0, 10).map((item) => (
                <span key={`${item.source}-${item.name}`} className={`heat-chip tone-text ${toneForPct(item.change_pct)}`}>
                  {item.name} {formatNumber(item.change_pct, 2)}%
                </span>
              ))}
            </div>
          </>
        ) : (
          <MarketEmpty title="暂无真实板块热力" />
        )}
      </section>

      <div className="lower-market-grid">
        <section className="market-block">
          <SectionTitle icon={PackageOpen} title="大宗商品" subtitle="贵金属与海外商品期货" />
          {isInitialLoading ? <MarketLoading title="正在加载商品行情" /> : <CommodityPanel quotes={data?.commodity_quotes || []} />}
        </section>
        <section className="market-block">
          <SectionTitle icon={Trophy} title="龙虎榜" subtitle="最近交易日净买额排行" />
          {isInitialLoading ? <MarketLoading title="正在加载龙虎榜" /> : <DragonTigerList items={data?.dragon_tiger || []} />}
        </section>
      </div>
    </div>
  );
}

function SectionTitle({
  icon: Icon,
  title,
  subtitle,
}: {
  icon: typeof Activity;
  title: string;
  subtitle: string;
}) {
  return (
    <div className="market-section-title">
      <div>
        <Icon size={16} />
        <h3>{title}</h3>
      </div>
      <span>{subtitle}</span>
    </div>
  );
}

function IndexCard({ quote, values }: { quote: QuoteSnapshot; values: number[] }) {
  const tone = toneForPct(quote.change_pct);
  return (
    <article className={`index-card index-${tone}`}>
      <div className="index-meta">
        <span>{quote.symbol}</span>
        <strong>{quote.name}</strong>
      </div>
      <div className="index-price-row">
        <span className="index-price">{formatNumber(quote.price, 2)}</span>
        <span className={`pct-pill ${tone}`}>{formatSignedPct(quote.change_pct)}</span>
      </div>
      <Sparkline values={values} tone={tone} />
      <div className="index-source">{quote.delay_label}</div>
    </article>
  );
}

function Sparkline({ values, tone }: { values: number[]; tone: "up" | "down" | "neutral" }) {
  if (values.length < 2) {
    return <div className="sparkline-empty" />;
  }
  const width = 150;
  const height = 48;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const spread = max - min || 1;
  const points = values
    .map((value, index) => {
      const x = (index / (values.length - 1)) * width;
      const y = height - ((value - min) / spread) * (height - 8) - 4;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");
  return (
    <svg className="sparkline" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="指数短线走势">
      <polyline className={`sparkline-line ${tone}`} points={points} />
    </svg>
  );
}

function PulseMetric({
  label,
  value,
  detail,
  tone = "neutral",
}: {
  label: string;
  value: string;
  detail: string;
  tone?: "neutral" | "up" | "down" | "split";
}) {
  return (
    <article className={`pulse-metric pulse-${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </article>
  );
}

function BreadthBar({ activity }: { activity: AShareActivity | null }) {
  if (!activity) {
    return <MarketEmpty title="暂无真实涨跌家数" compact />;
  }
  const total = Math.max(1, activity.advances + activity.declines + activity.unchanged);
  const up = (activity.advances / total) * 100;
  const flat = (activity.unchanged / total) * 100;
  const down = Math.max(0, 100 - up - flat);
  return (
    <div className="breadth-panel">
      <div className="breadth-labels">
        <span>上涨 {activity.advances}</span>
        <span>下跌 {activity.declines}</span>
        <span>涨停 {activity.limit_up}</span>
        <span>跌停 {activity.limit_down}</span>
      </div>
      <div className="breadth-track" aria-label="市场涨跌家数比例">
        <span className="breadth-up" style={{ width: `${up}%` }} />
        <span className="breadth-flat" style={{ width: `${flat}%` }} />
        <span className="breadth-down" style={{ width: `${down}%` }} />
      </div>
    </div>
  );
}

function FundFlowStrip({ summary }: { summary: FundFlowSummary | null }) {
  if (!summary) {
    return <MarketEmpty title="暂无真实资金流" compact />;
  }
  const rows = [...summary.top_inflows, ...summary.top_outflows].slice(0, 8);
  return (
    <div className="fund-flow-strip">
      {rows.map((item) => (
        <div key={`${item.symbol}-${item.name}`}>
          <strong>{item.name}</strong>
          <span className={item.net_amount >= 0 ? "tone-red" : "tone-green"}>{formatMoney(item.net_amount)}</span>
          <small>{formatSignedPct(item.change_pct)}</small>
        </div>
      ))}
    </div>
  );
}

function NewsTimeline({ news }: { news: MarketNewsItem[] }) {
  if (!news.length) {
    return <MarketEmpty title="暂无真实快讯" />;
  }
  return (
    <div className="news-timeline">
      {news.slice(0, 8).map((item) => (
        <a href={item.url || undefined} key={`${item.published_at}-${item.title}`} target={item.url ? "_blank" : undefined} rel="noreferrer">
          <time>{formatNewsTime(item.published_at)}</time>
          <strong>{item.title}</strong>
          <span>{item.content || item.source}</span>
        </a>
      ))}
    </div>
  );
}

function CommodityPanel({ quotes }: { quotes: CommodityQuote[] }) {
  if (!quotes.length) {
    return <MarketEmpty title="暂无真实商品行情" />;
  }
  return (
    <div className="commodity-list">
      {quotes.map((quote) => {
        const tone = toneForPct(quote.change_pct);
        return (
          <div className="commodity-row" key={`${quote.source}-${quote.symbol}`}>
            <div>
              <strong>{quote.name}</strong>
              <span>{quote.symbol}</span>
            </div>
            <div>
              <strong>{formatNumber(quote.price, 2)}</strong>
              <span className={`tone-text ${tone}`}>{formatSignedPct(quote.change_pct)}</span>
            </div>
            <Sparkline values={quote.sparkline} tone={tone} />
          </div>
        );
      })}
    </div>
  );
}

function DragonTigerList({ items }: { items: DragonTigerItem[] }) {
  if (!items.length) {
    return <MarketEmpty title="暂无真实龙虎榜" />;
  }
  return (
    <div className="dragon-list">
      {items.slice(0, 10).map((item, index) => (
        <div className="dragon-row" key={`${item.trade_date}-${item.symbol}`}>
          <span className="rank-number">{index + 1}</span>
          <div>
            <strong>{item.name}</strong>
            <span>{item.symbol} · {item.reason || item.trade_date}</span>
          </div>
          <div>
            <strong>{formatNumber(item.close, 2)}</strong>
            <span className={`tone-text ${toneForPct(item.change_pct)}`}>{formatSignedPct(item.change_pct)}</span>
          </div>
          <span className={item.net_amount >= 0 ? "tone-red" : "tone-green"}>{formatMoney(item.net_amount)}</span>
        </div>
      ))}
    </div>
  );
}

function MarketEmpty({ title, compact = false }: { title: string; compact?: boolean }) {
  return (
    <div className={`market-empty${compact ? " compact" : ""}`}>
      <strong>{title}</strong>
      <span>无可用真实数据或缓存。</span>
    </div>
  );
}

function MarketLoading({ title, compact = false }: { title: string; compact?: boolean }) {
  return (
    <div className={`market-empty market-loading${compact ? " compact" : ""}`}>
      <strong>{title}</strong>
      <span>正在连接免费行情源和本地 SQLite 缓存。</span>
    </div>
  );
}

function marketSourceWarning(
  isError: boolean,
  cacheStatus?: DashboardCacheStatus,
  statuses: DashboardSourceStatus[] = [],
): string {
  if (isError) {
    return "后端 API 暂不可用；请确认 FastAPI 已在 8000 端口运行。";
  }
  if (cacheStatus === "unavailable") {
    return "当前没有可用真实来源或 SQLite 缓存；请确认后端服务、网络连接和免费源状态。";
  }
  if (cacheStatus === "stale") {
    return "部分免费数据源超时，页面正在展示可用真实来源和 SQLite 最近缓存。";
  }
  if (cacheStatus === "partial" || statuses.some((status) => status.status === "unavailable")) {
    return "部分免费数据源暂不可用，页面已保留可用真实来源，不展示模拟数据。";
  }
  return "";
}

function formatTrillion(value: number): string {
  if (Math.abs(value) >= 1000000000000) {
    return `${formatNumber(value / 1000000000000, 2)}万亿`;
  }
  return formatMoney(value);
}

function formatBreadth(activity?: AShareActivity | null): string {
  if (!activity) {
    return "--";
  }
  return `${formatCompact(activity.advances)} / ${formatCompact(activity.declines)}`;
}

function formatSignedPct(value: number): string {
  const sign = value > 0 ? "+" : "";
  return `${sign}${formatNumber(value, 2)}%`;
}

function formatDateTime(value?: string | null): string {
  if (!value) {
    return "--";
  }
  return new Date(value).toLocaleString("zh-CN", { hour12: false });
}

function formatNewsTime(value?: string | null): string {
  if (!value) {
    return "--:--";
  }
  return new Date(value).toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}
