import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { api } from "../lib/api";
import type { MacroDashboardResponse, MacroTimeseriesResponse, MacroXrayResponse, MacroXrayTargetsResponse } from "../lib/types";
import { MacroPage } from "./MacroPage";

vi.mock("echarts", () => ({
  init: vi.fn(() => ({
    setOption: vi.fn(),
    resize: vi.fn(),
    dispose: vi.fn(),
  })),
}));

vi.mock("../lib/api", () => ({
  api: {
    macroDashboard: vi.fn(),
    macroTimeseries: vi.fn(),
    macroXray: vi.fn(),
    macroXrayTargets: vi.fn(),
  },
  apiFailureMessage: (_error: unknown, label: string) => `${label}暂不可用`,
}));

const macroDashboard: MacroDashboardResponse = {
  as_of: "2026-06-24T09:30:00Z",
  cache_status: "partial",
  source_status: [
    { name: "macro_china_money_supply", status: "live", source: "akshare", detail: "", as_of: "2026-06-24T09:30:00Z" },
    { name: "cn.real_estate.loan_yoy", status: "unavailable", source: "unavailable", detail: "待接官方源", as_of: null },
  ],
  rates: [{ name: "China 10Y", value: 1.85, unit: "%", as_of: "2026-06-24", source: "akshare", status: "live" }],
  indicators: [{ name: "PPI", value: -0.3, unit: "%", as_of: "2026-05", source: "akshare", status: "live" }],
  bond_yields: [{ name: "US 10Y", value: 4.2, unit: "%", as_of: "2026-06-24", source: "akshare", status: "live" }],
  fx_rates: [{ name: "USD/CNH", value: 7.18, unit: "", as_of: "2026-06-24", source: "akshare", status: "live" }],
  disclaimer: "公开免费源可能延迟或不可用",
};

const timeseriesResponse: MacroTimeseriesResponse = {
  ts: "2026-06-24T09:30:00Z",
  start: "2025-01-01",
  end: "2026-06-24",
  source_status: macroDashboard.source_status,
  disclaimer: "公开免费源可能延迟或不可用",
  series: [
    {
      series_id: "cn.money.m1_yoy",
      name: "M1 YoY",
      category: "money",
      frequency: "monthly",
      unit: "%",
      source: "akshare.macro_china_money_supply",
      status: "live",
      methodology: "公开源",
      is_derived: false,
      description: "",
      points: [
        { date: "2026-03-01", point_date: "2026-03-01", release_date: null, value: 4.8 },
        { date: "2026-04-01", point_date: "2026-04-01", release_date: null, value: 5.1 },
      ],
    },
    {
      series_id: "cn.money.m1_minus_m2_yoy",
      name: "M1-M2 YoY Spread",
      category: "money",
      frequency: "monthly",
      unit: "ppt",
      source: "derived",
      status: "live",
      methodology: "M1-M2",
      is_derived: true,
      description: "",
      points: [
        { date: "2026-03-01", point_date: "2026-03-01", release_date: null, value: -2.4 },
        { date: "2026-04-01", point_date: "2026-04-01", release_date: null, value: -2.1 },
      ],
    },
    {
      series_id: "cn.real_estate.loan_yoy",
      name: "Real Estate Loan YoY",
      category: "property",
      frequency: "quarterly",
      unit: "%",
      source: "unavailable",
      status: "unavailable",
      methodology: "待接官方源",
      is_derived: false,
      description: "",
      points: [],
    },
  ],
};

const xrayResponse: MacroXrayResponse = {
  ts: "2026-06-24T09:30:00Z",
  status: "live",
  index: "000300.SH",
  universe: { type: "index", code: "000300.SH", name: "沪深300", scope: "non_financial" },
  period: { latest: "2026Q2", quarters: 40, lookback: 6 },
  sample: { count: 1, coverage: 0, source: "public-macro-proxy" },
  latest: {
    period: "2026Q2",
    date: "2026-06-30",
    revenueYoy: 0.06,
    profitYoy: 0.04,
    profitRevenueGap: -0.02,
    inventoryYoy: 0.03,
    cashConversionRatio: 0.82,
  },
  points: [
    { period: "2026Q1", date: "2026-03-31", revenueYoy: 0.052, profitYoy: 0.031, inventoryYoy: 0.035, cashConversionRatio: 0.78 },
    { period: "2026Q2", date: "2026-06-30", revenueYoy: 0.06, profitYoy: 0.04, inventoryYoy: 0.03, cashConversionRatio: 0.82 },
  ],
  nominalGdp: [],
  crossIndex: [],
  insights: [{ level: "warning", title: "利润弹性弱于收入", detail: "利润-收入代理差为 -2.00%。" }],
  diagnostics: [],
  source_status: [],
  methodology: "公开宏观源近似版",
};

const targetsResponse: MacroXrayTargetsResponse = {
  ts: "2026-06-24T09:30:00Z",
  status: "live",
  source_status: [],
  methodology: "targets",
  items: [
    { id: "index:000300.SH", type: "index", code: "000300.SH", name: "沪深300", source: "static", status: "live" },
    { id: "industry:BK1036", type: "industry", code: "BK1036", name: "半导体", source: "akshare", status: "live" },
  ],
};

function renderMacroPage() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MacroPage />
    </QueryClientProvider>,
  );
}

describe("MacroPage workbench", () => {
  it("renders the macro weather workbench from dashboard, timeseries, and X-Ray APIs", async () => {
    vi.mocked(api.macroDashboard).mockResolvedValue(macroDashboard);
    vi.mocked(api.macroTimeseries).mockResolvedValue(timeseriesResponse);
    vi.mocked(api.macroXray).mockResolvedValue(xrayResponse);
    vi.mocked(api.macroXrayTargets).mockResolvedValue(targetsResponse);

    renderMacroPage();

    expect(await screen.findByText("宏观天气")).toBeTruthy();
    expect(screen.getByText("企业账本宏观传导链")).toBeTruthy();
    expect(screen.getByText("利润剪刀差")).toBeTruthy();
    expect(screen.getByText("周期罗盘")).toBeTruthy();
    expect(screen.getByText("温度计")).toBeTruthy();
    expect(screen.getByText("趋势图谱")).toBeTruthy();
    expect(screen.getByText("指标沙盘")).toBeTruthy();
    expect(screen.getByText("数据源状态")).toBeTruthy();
    expect(await screen.findByText("M1-M2 YoY Spread")).toBeTruthy();
    expect(screen.getAllByText(/待接官方源|unavailable/).length).toBeGreaterThan(0);
    expect(api.macroDashboard).toHaveBeenCalledOnce();
    expect(api.macroTimeseries).toHaveBeenCalledOnce();
    expect(api.macroXray).toHaveBeenCalled();
    expect(api.macroXrayTargets).toHaveBeenCalledOnce();
  });

  it("re-requests X-Ray data when the analysis target changes", async () => {
    vi.mocked(api.macroDashboard).mockResolvedValue(macroDashboard);
    vi.mocked(api.macroTimeseries).mockResolvedValue(timeseriesResponse);
    vi.mocked(api.macroXray).mockResolvedValue(xrayResponse);
    vi.mocked(api.macroXrayTargets).mockResolvedValue(targetsResponse);

    renderMacroPage();

    const select = (await screen.findByLabelText("分析标的")) as HTMLSelectElement;
    await waitFor(() => {
      expect(Array.from(select.options).map((option) => option.value)).toContain("industry:BK1036");
    });
    fireEvent.change(select, { target: { value: "industry:BK1036" } });

    await waitFor(() => {
      expect(api.macroXray).toHaveBeenCalledWith(
        expect.objectContaining({ universe_type: "industry", universe_code: "BK1036" }),
      );
    });
  });
});
