import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import * as echarts from "echarts";
import {
  Activity,
  AlertTriangle,
  BarChart3,
  Compass,
  Database,
  Gauge,
  GitBranch,
  Layers,
  LineChart,
  RefreshCw,
  SlidersHorizontal,
  Thermometer,
  type LucideIcon,
} from "lucide-react";
import { SourceStatusBadge } from "../components/SourceStatusBadge";
import { api, apiFailureMessage } from "../lib/api";
import { formatNumber } from "../lib/format";
import type {
  DashboardCacheStatus,
  DashboardSourceStatus,
  MacroTimeseriesResponse,
  MacroTimeseriesSeries,
  MacroXrayPoint,
  MacroXrayResponse,
  MacroXrayTarget,
  SourceMetric,
} from "../lib/types";

const XRAY_LABEL = "X-Ray（企业账本透视）";
const RANGES = [6, 16, 24, 32, 40];

const DEFAULT_SERIES_IDS = [
  "cn.rate.cn10y",
  "us.rate.us10y",
  "fx.usdcnh",
  "fx.dxy",
  "us.vix",
  "cn.money.m1_yoy",
  "cn.money.m2_yoy",
  "cn.money.m1_minus_m2_yoy",
  "cn.ppi.yoy",
  "cn.cpi.yoy",
  "cn.pmi.manu",
  "cn.activity.industrial_production_yoy",
  "cn.gdp.deflator_yoy",
  "cn.rates.repo.dr007",
  "cn.credit.social_financing_yoy",
  "cn.credit.mortgage_long_term_new",
  "cn.credit.real_estate_loans_balance_yoy",
  "cn.fiscal.gov_bond_net",
  "cn.fiscal.special_bond_progress_pct",
  "cn.market.financing_ratio",
  "cn.market.financing_balance",
  "cn.market.dividend_yield_all_a",
  "cn.market.turnover_rate_all_a",
  "cn.flow.hsgt.north_money_cum",
  "cn.house.price_70_city_mom",
  "cn.house.price_70_city_mom.tier1",
  "cn.house.price_70_city_mom.strong_tier2",
];

const SERIES_LABELS: Record<string, string> = {
  "cn.rate.cn10y": "CN10Y（中国10年期国债收益率）",
  "us.rate.us10y": "US10Y（美国10年期国债收益率）",
  "fx.usdcnh": "USD/CNH（美元兑离岸人民币）",
  "fx.dxy": "DXY（美元指数）",
  "us.vix": "VIX（标普500波动率指数）",
  "cn.money.m1_yoy": "M1（狭义货币）同比",
  "cn.money.m2_yoy": "M2（广义货币）同比",
  "cn.money.m1_minus_m2_yoy": "M1-M2（狭义货币-广义货币同比差）",
  "cn.ppi.yoy": "PPI（工业品出厂价格指数）",
  "cn.cpi.yoy": "CPI（居民消费价格指数）",
  "cn.pmi.manu": "PMI（制造业采购经理指数）",
  "cn.activity.industrial_production_yoy": "工业增加值同比",
  "cn.gdp.deflator_yoy": "GDP平减指数",
  "cn.rates.repo.dr007": "DR007（银行间7天回购利率）",
  "cn.credit.social_financing_yoy": "社会融资存量同比",
  "cn.credit.mortgage_long_term_new": "居民中长期贷款",
  "cn.credit.real_estate_loans_balance_yoy": "房地产贷款余额同比",
  "cn.fiscal.gov_bond_net": "政府债净融资",
  "cn.fiscal.special_bond_progress_pct": "专项债发行进度",
  "cn.market.financing_ratio": "融资比例",
  "cn.market.financing_balance": "融资余额",
  "cn.market.dividend_yield_all_a": "全A股息率",
  "cn.market.turnover_rate_all_a": "全A换手率",
  "cn.flow.hsgt.north_money_cum": "北向资金累计",
  "cn.house.price_70_city_mom": "70城房价环比",
  "cn.house.price_70_city_mom.tier1": "一线城市房价环比",
  "cn.house.price_70_city_mom.strong_tier2": "强二线房价环比",
};

const NAME_LABELS: Record<string, string> = {
  "China 10Y": SERIES_LABELS["cn.rate.cn10y"],
  CN10Y: SERIES_LABELS["cn.rate.cn10y"],
  "US 10Y": SERIES_LABELS["us.rate.us10y"],
  US10Y: SERIES_LABELS["us.rate.us10y"],
  USDCNH: SERIES_LABELS["fx.usdcnh"],
  "USD/CNH": SERIES_LABELS["fx.usdcnh"],
  DXY: SERIES_LABELS["fx.dxy"],
  VIX: SERIES_LABELS["us.vix"],
  PPI: SERIES_LABELS["cn.ppi.yoy"],
  "PPI YoY": SERIES_LABELS["cn.ppi.yoy"],
  CPI: SERIES_LABELS["cn.cpi.yoy"],
  PMI: SERIES_LABELS["cn.pmi.manu"],
  DR007: SERIES_LABELS["cn.rates.repo.dr007"],
  "M1 YoY": SERIES_LABELS["cn.money.m1_yoy"],
  "M2 YoY": SERIES_LABELS["cn.money.m2_yoy"],
  "M1-M2": SERIES_LABELS["cn.money.m1_minus_m2_yoy"],
  "M1-M2 YoY Spread": SERIES_LABELS["cn.money.m1_minus_m2_yoy"],
};

const SOURCE_LABELS: Record<string, string> = {
  akshare: "AkShare（公开财经数据接口）",
  danginvest: "DangInvest（公开可访问接口）",
  derived: "派生指标",
  static: "静态配置",
  unavailable: "待接官方源",
  "public-macro-proxy": "公开宏观代理口径",
  public_macro_proxy: "公开宏观代理口径",
};

const PRESETS = [
  { id: "external_pressure", label: "外部压力", ids: ["fx.usdcnh", "fx.dxy", "cn.rate.cn10y", "us.rate.us10y"] },
  { id: "property", label: "地产脉冲", ids: ["cn.house.price_70_city_mom", "cn.credit.real_estate_loans_balance_yoy"] },
  { id: "liquidity", label: "流动性", ids: ["cn.money.m1_yoy", "cn.money.m2_yoy", "cn.rates.repo.dr007"] },
  { id: "growth", label: "增长稀释", ids: ["cn.activity.industrial_production_yoy", "cn.ppi.yoy", "cn.gdp.deflator_yoy"] },
  { id: "sentiment", label: "市场情绪", ids: ["cn.market.financing_ratio", "cn.market.turnover_rate_all_a", "cn.flow.hsgt.north_money_cum"] },
];

type ChartOption = echarts.EChartsOption;

export function MacroPage() {
  const [targetValue, setTargetValue] = useState("index:000300.SH");
  const [targetType, setTargetType] = useState("index");
  const [scope, setScope] = useState("non_financial");
  const [periodWindow, setPeriodWindow] = useState(16);
  const [sandboxIds, setSandboxIds] = useState(["cn.money.m1_yoy", "cn.money.m1_minus_m2_yoy", "cn.ppi.yoy"]);
  const target = parseTargetValue(targetValue);

  const dashboard = useQuery({
    queryKey: ["macro-dashboard"],
    queryFn: () => api.macroDashboard(),
  });
  const timeseries = useQuery({
    queryKey: ["macro-timeseries"],
    queryFn: () => api.macroTimeseries({ series_ids: DEFAULT_SERIES_IDS, start: "2006-01-01", max_points: 2000 }),
  });
  const targets = useQuery({
    queryKey: ["macro-xray-targets", targetType],
    queryFn: () => api.macroXrayTargets({ universe_type: targetType, lookback: 6, target_source: "stock_basic_full_v1" }),
  });
  const xray = useQuery({
    queryKey: ["macro-xray", target.universe_type, target.universe_code, scope],
    queryFn: () =>
      api.macroXray({
        universe_type: target.universe_type,
        universe_code: target.universe_code,
        scope,
        period: "latest",
        quarters: 40,
        lookback: 6,
      }),
  });

  const dashboardData = dashboard.data;
  const timeseriesData = timeseries.data;
  const xrayData = xray.data;
  const seriesMap = useMemo(() => mapSeries(timeseriesData), [timeseriesData]);
  const targetItems = normalizeTargets(targets.data).length ? normalizeTargets(targets.data) : fallbackTargets();
  const allStatuses = mergeStatuses([
    ...(dashboardData?.source_status || []),
    ...(timeseriesData?.source_status || []),
    ...(xrayData?.source_status || []),
    ...(targets.data?.source_status || []),
  ]);
  const hasError = dashboard.isError || timeseries.isError || xray.isError || targets.isError;
  const cacheStatus = dashboard.isPending ? "loading" : dashboardData?.cache_status || "unavailable";
  const latest = xrayData?.latest || null;

  return (
    <div className="page-stack macro-page macro-workbench macro-danglike">
      <section className="section-head macro-hero macro-weather-hero">
        <div>
          <div className="eyebrow">MARKET PULSE（市场脉冲）</div>
          <h2>宏观天气</h2>
          <p>基于宏观公开源与 {XRAY_LABEL} 混合适配层，观察流动性、通胀、信用、利率、汇率与企业账本传导。</p>
        </div>
        <div className="market-hero-actions">
          <span className="market-clock">更新 {formatDateTime(dashboardData?.as_of || timeseriesData?.ts || xrayData?.ts)}</span>
          <SourceStatusBadge status={cacheStatus as DashboardCacheStatus | "loading"} label={statusLabel(cacheStatus)} />
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

      <section className="data-panel macro-xray-panel macro-chain-panel">
        <div className="panel-head macro-panel-head">
          <div>
            <h3>
              <GitBranch size={16} />
              企业账本宏观传导链
            </h3>
            <span>
              <b>{XRAY_LABEL}</b> · {displayMethodology(xrayData?.methodology)}
            </span>
          </div>
          <div className="macro-xray-controls">
            <div className="macro-segmented" aria-label="标的类型">
              {[
                ["index", "宽基指数"],
                ["industry", "个股行业"],
                ["etf", "行业 ETF"],
              ].map(([value, label]) => (
                <button
                  className={targetType === value ? "active" : ""}
                  key={value}
                  type="button"
                  onClick={() => {
                    setTargetType(value);
                    const fallback = fallbackTargets().find((item) => item.type === value) || fallbackTargets()[0];
                    setTargetValue(`${fallback.type}:${fallback.code}`);
                  }}
                >
                  {label}
                </button>
              ))}
            </div>
            <label className="macro-target-picker">
              <span>分析标的</span>
              <select aria-label="分析标的" value={targetValue} onChange={(event) => setTargetValue(event.target.value)}>
                {targetItems.map((item) => (
                  <option key={item.id} value={`${item.type}:${item.code}`}>
                    {displayTargetName(item)} - {targetTypeLabel(item.type)}
                  </option>
                ))}
              </select>
            </label>
            <label className="macro-target-picker compact">
              <span>统计范围</span>
              <select aria-label="统计范围" value={scope} onChange={(event) => setScope(event.target.value)}>
                <option value="non_financial">剔除金融</option>
                <option value="all">全量</option>
              </select>
            </label>
            <span className="macro-quarter-pill">{xrayData?.period.latest || xrayData?.period.label || "最新季度"}</span>
            <button className="terminal-button soft macro-quality-button" type="button">
              数据质量诊断
            </button>
          </div>
        </div>
        <LedgerChain latest={latest} loading={xray.isPending} />
        <MetricTransmissionGrid latest={latest} />
      </section>

      <section className="macro-chart-grid">
        <MacroChartCard
          title="营收利润剪刀差"
          subtitle="营收、净利润与利润-收入差，用于观察利润弹性是否领先。"
          icon={BarChart3}
          activeRange={periodWindow}
          onRangeChange={setPeriodWindow}
          option={xrayLineOption(xrayData, ["revenueYoy", "profitYoy", "profitRevenueGap"], ["营收同比", "净利润同比", "利润-收入差"], periodWindow)}
        />
        <MacroChartCard
          title="宏观库存指数"
          subtitle="库存、现金转化和收入改善共同判断补库周期。"
          icon={Activity}
          activeRange={periodWindow}
          onRangeChange={setPeriodWindow}
          option={xrayLineOption(xrayData, ["inventoryYoy", "cashConversionRatio"], ["库存同比", "现金转化"], periodWindow)}
        />
        <MacroChartCard
          title="企业躺平指数"
          subtitle="现金流较强但资本开支较弱时，企业更偏保守和回报股东。"
          icon={Layers}
          activeRange={periodWindow}
          onRangeChange={setPeriodWindow}
          option={xrayLineOption(xrayData, ["capexYoy", "ocfYoy", "netCashCompanyRatio"], ["资本开支", "经营现金流", "净现金公司占比"], periodWindow)}
        />
        <MacroChartCard
          title="分红挤出扩产"
          subtitle="比较扩产现金与分红/偿息现金，识别现金回报对扩产的挤出。"
          icon={SlidersHorizontal}
          activeRange={periodWindow}
          onRangeChange={setPeriodWindow}
          option={xrayLineOption(xrayData, ["capexYoy", "distributionCashYoy"], ["资本开支", "分红/偿息现金"], periodWindow)}
        />
        <MacroChartCard
          title="实物库存钟"
          subtitle="横轴营收，纵轴库存；右下角通常是需求改善但库存仍在消化。"
          icon={Compass}
          activeRange={periodWindow}
          onRangeChange={setPeriodWindow}
          option={xrayScatterOption(xrayData, "revenueYoy", "inventoryYoy", periodWindow)}
        />
        <MacroChartCard
          title="亏损扩散"
          subtitle="亏损公司占比与利润下滑公司占比，观察压力扩散或收敛。"
          icon={LineChart}
          activeRange={periodWindow}
          onRangeChange={setPeriodWindow}
          option={xrayLineOption(xrayData, ["lossCompanyRatio", "profitDeclineCompanyRatio"], ["亏损占比", "利润下滑占比"], periodWindow)}
        />
      </section>

      <RegimeStrip latest={latest} seriesMap={seriesMap} />

      <section className="macro-cycle-grid">
        <CycleCompass latest={latest} />
        <ThermoMeter latest={latest} seriesMap={seriesMap} />
      </section>

      <TrendAtlas timeseries={timeseriesData} />

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
    metricPill("cn.rate.cn10y", latestSeries(timeseries, "cn.rate.cn10y"), "%"),
    metricPill("us.rate.us10y", latestSeries(timeseries, "us.rate.us10y"), "%"),
    metricPill("fx.usdcnh", latestSeries(timeseries, "fx.usdcnh"), ""),
    metricPill("fx.dxy", latestSeries(timeseries, "fx.dxy"), ""),
    metricPill("us.vix", latestSeries(timeseries, "us.vix"), ""),
    metricPill("cn.money.m1_minus_m2_yoy", latestSeries(timeseries, "cn.money.m1_minus_m2_yoy"), "ppt"),
  ];
  const fallback = [...(dashboard?.rates || []), ...(dashboard?.indicators || []), ...(dashboard?.bond_yields || []), ...(dashboard?.fx_rates || [])].slice(0, 4);
  return (
    <section className="macro-weather-strip">
      <div className="macro-alert">
        <AlertTriangle size={16} />
        <span>基于估算的观测界限。部分宏观历史数据首次发布日期存在轻微估计偏差；接口不可用时会降级到公开源。</span>
      </div>
      <div className="macro-pill-strip">
        {loading ? <div className="market-empty compact macro-loading-row">正在连接宏观公开源</div> : null}
        {!loading && pills.every((pill) => pill.value === null)
          ? fallback.map((item) => (
              <MetricPill key={item.name} label={displayMetricName(item.name)} value={item.value} unit={item.unit} status={item.status} />
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
      <small>{statusLabel(status)}</small>
    </article>
  );
}

function LedgerChain({ latest, loading }: { latest: MacroXrayPoint | null; loading: boolean }) {
  const items = [
    { label: "订单温度", value: latest?.orderBacklogYoy, unit: "%", detail: "合同负债/订单前置信号" },
    { label: "定价权", value: latest?.grossMarginProxy, unit: "%", detail: "毛利率或价格传导" },
    { label: "利润变现", value: latest?.cashConversionRatio, unit: "x", detail: "经营现金流/利润" },
    { label: "产能利用", value: latest?.equipmentRenewalRatio, unit: "x", detail: "设备更新与折旧" },
    { label: "设备更新", value: latest?.fixedAssetsYoy, unit: "%", detail: "固定资产与扩产线索" },
  ];
  return (
    <div className="macro-ledger-grid">
      {loading ? <div className="market-empty compact macro-loading-row">正在计算 {XRAY_LABEL} 指标</div> : null}
      {!loading && !latest ? <div className="market-empty compact macro-loading-row">暂无可用企业账本数据</div> : null}
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

function MetricTransmissionGrid({ latest }: { latest: MacroXrayPoint | null }) {
  const cards = [
    ["周期现金", latest?.cashConversionRatio, "x", "销售变现能力"],
    ["利润剪刀差", latest?.profitRevenueGap, "%", "利润弹性"],
    ["存货周转", latest?.inventoryYoy, "%", "补库/去库压力"],
    ["应收压力", latest?.receivableYoy, "%", "回款压力"],
    ["资本开支", latest?.capexYoy, "%", "扩产强度"],
    ["设备更新", latest?.equipmentRenewalRatio, "x", "更新比例"],
    ["费用压力", latest?.expenseToRevenue, "%", "费用/收入"],
    ["亏损占比", latest?.lossCompanyRatio, "%", "亏损公司占比"],
  ];
  return (
    <div className="macro-transmission-grid">
      {cards.map(([label, value, unit, note]) => (
        <article className={toneClass(value as number | null | undefined)} key={String(label)}>
          <span>{label}</span>
          <strong>{formatXrayValue(value as number | null | undefined, String(unit))}</strong>
          <small>{note}</small>
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
  activeRange,
  onRangeChange,
}: {
  title: string;
  subtitle: string;
  icon: LucideIcon;
  option: ChartOption;
  activeRange: number;
  onRangeChange: (value: number) => void;
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
        <RangeButtons value={activeRange} onChange={onRangeChange} />
      </div>
      <EChartHost option={option} ariaLabel={title} />
    </section>
  );
}

function RangeButtons({ value, onChange }: { value: number; onChange: (value: number) => void }) {
  return (
    <div className="macro-range-buttons">
      {RANGES.map((item) => (
        <button className={value === item ? "active" : ""} key={item} type="button" onClick={() => onChange(item)}>
          {item}期
        </button>
      ))}
    </div>
  );
}

function RegimeStrip({ latest, seriesMap }: { latest: MacroXrayPoint | null; seriesMap: Map<string, MacroTimeseriesSeries> }) {
  const dr007 = latestPoint(seriesMap.get("cn.rates.repo.dr007"))?.value ?? null;
  const ppi = latestPoint(seriesMap.get("cn.ppi.yoy"))?.value ?? null;
  const spread = latestPoint(seriesMap.get("cn.money.m1_minus_m2_yoy"))?.value ?? null;
  const credit = latest?.receivableYoy ?? latestPoint(seriesMap.get("cn.credit.social_financing_yoy"))?.value ?? null;
  const items = [
    ["信用状态", credit, "%", credit !== null && credit >= 0 ? "信用修复" : "信用偏弱"],
    ["货币状态", dr007, "%", `${SERIES_LABELS["cn.rates.repo.dr007"]} ${dr007 === null ? "--" : formatNumber(dr007, 2) + "%"}`],
    ["价格状态", ppi, "%", ppi !== null && ppi >= 0 ? "价格修复" : "通缩压力"],
    ["M1-M2剪刀", spread, "ppt", spread !== null && spread >= 0 ? "剪刀差转正" : "剪刀差仍负"],
  ];
  return (
    <section className="macro-regime-strip">
      {items.map(([label, value, unit, detail]) => (
        <article key={String(label)}>
          <span>{label}</span>
          <strong>{formatPlainValue(value as number | null, String(unit))}</strong>
          <small>{detail}</small>
        </article>
      ))}
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
          <span>使用收入与价格利润信号定位周期象限。</span>
        </div>
      </div>
      <div className="macro-compass-grid">
        <span className="macro-compass-zone top-left">滞胀</span>
        <span className="macro-compass-zone top-right">过热</span>
        <span className="macro-compass-zone bottom-left">衰退</span>
        <span className="macro-compass-zone bottom-right">复苏</span>
        <i style={{ left: `${x}%`, top: `${y}%` }} />
      </div>
    </section>
  );
}

function ThermoMeter({ latest, seriesMap }: { latest: MacroXrayPoint | null; seriesMap: Map<string, MacroTimeseriesSeries> }) {
  const score = macroTemperature(latest, seriesMap);
  return (
    <section className="data-panel macro-chart-card macro-thermo-card">
      <div className="panel-head macro-panel-head">
        <div>
          <h3>
            <Thermometer size={16} />
            温度计
          </h3>
          <span>综合流动性与增长态势。</span>
        </div>
      </div>
      <div className="macro-thermo">
        <Gauge size={30} />
        <div className="macro-thermo-arc">
          <i style={{ width: `${score}%` }} />
        </div>
        <strong>{score >= 70 ? "偏热" : score >= 35 ? "中性" : "偏冷"}</strong>
        <span>剪刀差、PPI、利率综合分 {formatNumber(score, 0)} / 100</span>
      </div>
    </section>
  );
}

function TrendAtlas({ timeseries }: { timeseries?: MacroTimeseriesResponse }) {
  return (
    <section className="macro-trend-section">
      <div className="macro-section-title">
        <h3>趋势图谱</h3>
        <span>剪刀差、平减指数、价格组合与市场融资指标。</span>
      </div>
      <div className="macro-trend-grid">
        <TrendCard title="剪刀差" code="cn.money.m1_minus_m2_yoy" option={timeseriesLineOption(timeseries, ["cn.money.m1_yoy", "cn.money.m2_yoy", "cn.money.m1_minus_m2_yoy"])} />
        <TrendCard title="平减指数" code="cn.gdp.deflator_yoy" option={timeseriesLineOption(timeseries, ["cn.gdp.deflator_yoy"])} />
        <TrendCard title="PPI/CPI" code="cn.ppi.yoy / cn.cpi.yoy" option={timeseriesLineOption(timeseries, ["cn.ppi.yoy", "cn.cpi.yoy"])} />
        <TrendCard title="融资比例" code="cn.market.financing_ratio" option={timeseriesLineOption(timeseries, ["cn.market.financing_ratio"])} />
      </div>
    </section>
  );
}

function TrendCard({ title, code, option }: { title: string; code: string; option: ChartOption }) {
  return (
    <section className="data-panel macro-chart-card">
      <div className="panel-head macro-panel-head">
        <div>
          <small className="macro-code">{code}</small>
          <h3>{title}</h3>
        </div>
      </div>
      <EChartHost option={option} ariaLabel={title} />
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
  const visible = (series.length ? series : fallbackSandboxSeries(selectedIds)).slice(0, 18);
  return (
    <section className="data-panel macro-sandbox">
      <div className="panel-head macro-panel-head">
        <div>
          <h3>
            <SlidersHorizontal size={16} />
            指标沙盘
          </h3>
          <span>自由组合多个宏观指标，观察联动关系。</span>
        </div>
        <div className="macro-preset-buttons">
          {PRESETS.map((preset) => (
            <button key={preset.id} type="button" onClick={() => onChange(preset.ids)}>
              {preset.label}
            </button>
          ))}
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
              <span>{displaySeriesName(item)}</span>
              <small>{item.status === "unavailable" ? "待接官方源" : displaySeriesMeta(item)}</small>
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
          <h3>
            <Database size={16} />
            数据源状态
          </h3>
          <span>{disclaimer || "免费公开源可能延迟、缺失或被缓存。"}</span>
        </div>
      </div>
      <div className="quote-list">
        {statuses.map((status) => (
          <div className="quote-row" key={`${status.name}-${status.source}`}>
            <div>
              <strong>{displaySourceName(status.name)}</strong>
              <span>{displaySourceDetail(status.detail || status.source)}</span>
            </div>
            <div className="quote-price">
              <strong>{statusLabel(status.status)}</strong>
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

function xrayLineOption(data: MacroXrayResponse | undefined, fields: Array<keyof MacroXrayPoint>, labels: string[], limit = 16): ChartOption {
  const points = (data?.points || []).slice(-limit);
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

function xrayScatterOption(data: MacroXrayResponse | undefined, xField: keyof MacroXrayPoint, yField: keyof MacroXrayPoint, limit = 16): ChartOption {
  const points = (data?.points || []).slice(-limit);
  return {
    ...baseLineOption([], []),
    xAxis: { type: "value", axisLabel: { color: "#6b7f93", formatter: "{value}%" }, splitLine: { lineStyle: { color: "#e8eef4", type: "dashed" } } },
    yAxis: { type: "value", axisLabel: { color: "#6b7f93", formatter: "{value}%" }, splitLine: { lineStyle: { color: "#e8eef4", type: "dashed" } } },
    series: [
      {
        name: "库存钟轨迹",
        type: "scatter",
        symbolSize: 9,
        data: points.map((point) => [metricForChart(point[xField]), metricForChart(point[yField]), point.period]),
      },
    ],
  };
}

function timeseriesLineOption(data: MacroTimeseriesResponse | undefined, ids: string[]): ChartOption {
  const selected = ids.map((id) => data?.series.find((item) => item.series_id === id)).filter(Boolean) as MacroTimeseriesSeries[];
  const dates = Array.from(new Set(selected.flatMap((item) => item.points.map((point) => point.date)))).sort();
  return baseLineOption(
    dates,
    selected.map((item) => {
      const valueByDate = new Map(item.points.map((point) => [point.date, point.value]));
      return {
        name: displaySeriesName(item),
        type: "line",
        smooth: true,
        symbolSize: 3,
        data: dates.map((date) => valueByDate.get(date) ?? null),
      };
    }),
  );
}

function baseLineOption(xData: string[], series: ChartOption["series"]): ChartOption {
  return {
    animationDuration: 360,
    color: ["#38bdf8", "#10b981", "#fb7185", "#f59e0b", "#64748b"],
    grid: { top: 30, right: 14, bottom: 30, left: 42 },
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

function metricPill(seriesId: string, series: MacroTimeseriesSeries | undefined, fallbackUnit: string) {
  const latest = latestPoint(series);
  const previous = previousPoint(series);
  const value = latest?.value ?? null;
  const change = value !== null && previous?.value !== null && previous?.value !== undefined ? value - previous.value : null;
  return {
    label: SERIES_LABELS[seriesId] || displaySeriesName(series),
    value,
    unit: series?.unit === "pct" ? "%" : series?.unit || fallbackUnit,
    status: series?.status || "unavailable",
    change,
  };
}

function latestSeries(data: MacroTimeseriesResponse | undefined, id: string): MacroTimeseriesSeries | undefined {
  return data?.series.find((item) => item.series_id === id);
}

function mapSeries(data: MacroTimeseriesResponse | undefined): Map<string, MacroTimeseriesSeries> {
  return new Map((data?.series || []).map((item) => [item.series_id, item]));
}

function latestPoint(series: MacroTimeseriesSeries | undefined) {
  return series?.points[series.points.length - 1];
}

function previousPoint(series: MacroTimeseriesSeries | undefined) {
  return series && series.points.length > 1 ? series.points[series.points.length - 2] : null;
}

function normalizeTargets(data: { items?: MacroXrayTarget[]; targets?: MacroXrayTarget[] } | undefined): MacroXrayTarget[] {
  return data?.targets?.length ? data.targets : data?.items || [];
}

function fallbackSandboxSeries(ids: string[]): MacroTimeseriesSeries[] {
  return ids.map((id) => ({
    series_id: id,
    name: SERIES_LABELS[id] || id,
    category: "macro",
    frequency: "loading",
    unit: "",
    source: "unavailable",
    status: "unavailable",
    methodology: "待接官方源",
    is_derived: false,
    description: "",
    points: [],
  }));
}

function displaySeriesName(series: MacroTimeseriesSeries | undefined): string {
  if (!series) {
    return "未接入指标";
  }
  return SERIES_LABELS[series.series_id] || displayMetricName(series.name);
}

function displayMetricName(name: string): string {
  return SERIES_LABELS[name] || NAME_LABELS[name] || name;
}

function displaySeriesMeta(series: MacroTimeseriesSeries): string {
  const frequency = frequencyLabel(series.frequency);
  const unit = unitLabel(series.unit);
  return unit ? `${frequency} - ${unit}` : frequency;
}

function displaySourceName(name: string): string {
  return SERIES_LABELS[name] || NAME_LABELS[name] || SOURCE_LABELS[name] || name;
}

function displaySourceDetail(value: string | null | undefined): string {
  if (!value) {
    return "未披露来源";
  }
  const normalized = value.toLowerCase();
  if (SOURCE_LABELS[value]) {
    return SOURCE_LABELS[value];
  }
  if (normalized.includes("unavailable") || value.includes("待接")) {
    return "待接官方源";
  }
  if (normalized.includes("danginvest")) {
    return SOURCE_LABELS.danginvest;
  }
  if (normalized.includes("akshare")) {
    return SOURCE_LABELS.akshare;
  }
  if (normalized.includes("derived")) {
    return "派生指标";
  }
  if (normalized.includes("proxy")) {
    return "代理口径";
  }
  return value;
}

function displayMethodology(value: string | null | undefined): string {
  if (!value) {
    return "等待数据返回";
  }
  return value.replace("X-Ray", XRAY_LABEL);
}

function statusLabel(status: string | null | undefined): string {
  const labels: Record<string, string> = {
    loading: "加载中",
    live: "可用",
    stale: "缓存",
    partial: "部分可用",
    unavailable: "不可用",
  };
  return labels[status || "unavailable"] || "未知";
}

function targetTypeLabel(type: string): string {
  if (type === "index") {
    return "宽基指数";
  }
  if (type === "industry" || type === "ths_industry") {
    return "个股行业";
  }
  if (type === "etf") {
    return "行业 ETF（交易型开放式指数基金）";
  }
  return type;
}

function displayTargetName(item: MacroXrayTarget): string {
  return item.label || item.name || item.shortLabel || item.code;
}

function frequencyLabel(frequency: string): string {
  const labels: Record<string, string> = {
    D: "日频",
    W: "周频",
    M: "月频",
    Q: "季频",
    daily: "日频",
    weekly: "周频",
    monthly: "月频",
    quarterly: "季频",
  };
  return labels[frequency] || frequency || "频率未披露";
}

function unitLabel(unit: string): string {
  if (!unit || unit === "num") {
    return "";
  }
  if (unit === "ppt") {
    return "百分点";
  }
  if (unit === "pct") {
    return "%";
  }
  return unit;
}

function formatXrayValue(value: unknown, unit: string): string {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "--";
  }
  if (unit === "%") {
    return `${formatNumber(Math.abs(value) <= 2 ? value * 100 : value, 1)}%`;
  }
  if (unit === "x") {
    return `${formatNumber(value, 2)}x`;
  }
  return formatNumber(value, 2);
}

function formatPlainValue(value: number | null, unit: string): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return "--";
  }
  return `${formatNumber(value, unit ? 2 : 3)}${unit}`;
}

function metricForChart(value: unknown): number | null {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return null;
  }
  return Math.abs(value) <= 2 ? Number((value * 100).toFixed(4)) : value;
}

function toneClass(value: number | null | undefined): string {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "neutral";
  }
  if (value > 0.02) {
    return "hot";
  }
  if (value < -0.02) {
    return "cold";
  }
  return "neutral";
}

function macroTemperature(latest: MacroXrayPoint | null, seriesMap: Map<string, MacroTimeseriesSeries>): number {
  const spread = latestPoint(seriesMap.get("cn.money.m1_minus_m2_yoy"))?.value ?? -2;
  const ppi = latestPoint(seriesMap.get("cn.ppi.yoy"))?.value ?? 0;
  const dr007 = latestPoint(seriesMap.get("cn.rates.repo.dr007"))?.value ?? 2;
  const profit = latest?.profitYoy ?? 0;
  const score = 50 + spread * 4 + ppi * 3 - (dr007 - 1.8) * 12 + profit * 180;
  return Math.max(0, Math.min(100, Math.round(score)));
}

function parseTargetValue(value: string): { universe_type: string; universe_code: string } {
  const [type, ...rest] = value.split(":");
  return { universe_type: type || "index", universe_code: rest.join(":") || "000300.SH" };
}

function fallbackTargets(): MacroXrayTarget[] {
  return [
    { id: "index:000300.SH", type: "index", code: "000300.SH", name: "沪深300", source: "static", status: "live" },
    { id: "index:000905.SH", type: "index", code: "000905.SH", name: "中证500", source: "static", status: "live" },
    { id: "industry:BK1036", type: "industry", code: "BK1036", name: "半导体", source: "static", status: "live" },
    { id: "etf:512200.SH", type: "etf", code: "512200.SH", name: "房地产ETF", source: "static", status: "live" },
  ];
}

function mergeStatuses(statuses: DashboardSourceStatus[]): DashboardSourceStatus[] {
  const seen = new Set<string>();
  return statuses.filter((status) => {
    const key = `${status.name}-${status.source}`;
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) {
    return "--";
  }
  try {
    return new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
  } catch {
    return value;
  }
}
