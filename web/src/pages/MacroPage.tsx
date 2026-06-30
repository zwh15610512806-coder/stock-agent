import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import * as echarts from "echarts";
import {
  Activity,
  AlertTriangle,
  BarChart3,
  Compass,
  Gauge,
  GitBranch,
  RefreshCw,
  SlidersHorizontal,
  Thermometer,
} from "lucide-react";
import { SourceStatusBadge } from "../components/SourceStatusBadge";
import { api, apiFailureMessage } from "../lib/api";
import { formatNumber } from "../lib/format";
import type {
  DashboardSourceStatus,
  MacroTimeseriesResponse,
  MacroTimeseriesSeries,
  MacroXrayPoint,
  MacroXrayResponse,
  MacroXrayTarget,
  SourceMetric,
} from "../lib/types";

const DEFAULT_SERIES_IDS = [
  "cn.rate.cn10y",
  "us.rate.us10y",
  "fx.usdcnh",
  "fx.dxy",
  "cn.money.m1_yoy",
  "cn.money.m2_yoy",
  "cn.money.m1_minus_m2_yoy",
  "cn.ppi.yoy",
  "cn.cpi.yoy",
  "cn.pmi.manu",
  "cn.activity.industrial_production_yoy",
  "cn.credit.social_financing_yoy",
  "cn.credit.new_rmb_loans",
  "cn.rates.repo.dr007",
  "cn.market.financing_ratio",
  "cn.market.dividend_yield_all_a",
  "cn.market.turnover_rate_all_a",
  "cn.real_estate.loan_yoy",
  "cn.special_bond.progress",
];

type ChartOption = echarts.EChartsOption;

export function MacroPage() {
  const [targetValue, setTargetValue] = useState("index:000300.SH");
  const [sandboxIds, setSandboxIds] = useState(["cn.money.m1_yoy", "cn.money.m1_minus_m2_yoy", "cn.ppi.yoy"]);
  const target = parseTargetValue(targetValue);

  const dashboard = useQuery({
    queryKey: ["macro-dashboard"],
    queryFn: () => api.macroDashboard(),
  });
  const timeseries = useQuery({
    queryKey: ["macro-timeseries"],
    queryFn: () => api.macroTimeseries({ series_ids: DEFAULT_SERIES_IDS, start: "2006-01-01", max_points: 260 }),
  });
  const targets = useQuery({
    queryKey: ["macro-xray-targets"],
    queryFn: () => api.macroXrayTargets({ universe_type: "all", lookback: 6 }),
  });
  const xray = useQuery({
    queryKey: ["macro-xray", target.universe_type, target.universe_code],
    queryFn: () =>
      api.macroXray({
        universe_type: target.universe_type,
        universe_code: target.universe_code,
        scope: "non_financial",
        period: "latest",
        quarters: 40,
        lookback: 6,
      }),
  });

  const dashboardData = dashboard.data;
  const timeseriesData = timeseries.data;
  const xrayData = xray.data;
  const targetItems = targets.data?.items || fallbackTargets();
  const allStatuses = mergeStatuses([
    ...(dashboardData?.source_status || []),
    ...(timeseriesData?.source_status || []),
    ...(xrayData?.source_status || []),
    ...(targets.data?.source_status || []),
  ]);
  const hasError = dashboard.isError || timeseries.isError || xray.isError || targets.isError;

  return (
    <div className="page-stack macro-page macro-workbench">
      <section className="section-head macro-hero macro-weather-hero">
        <div>
          <div className="eyebrow">MARKET PULSE</div>
          <h2>宏观天气</h2>
          <p>覆盖流动性、通胀、信用、利率、汇率与企业账本代理指标；免费公开源缺失时明确降级，不生成假数据。</p>
        </div>
        <div className="market-hero-actions">
          <span className="market-clock">更新 {formatDateTime(dashboardData?.as_of || timeseriesData?.ts || xrayData?.ts)}</span>
          <SourceStatusBadge status={dashboard.isPending ? "loading" : dashboardData?.cache_status || "unavailable"} />
          <button
            className="terminal-button soft market-refresh"
            onClick={() => {
              dashboard.refetch();
              timeseries.refetch();
              xray.refetch();
              targets.refetch();
            }}
            type="button"
          >
            <RefreshCw size={15} />
            刷新
          </button>
        </div>
      </section>

      {hasError ? (
        <div className="source-warning">{apiFailureMessage(dashboard.error || timeseries.error || xray.error || targets.error, "宏观工作台")}</div>
      ) : null}

      <MacroWeatherStrip dashboard={dashboardData} timeseries={timeseriesData} loading={dashboard.isPending || timeseries.isPending} />

      <section className="data-panel macro-xray-panel">
        <div className="panel-head macro-panel-head">
          <div>
            <h3>
              <GitBranch size={16} />
              企业账本宏观传导链
            </h3>
            <span>{xrayData?.methodology || "公开宏观源近似版，等待 X-Ray 数据返回"}</span>
          </div>
          <label className="macro-target-picker">
            <span>分析标的</span>
            <select aria-label="分析标的" value={targetValue} onChange={(event) => setTargetValue(event.target.value)}>
              {targetItems.map((item) => (
                <option key={item.id} value={`${item.type}:${item.code}`}>
                  {item.name} · {item.type}
                </option>
              ))}
            </select>
          </label>
        </div>
        <LedgerChain latest={xrayData?.latest || null} loading={xray.isPending} />
      </section>

      <section className="macro-chart-grid">
        <MacroChartCard
          title="利润剪刀差"
          subtitle="收入代理与利润代理的差值用于观察利润弹性"
          icon={BarChart3}
          option={xrayLineOption(xrayData, ["revenueYoy", "profitYoy"], ["收入代理", "利润代理"])}
        />
        <MacroChartCard
          title="补库与现金"
          subtitle="库存代理、现金转化代理和 M1-M2 共同判断库存周期"
          icon={Activity}
          option={xrayLineOption(xrayData, ["inventoryYoy", "cashConversionRatio"], ["库存代理", "现金转化"])}
        />
        <MacroChartCard
          title="扩产与产能"
          subtitle="社融和扩产代理反映企业资本开支压力"
          icon={SlidersHorizontal}
          option={xrayLineOption(xrayData, ["capexYoy", "interestDebtYoy"], ["扩产代理", "债务代理"])}
        />
        <CycleCompass latest={xrayData?.latest || null} />
        <ThermoMeter latest={xrayData?.latest || null} />
        <MacroChartCard
          title="趋势图谱"
          subtitle="M1、M1-M2、PPI 与利率的中长期变化"
          icon={Compass}
          option={timeseriesLineOption(timeseriesData, ["cn.money.m1_yoy", "cn.money.m1_minus_m2_yoy", "cn.ppi.yoy", "cn.rate.cn10y"])}
        />
      </section>

      <IndicatorSandbox
        series={timeseriesData?.series || []}
        selectedIds={sandboxIds}
        onChange={setSandboxIds}
        option={timeseriesLineOption(timeseriesData, sandboxIds)}
      />

      <SourcePanel statuses={allStatuses} disclaimer={timeseriesData?.disclaimer || dashboardData?.disclaimer || ""} />
    </div>
  );
}

function MacroWeatherStrip({
  dashboard,
  timeseries,
  loading,
}: {
  dashboard?: { rates: SourceMetric[]; indicators: SourceMetric[]; bond_yields: SourceMetric[]; fx_rates: SourceMetric[] };
  timeseries?: MacroTimeseriesResponse;
  loading: boolean;
}) {
  const pills = [
    metricPill("CN10Y", latestSeries(timeseries, "cn.rate.cn10y"), "%"),
    metricPill("US10Y", latestSeries(timeseries, "us.rate.us10y"), "%"),
    metricPill("M1-M2", latestSeries(timeseries, "cn.money.m1_minus_m2_yoy"), "ppt"),
    metricPill("PPI", latestSeries(timeseries, "cn.ppi.yoy"), "%"),
    metricPill("USDCNH", latestSeries(timeseries, "fx.usdcnh"), ""),
  ];
  const fallback = [...(dashboard?.rates || []), ...(dashboard?.indicators || []), ...(dashboard?.bond_yields || []), ...(dashboard?.fx_rates || [])].slice(0, 4);
  return (
    <section className="macro-weather-strip">
      <div className="macro-alert">
        <AlertTriangle size={16} />
        <span>基于公开免费源构建。房地产贷款、专项债进度、全 A 融资/股息/换手等项首版为代理或待接官方源。</span>
      </div>
      <div className="macro-pill-strip">
        {loading ? <div className="market-empty compact">正在连接宏观公开源</div> : null}
        {!loading && pills.every((pill) => pill.value === null)
          ? fallback.map((item) => (
              <MetricPill key={item.name} label={item.name} value={item.value} unit={item.unit} status={item.status} />
            ))
          : pills.map((pill) => <MetricPill key={pill.label} {...pill} />)}
      </div>
    </section>
  );
}

function MetricPill({ label, value, unit, status }: { label: string; value: number | null; unit: string; status: string }) {
  return (
    <article className={`macro-weather-pill ${status === "unavailable" ? "is-unavailable" : ""}`}>
      <span>{label}</span>
      <strong>{value === null ? "--" : `${formatNumber(value, unit ? 2 : 3)}${unit}`}</strong>
      <small>{status}</small>
    </article>
  );
}

function LedgerChain({ latest, loading }: { latest: MacroXrayPoint | null; loading: boolean }) {
  const items = [
    { label: "收入代理", value: latest?.revenueYoy, unit: "%", detail: "工业增加值同比代理" },
    { label: "利润代理", value: latest?.profitYoy, unit: "%", detail: "收入 + PPI 弹性代理" },
    { label: "库存代理", value: latest?.inventoryYoy, unit: "%", detail: "M2 与 M1-M2 组合代理" },
    { label: "现金转化", value: latest?.cashConversionRatio, unit: "x", detail: "M1-M2 与价格组合" },
    { label: "利润-收入差", value: latest?.profitRevenueGap ?? null, unit: "%", detail: "利润弹性是否领先" },
  ];
  return (
    <div className="macro-ledger-grid">
      {loading ? <div className="market-empty compact">正在计算 X-Ray 代理指标</div> : null}
      {!loading && !latest ? <div className="market-empty compact">暂无可用企业账本代理数据</div> : null}
      {items.map((item, index) => (
        <article className="macro-ledger-node" key={item.label}>
          <small>0{index + 1}</small>
          <span>{item.label}</span>
          <strong>{formatXrayValue(item.value, item.unit)}</strong>
          <em>{item.detail}</em>
        </article>
      ))}
    </div>
  );
}

function MacroChartCard({
  title,
  subtitle,
  icon: Icon,
  option,
}: {
  title: string;
  subtitle: string;
  icon: typeof Activity;
  option: ChartOption;
}) {
  return (
    <section className="data-panel macro-chart-card">
      <div className="panel-head macro-panel-head">
        <div>
          <h3>
            <Icon size={16} />
            {title}
          </h3>
          <span>{subtitle}</span>
        </div>
      </div>
      <EChartHost option={option} ariaLabel={title} />
    </section>
  );
}

function CycleCompass({ latest }: { latest: MacroXrayPoint | null }) {
  const revenue = latest?.revenueYoy ?? 0;
  const profit = latest?.profitYoy ?? 0;
  const x = Math.max(8, Math.min(92, 50 + revenue * 420));
  const y = Math.max(8, Math.min(92, 50 - profit * 420));
  return (
    <section className="data-panel macro-chart-card macro-compass-card">
      <div className="panel-head macro-panel-head">
        <div>
          <h3>
            <Compass size={16} />
            周期罗盘
          </h3>
          <span>横轴收入，纵轴利润，定位当前周期象限</span>
        </div>
      </div>
      <div className="macro-compass-grid">
        <span className="macro-compass-zone top-left">利润承压</span>
        <span className="macro-compass-zone top-right">量升价弱</span>
        <span className="macro-compass-zone bottom-left">收缩出清</span>
        <span className="macro-compass-zone bottom-right">扩张修复</span>
        <i style={{ left: `${x}%`, top: `${y}%` }} />
      </div>
    </section>
  );
}

function ThermoMeter({ latest }: { latest: MacroXrayPoint | null }) {
  const score = macroTemperature(latest);
  return (
    <section className="data-panel macro-chart-card macro-thermo-card">
      <div className="panel-head macro-panel-head">
        <div>
          <h3>
            <Thermometer size={16} />
            温度计
          </h3>
          <span>利润、库存、现金转化的合成温度</span>
        </div>
      </div>
      <div className="macro-thermo">
        <Gauge size={30} />
        <div className="macro-thermo-arc">
          <i style={{ width: `${score}%` }} />
        </div>
        <strong>{score >= 65 ? "偏热" : score >= 35 ? "中性" : "偏冷"}</strong>
        <span>{formatNumber(score, 0)} / 100</span>
      </div>
    </section>
  );
}

function IndicatorSandbox({
  series,
  selectedIds,
  onChange,
  option,
}: {
  series: MacroTimeseriesSeries[];
  selectedIds: string[];
  onChange: (ids: string[]) => void;
  option: ChartOption;
}) {
  const visible = series.slice(0, 10);
  return (
    <section className="data-panel macro-sandbox">
      <div className="panel-head macro-panel-head">
        <div>
          <h3>
            <SlidersHorizontal size={16} />
            指标沙盘
          </h3>
          <span>勾选指标组合，查看公开源趋势是否同向或背离</span>
        </div>
      </div>
      <div className="macro-sandbox-body">
        <div className="macro-sandbox-controls">
          {visible.map((item) => (
            <label key={item.series_id}>
              <input
                checked={selectedIds.includes(item.series_id)}
                type="checkbox"
                onChange={(event) => {
                  if (event.target.checked) {
                    onChange([...selectedIds, item.series_id]);
                  } else {
                    onChange(selectedIds.filter((id) => id !== item.series_id));
                  }
                }}
              />
              <span>{item.name}</span>
              <small>{item.status === "unavailable" ? "待接官方源" : item.unit || item.frequency}</small>
            </label>
          ))}
          {!visible.length ? <div className="market-empty compact">暂无可用指标</div> : null}
        </div>
        <EChartHost option={option} ariaLabel="指标沙盘" />
      </div>
    </section>
  );
}

function SourcePanel({ statuses, disclaimer }: { statuses: DashboardSourceStatus[]; disclaimer: string }) {
  return (
    <section className="data-panel macro-source-panel">
      <div className="panel-head macro-panel-head">
        <div>
          <h3>数据源状态</h3>
          <span>{disclaimer || "免费公开源可能延迟、缺失或被缓存"}</span>
        </div>
      </div>
      <div className="quote-list">
        {statuses.map((status) => (
          <div className="quote-row" key={`${status.name}-${status.source}`}>
            <div>
              <strong>{status.name}</strong>
              <span>{status.detail || status.source}</span>
            </div>
            <div className="quote-price">
              <strong>{status.status}</strong>
              <span>{formatDateTime(status.as_of)}</span>
            </div>
          </div>
        ))}
        {!statuses.length ? <div className="market-empty compact">暂无真实宏观数据源状态</div> : null}
      </div>
    </section>
  );
}

function EChartHost({ option, ariaLabel }: { option: ChartOption; ariaLabel: string }) {
  const ref = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (!ref.current) {
      return;
    }
    const chart = echarts.init(ref.current);
    chart.setOption(option);
    const handleResize = () => chart.resize();
    window.addEventListener("resize", handleResize);
    return () => {
      window.removeEventListener("resize", handleResize);
      chart.dispose();
    };
  }, [option]);
  return <div className="macro-chart-host" ref={ref} role="img" aria-label={ariaLabel} />;
}

function xrayLineOption(data: MacroXrayResponse | undefined, fields: Array<keyof MacroXrayPoint>, labels: string[]): ChartOption {
  const points = data?.points || [];
  const xData = points.map((point) => point.period);
  return baseLineOption(
    xData,
    fields.map((field, index) => ({
      name: labels[index],
      type: "line",
      smooth: true,
      symbolSize: 5,
      data: points.map((point) => metricForChart(point[field])),
    })),
  );
}

function timeseriesLineOption(data: MacroTimeseriesResponse | undefined, ids: string[]): ChartOption {
  const selected = ids.map((id) => data?.series.find((item) => item.series_id === id)).filter(Boolean) as MacroTimeseriesSeries[];
  const dates = Array.from(new Set(selected.flatMap((item) => item.points.map((point) => point.date)))).sort();
  return baseLineOption(
    dates,
    selected.map((item) => {
      const valueByDate = new Map(item.points.map((point) => [point.date, point.value]));
      return {
        name: item.name,
        type: "line",
        smooth: true,
        symbolSize: 4,
        data: dates.map((date) => valueByDate.get(date) ?? null),
      };
    }),
  );
}

function baseLineOption(xData: string[], series: ChartOption["series"]): ChartOption {
  return {
    animationDuration: 360,
    color: ["#e24a3b", "#078764", "#2f7ecb", "#f3a21b", "#64748b"],
    grid: { top: 24, right: 14, bottom: 30, left: 42 },
    tooltip: { trigger: "axis" },
    legend: { top: 0, right: 0, itemWidth: 10, itemHeight: 6, textStyle: { color: "#486079", fontSize: 11 } },
    xAxis: {
      type: "category",
      data: xData,
      boundaryGap: false,
      axisLabel: { color: "#6b7f93", fontSize: 10 },
      axisLine: { lineStyle: { color: "#dfe7ef" } },
    },
    yAxis: {
      type: "value",
      axisLabel: { color: "#6b7f93", fontSize: 10 },
      splitLine: { lineStyle: { color: "#e8eef4", type: "dashed" } },
    },
    series,
  };
}

function metricPill(label: string, series: MacroTimeseriesSeries | undefined, fallbackUnit: string) {
  const latest = latestPoint(series);
  return {
    label,
    value: latest?.value ?? null,
    unit: series?.unit || fallbackUnit,
    status: series?.status || "unavailable",
  };
}

function latestSeries(data: MacroTimeseriesResponse | undefined, id: string): MacroTimeseriesSeries | undefined {
  return data?.series.find((item) => item.series_id === id);
}

function latestPoint(series: MacroTimeseriesSeries | undefined) {
  return series?.points[series.points.length - 1];
}

function formatXrayValue(value: number | null | undefined, unit: string): string {
  if (value === null || value === undefined) {
    return "--";
  }
  if (unit === "%") {
    return `${formatNumber(value * 100, 1)}%`;
  }
  if (unit === "x") {
    return `${formatNumber(value, 2)}x`;
  }
  return formatNumber(value, 2);
}

function metricForChart(value: unknown): number | null {
  if (typeof value !== "number") {
    return null;
  }
  return Math.abs(value) <= 2 ? Number((value * 100).toFixed(4)) : value;
}

function macroTemperature(latest: MacroXrayPoint | null): number {
  if (!latest) {
    return 0;
  }
  const profit = latest.profitYoy ?? 0;
  const inventory = latest.inventoryYoy ?? 0;
  const cash = latest.cashConversionRatio ?? 0.75;
  const score = 50 + profit * 280 - inventory * 120 + (cash - 0.8) * 45;
  return Math.max(0, Math.min(100, Math.round(score)));
}

function parseTargetValue(value: string): { universe_type: string; universe_code: string } {
  const [type, ...rest] = value.split(":");
  return {
    universe_type: type || "index",
    universe_code: rest.join(":") || "000300.SH",
  };
}

function fallbackTargets(): MacroXrayTarget[] {
  return [{ id: "index:000300.SH", type: "index", code: "000300.SH", name: "沪深300", source: "static", status: "live" }];
}

function mergeStatuses(statuses: DashboardSourceStatus[]): DashboardSourceStatus[] {
  const byKey = new Map<string, DashboardSourceStatus>();
  statuses.forEach((status) => {
    byKey.set(`${status.name}:${status.source}`, status);
  });
  return Array.from(byKey.values());
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) {
    return "--";
  }
  return new Date(value).toLocaleString("zh-CN", { hour12: false });
}
