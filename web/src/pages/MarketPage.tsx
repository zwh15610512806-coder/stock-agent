import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronRight, RefreshCw } from "lucide-react";
import { CandleChart } from "../components/CandleChart";
import { DashboardMetricCard } from "../components/DashboardMetricCard";
import { EmptyState } from "../components/EmptyState";
import { FundFlowList } from "../components/FundFlowList";
import { Heatmap } from "../components/Heatmap";
import { SentimentGauge } from "../components/SentimentGauge";
import { SourceStatusBadge } from "../components/SourceStatusBadge";
import { api } from "../lib/api";
import { formatCompact, formatMoney, formatNumber, toneForPct } from "../lib/format";
import type { DashboardCacheStatus, DashboardHeatItem, DashboardSourceStatus } from "../lib/types";

type KlinePeriod = "daily" | "weekly" | "monthly";
type PeriodOption = { label: string; value: KlinePeriod | "intraday"; disabled?: boolean };

const periodOptions: PeriodOption[] = [
  { label: "分时", value: "intraday", disabled: true },
  { label: "日K", value: "daily" },
  { label: "周K", value: "weekly" },
  { label: "月K", value: "monthly" },
];

export function MarketPage() {
  const [period, setPeriod] = useState<KlinePeriod>("daily");
  const dashboard = useQuery({
    queryKey: ["market-dashboard", period],
    queryFn: () => api.marketDashboard(["CN", "HK", "US"], period),
  });
  const data = dashboard.data;
  const primaryQuote = data?.primary_quote;
  const activity = data?.a_share_activity;

  return (
    <div className="market-dashboard">
      <section className="dashboard-heading">
        <div>
          <h2>大盘趋势</h2>
          <p>查看大盘走势，把握市场节奏、洞察资金动向，辅助投资决策。</p>
        </div>
        <div className="heading-status">
          <SourceStatusBadge status={data?.cache_status || "unavailable"} />
          <button className="terminal-button soft" onClick={() => dashboard.refetch()}>
            <RefreshCw size={16} />
            刷新
          </button>
        </div>
      </section>

      {dashboard.isError ? (
        <EmptyState title="行情加载失败" body="请确认后端 API 已启动，或稍后重试。不会展示样例行情作为真实数据。" />
      ) : null}

      {data?.source_status.some((status) => status.status === "unavailable") ? (
        <div className="source-warning">数据源暂不可用，页面仅展示其它真实源或 SQLite 最近成功缓存。</div>
      ) : null}

      <div className="dashboard-main-grid">
        <section className="dashboard-panel chart-panel">
          <div className="panel-head dashboard-panel-head">
            <div>
              <h3>上证指数走势</h3>
              <span>
                {primaryQuote?.as_of ? new Date(primaryQuote.as_of).toLocaleString("zh-CN") : "等待真实行情"}
                {primaryQuote ? `　收 ${formatNumber(primaryQuote.price, 2)}` : ""}
                {primaryQuote ? `　涨跌 ${formatNumber(primaryQuote.change, 2)} (${formatNumber(primaryQuote.change_pct, 2)}%)` : ""}
              </span>
            </div>
            <div className="period-tabs">
              {periodOptions.map((item) => (
                <button
                  key={item.value}
                  disabled={item.disabled}
                  className={period === item.value ? "active" : ""}
                  onClick={() => {
                    if (!item.disabled && item.value !== "intraday") {
                      setPeriod(item.value);
                    }
                  }}
                  type="button"
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>
          <div className="moving-average-row">
            <span>MA5: 真实源暂未提供</span>
            <span>MA10: 真实源暂未提供</span>
            <span>MA20: 真实源暂未提供</span>
          </div>
          {data?.primary_candles.length ? <CandleChart candles={data.primary_candles} /> : <div className="chart-skeleton" />}
          <div className="chart-footnote">分时数据暂未接入免费真实源；首版支持日K、周K、月K。</div>
        </section>

        <section className="dashboard-panel sentiment-panel">
          <div className="panel-head dashboard-panel-head">
            <div>
              <h3>市场情绪</h3>
              <span>综合资金流、赚钱效应、涨跌市场氛围</span>
            </div>
          </div>
          <SentimentGauge activity={activity || null} />
        </section>
      </div>

      <div className="dashboard-metric-grid">
        <DashboardMetricCard title="A股概览" value={activity ? `${formatNumber(activity.sentiment, 1)}` : "--"} detail="赚钱效应活跃度" accent="blue">
          <div className="mini-stat-grid">
            <span>涨 {activity?.advances ?? "--"}</span>
            <span>跌 {activity?.declines ?? "--"}</span>
            <span>平 {activity?.unchanged ?? "--"}</span>
          </div>
        </DashboardMetricCard>

        {data?.markets.flatMap((market) =>
          market.indices.slice(0, market.market === "CN" ? 3 : 2).map((quote) => (
            <DashboardMetricCard
              key={quote.symbol}
              title={quote.name}
              value={formatNumber(quote.price, 2)}
              detail={`${formatNumber(quote.change, 2)}　${formatNumber(quote.change_pct, 2)}%`}
              accent={quote.change_pct >= 0 ? "red" : "green"}
            />
          )),
        )}

        <section className="dashboard-panel compact-list-panel">
          <div className="panel-head dashboard-panel-head">
            <div>
              <h3>资金流向</h3>
              <span>同花顺个股资金流真实源</span>
            </div>
          </div>
          <FundFlowList summary={data?.fund_flow_summary || null} />
        </section>
      </div>

      <div className="dashboard-heatmap-grid">
        <DashboardHeatmapPanel title="行业涨跌热力图（申万一级）" actionLabel="更多行业" data={data?.industry_heatmap || []} />
        <DashboardHeatmapPanel title="概念涨跌热力图" actionLabel="更多概念" data={data?.concept_heatmap || []} />
        <DashboardHeatmapPanel title="地域涨跌热力图" actionLabel="更多地区" data={data?.region_heatmap || []} />
      </div>

      <section className="dashboard-panel source-panel">
        <div className="panel-head dashboard-panel-head">
          <div>
            <h3>数据源状态</h3>
            <span>{data?.disclaimer || "严格真实模式：无真实源或缓存时不展示样例数据。"}</span>
          </div>
        </div>
        <div className="source-status-grid">
          {(data?.source_status || []).map((status) => (
            <SourceStatusRow key={`${status.name}-${status.source}`} status={status} />
          ))}
        </div>
      </section>
    </div>
  );
}

function DashboardHeatmapPanel({
  title,
  actionLabel,
  data,
}: {
  title: string;
  actionLabel: string;
  data: DashboardHeatItem[];
}) {
  return (
    <section className="dashboard-panel heatmap-panel">
      <div className="panel-head dashboard-panel-head">
        <div>
          <h3>{title}</h3>
          <span>按真实资金流和涨跌幅排序</span>
        </div>
        <button type="button" className="panel-link">
          {actionLabel}
          <ChevronRight size={15} />
        </button>
      </div>
      {data.length ? (
        <>
          <Heatmap data={data} />
          <div className="heatmap-strip">
            {data.slice(0, 4).map((item) => (
              <span key={item.name} className={`tone-text ${toneForPct(item.change_pct)}`}>
                {item.name} {formatNumber(item.change_pct, 2)}% / {formatMoney(item.net_amount)}
              </span>
            ))}
          </div>
        </>
      ) : (
        <div className="dashboard-empty">
          <strong>暂无真实数据</strong>
          <span>该模块无可用真实数据或 SQLite 缓存。</span>
        </div>
      )}
    </section>
  );
}

function SourceStatusRow({ status }: { status: DashboardSourceStatus }) {
  return (
    <div className="source-status-row">
      <div>
        <strong>{status.name}</strong>
        <span>{status.source}</span>
      </div>
      <div>
        <SourceStatusBadge status={status.status} />
        {status.as_of ? <span>{new Date(status.as_of).toLocaleString("zh-CN")}</span> : null}
      </div>
    </div>
  );
}
