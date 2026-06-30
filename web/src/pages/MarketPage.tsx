import { useMemo, useState } from "react";
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
import { Heatmap, type HeatmapAreaMetric } from "../components/Heatmap";
import { SourceStatusBadge } from "../components/SourceStatusBadge";
import { api } from "../lib/api";
import { formatCompact, formatMoney, formatNumber, toneForPct } from "../lib/format";
import type {
  AShareActivity,
  CommodityQuote,
  DragonTigerItem,
  DashboardCacheStatus,
  DashboardHeatItem,
  FundFlowSummary,
  MarketNewsItem,
  QuoteSnapshot,
} from "../lib/types";

type HeatmapGroupKey = "etf" | "industry" | "sector" | "concept" | "region";
type DragonTigerSortKey = "net_inflow" | "net_outflow" | "rise_pct" | "fall_pct" | "turnover";

const HEATMAP_GROUP_ORDER: HeatmapGroupKey[] = ["etf", "industry", "sector", "region", "concept"];

const HEATMAP_TABS: Array<{ label: string; group: HeatmapGroupKey }> = [
  { label: "ETF", group: "etf" },
  { label: "大类行业", group: "industry" },
  { label: "细分行业", group: "sector" },
  { label: "地域", group: "region" },
  { label: "概念", group: "concept" },
];

const HEATMAP_GROUP_LABELS: Record<HeatmapGroupKey, string> = {
  etf: "ETF",
  industry: "大类行业",
  sector: "细分行业",
  concept: "概念",
  region: "地域",
};

const HEATMAP_METRIC_OPTIONS: Array<{ value: HeatmapAreaMetric; label: string }> = [
  { value: "turnover", label: "成交额" },
  { value: "net_amount", label: "净流入" },
  { value: "change_pct", label: "涨跌幅" },
];

const HEATMAP_LIMIT_OPTIONS = [30, 60, 120];

const DRAGON_TIGER_SORT_OPTIONS: Array<{ value: DragonTigerSortKey; label: string }> = [
  { value: "net_inflow", label: "净流入" },
  { value: "net_outflow", label: "净流出" },
  { value: "rise_pct", label: "上涨%" },
  { value: "fall_pct", label: "下跌%" },
  { value: "turnover", label: "成交额" },
];

export function MarketPage() {
  const [heatmapGroup, setHeatmapGroup] = useState<HeatmapGroupKey>("industry");
  const [heatmapMetric, setHeatmapMetric] = useState<HeatmapAreaMetric>("turnover");
  const [heatmapLimit, setHeatmapLimit] = useState(60);
  const dashboard = useQuery({
    queryKey: ["market-dashboard", "reference-overview"],
    queryFn: () => api.marketDashboard(["CN", "HK", "US"], "daily"),
  });
  const data = dashboard.data;
  const isInitialLoading = dashboard.isPending && !data;
  const indexQuotes = data?.markets.flatMap((market) => market.indices) || [];
  const aShare = data?.markets.find((market) => market.market === "CN");
  const aShareTurnover = data?.a_share_turnover;
  const heatmapBuckets = useMemo<Record<HeatmapGroupKey, DashboardHeatItem[]>>(
    () => ({
      etf: data?.etf_heatmap || [],
      industry: data?.industry_heatmap || [],
      sector: data?.sector_heatmap || [],
      concept: data?.concept_heatmap || [],
      region: data?.region_heatmap || [],
    }),
    [data?.concept_heatmap, data?.etf_heatmap, data?.industry_heatmap, data?.region_heatmap, data?.sector_heatmap],
  );
  const activeHeatmapGroup =
    heatmapBuckets[heatmapGroup].length > 0
      ? heatmapGroup
      : HEATMAP_GROUP_ORDER.find((group) => heatmapBuckets[group].length > 0) || heatmapGroup;
  const activeHeatmapData = heatmapBuckets[activeHeatmapGroup];
  const selectedHeatmapData = useMemo(
    () =>
      [...activeHeatmapData]
        .sort((left, right) => heatmapSortValue(right, heatmapMetric) - heatmapSortValue(left, heatmapMetric))
        .slice(0, heatmapLimit),
    [activeHeatmapData, heatmapLimit, heatmapMetric],
  );
  const sourceWarning = isInitialLoading
    ? ""
    : marketSourceWarning(dashboard.isError, data?.cache_status);

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
        <div className="heatmap-board-head">
          <div className="heatmap-title-copy">
            <div>
              <Flame size={16} />
              <h3>板块热力图</h3>
            </div>
            <span>
              {HEATMAP_GROUP_LABELS[activeHeatmapGroup]} · 盘中聚合 {formatShortDate(data?.as_of)}
            </span>
          </div>
          <div className="heatmap-controls" aria-label="板块热力图控制">
            <select
              aria-label="热力图面积指标"
              className="heatmap-select"
              value={heatmapMetric}
              onChange={(event) => setHeatmapMetric(event.target.value as HeatmapAreaMetric)}
            >
              {HEATMAP_METRIC_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <select
              aria-label="热力图显示数量"
              className="heatmap-select compact"
              value={heatmapLimit}
              onChange={(event) => setHeatmapLimit(Number(event.target.value))}
            >
              {HEATMAP_LIMIT_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  显示 {option}
                </option>
              ))}
            </select>
            <div className="heatmap-tabs" role="tablist" aria-label="板块分类">
              {HEATMAP_TABS.map((tab) => {
                const enabled = heatmapBuckets[tab.group].length > 0;
                const active = tab.group === activeHeatmapGroup;
                return (
                  <button
                    aria-selected={active}
                    className={active ? "active" : ""}
                    disabled={!enabled}
                    key={tab.label}
                    onClick={() => setHeatmapGroup(tab.group)}
                    role="tab"
                    type="button"
                  >
                    {tab.label}
                  </button>
                );
              })}
            </div>
          </div>
        </div>
        {isInitialLoading ? (
          <MarketLoading title="正在加载板块热力" />
        ) : selectedHeatmapData.length ? (
          <>
            <Heatmap data={selectedHeatmapData} areaMetric={heatmapMetric} displayLimit={heatmapLimit} />
            <div className="heatmap-count">
              已显示 {selectedHeatmapData.length}（共 {activeHeatmapData.length}）
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
          <SectionTitle icon={Trophy} title="龙虎榜" subtitle="最近交易日多指标排行" />
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
  const sortedNews = [...news].sort((left, right) => {
    const leftTime = parseNewsDate(left.published_at)?.getTime() || 0;
    const rightTime = parseNewsDate(right.published_at)?.getTime() || 0;
    return rightTime - leftTime;
  });
  const latest = parseNewsDate(sortedNews[0]?.published_at) || new Date();
  const start = new Date(latest.getTime() - 24 * 60 * 60 * 1000);
  return (
    <div className="news-live-panel">
      <div className="news-live-meta">
        <span>近24小时</span>
        <span>已加载 {sortedNews.length} 条</span>
      </div>
      <NewsTimeAxis start={start} end={latest} latest={latest} />
      <div className="news-timeline">
        {sortedNews.slice(0, 12).map((item) => (
          <a href={item.url || undefined} key={`${item.published_at}-${item.title}-${item.url}`} target={item.url ? "_blank" : undefined} rel="noreferrer">
            <time>{formatNewsTime(item.published_at)}</time>
            <span className="news-source-pill">{item.source}</span>
            <strong>{item.title}</strong>
            <span>{item.content || item.source}</span>
          </a>
        ))}
      </div>
    </div>
  );
}

function NewsTimeAxis({ start, end, latest }: { start: Date; end: Date; latest: Date }) {
  const ticks = buildTimelineTicks(start, end);
  return (
    <div className="news-axis" aria-label="近24小时快讯时间轴">
      <div className="news-axis-head">
        <span>{formatAxisDate(start)}</span>
        <span>{formatAxisDate(end)}</span>
      </div>
      <div className="news-axis-track">
        <span className="news-axis-fill" />
        <span className="news-axis-latest" style={{ left: `${newsPositionPct(latest, start, end)}%` }}>
          最新资讯
        </span>
      </div>
      <div className="news-axis-ticks">
        {ticks.map((tick) => (
          <span key={tick.toISOString()}>{formatAxisTime(tick)}</span>
        ))}
      </div>
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
  const [sortKey, setSortKey] = useState<DragonTigerSortKey>("net_inflow");
  const rows = useMemo(() => sortDragonTigerItems(items, sortKey).slice(0, 10), [items, sortKey]);

  if (!items.length) {
    return <MarketEmpty title="暂无真实龙虎榜" />;
  }
  return (
    <div className="dragon-panel">
      <div className="dragon-tabs" aria-label="龙虎榜排序">
        {DRAGON_TIGER_SORT_OPTIONS.map((option) => (
          <button
            aria-pressed={sortKey === option.value}
            className={sortKey === option.value ? "active" : ""}
            key={option.value}
            onClick={() => setSortKey(option.value)}
            type="button"
          >
            {option.label}
          </button>
        ))}
      </div>
      {rows.length ? (
        <div className="dragon-list">
          {rows.map((item, index) => {
            const changeTone = toneForPct(item.change_pct);
            const netTone = item.net_amount >= 0 ? "tone-red" : "tone-green";
            return (
              <div className="dragon-row" data-testid="dragon-row" key={`${item.trade_date}-${item.symbol}-${index}`}>
                <span className="rank-number">{index + 1}</span>
                <div className="dragon-main">
                  <div className="dragon-title-row">
                    <strong>{item.name}</strong>
                    <span className="dragon-tag">{item.market_segment || "--"}</span>
                    <span className="dragon-tag">{item.sector || "--"}</span>
                  </div>
                  <span>{item.symbol} · {item.reason || item.trade_date}</span>
                </div>
                <div className="dragon-metrics">
                  <div className={`dragon-metric ${sortKey === "rise_pct" || sortKey === "fall_pct" ? "active" : ""}`}>
                    <span>收盘/涨跌</span>
                    <strong>{formatNumber(item.close, 2)}</strong>
                    <small className={`tone-text ${changeTone}`}>{formatSignedPct(item.change_pct)}</small>
                  </div>
                  <div className={`dragon-metric ${sortKey === "net_inflow" || sortKey === "net_outflow" ? "active" : ""}`}>
                    <span>净买额</span>
                    <strong className={netTone}>{formatMoney(item.net_amount)}</strong>
                  </div>
                  <div className={`dragon-metric ${sortKey === "turnover" ? "active" : ""}`}>
                    <span>成交额</span>
                    <strong>{formatDragonTurnover(item.turnover)}</strong>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <MarketEmpty title="当前排序暂无真实龙虎榜" compact />
      )}
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
  if (cacheStatus === "partial") {
    return "部分免费数据源暂不可用，页面已保留可用真实来源，不展示模拟数据。";
  }
  return "";
}

function heatmapSortValue(item: DashboardHeatItem, metric: HeatmapAreaMetric): number {
  if (metric === "net_amount") {
    return Math.abs(item.net_amount || 0);
  }
  if (metric === "change_pct") {
    return Math.abs(item.change_pct || 0);
  }
  return item.turnover || 0;
}

function sortDragonTigerItems(items: DragonTigerItem[], sortKey: DragonTigerSortKey): DragonTigerItem[] {
  const filtered = items.filter((item) => {
    if (sortKey === "rise_pct") {
      return item.change_pct > 0;
    }
    if (sortKey === "fall_pct") {
      return item.change_pct < 0;
    }
    return true;
  });

  return [...filtered].sort((left, right) => {
    if (sortKey === "net_outflow") {
      return left.net_amount - right.net_amount || right.turnover - left.turnover;
    }
    if (sortKey === "rise_pct") {
      return right.change_pct - left.change_pct || right.net_amount - left.net_amount;
    }
    if (sortKey === "fall_pct") {
      return left.change_pct - right.change_pct || left.net_amount - right.net_amount;
    }
    if (sortKey === "turnover") {
      return dragonTurnoverSortValue(right) - dragonTurnoverSortValue(left) || right.net_amount - left.net_amount;
    }
    return right.net_amount - left.net_amount || right.turnover - left.turnover;
  });
}

function dragonTurnoverSortValue(item: DragonTigerItem): number {
  return item.turnover > 0 ? item.turnover : Number.NEGATIVE_INFINITY;
}

function formatDragonTurnover(value: number): string {
  return value > 0 ? formatMoney(value) : "--";
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

function formatShortDate(value?: string | null): string {
  if (!value) {
    return "--";
  }
  return new Date(value).toLocaleDateString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    year: "numeric",
  });
}

function formatNewsTime(value?: string | null): string {
  const parsed = parseNewsDate(value);
  if (!parsed) {
    return "--:--";
  }
  return parsed.toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

function parseNewsDate(value?: string | null): Date | null {
  if (!value) {
    return null;
  }
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function buildTimelineTicks(start: Date, end: Date): Date[] {
  const ticks: Date[] = [];
  const step = (end.getTime() - start.getTime()) / 6;
  for (let index = 1; index < 6; index += 1) {
    ticks.push(new Date(start.getTime() + step * index));
  }
  return ticks;
}

function newsPositionPct(value: Date, start: Date, end: Date): number {
  const total = Math.max(1, end.getTime() - start.getTime());
  return Math.max(0, Math.min(100, ((value.getTime() - start.getTime()) / total) * 100));
}

function formatAxisDate(value: Date): string {
  return value.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

function formatAxisTime(value: Date): string {
  return value.toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}
