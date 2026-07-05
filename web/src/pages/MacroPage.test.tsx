import { readFileSync } from "node:fs";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
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
  apiFailureMessage: (_error: unknown, label: string) => `${label}\u6682\u4e0d\u53ef\u7528`,
}));

const zh = {
  macroWeather: "\u5b8f\u89c2\u5929\u6c14",
  ledger: "\u4f01\u4e1a\u8d26\u672c\u5b8f\u89c2\u4f20\u5bfc\u94fe",
  profitGap: "\u5229\u6da6\u526a\u5200\u5dee",
  compass: "\u5468\u671f\u7f57\u76d8",
  thermometer: "\u6e29\u5ea6\u8ba1",
  trendMap: "\u8d8b\u52bf\u56fe\u8c31",
  sandbox: "\u6307\u6807\u6c99\u76d8",
  sourceStatus: "\u6570\u636e\u6e90\u72b6\u6001",
  target: "\u5206\u6790\u6807\u7684",
  m1M2: "M1-M2\uff08\u72ed\u4e49\u8d27\u5e01-\u5e7f\u4e49\u8d27\u5e01\u540c\u6bd4\u5dee\uff09",
  ppi: "PPI\uff08\u5de5\u4e1a\u54c1\u51fa\u5382\u4ef7\u683c\u6307\u6570\uff09",
  usdcnh: "USD/CNH\uff08\u7f8e\u5143\u5151\u79bb\u5cb8\u4eba\u6c11\u5e01\uff09",
  unavailable: "\u5f85\u63a5\u5b98\u65b9\u6e90",
  revenueProfit: "\u8425\u6536\u5229\u6da6\u526a\u5200\u5dee",
  inventoryIndex: "\u5b8f\u89c2\u5e93\u5b58\u6307\u6570",
  lyingFlat: "\u4f01\u4e1a\u8eba\u5e73\u6307\u6570",
  dividendCapex: "\u5206\u7ea2\u6324\u51fa\u6269\u4ea7",
  inventoryClock: "\u5b9e\u7269\u5e93\u5b58\u949f",
  lossDiffusion: "\u4e8f\u635f\u6269\u6563",
  scissors: "\u526a\u5200\u5dee",
  deflator: "\u5e73\u51cf\u6307\u6570",
  financingRatio: "\u878d\u8d44\u6bd4\u4f8b",
  broadIndex: "\u5bbd\u57fa\u6307\u6570",
  industry: "\u4e2a\u80a1\u884c\u4e1a",
  etf: "\u884c\u4e1a ETF",
  dataQuality: "\u6570\u636e\u8d28\u91cf\u8bca\u65ad",
  sampleCount: "\u6837\u672c\u6570",
  coverage: "\u8986\u76d6\u7387",
  dr007: "DR007\uff08\u94f6\u884c\u95f47\u5929\u56de\u8d2d\u5229\u7387\uff09",
  xray: "X-Ray\uff08\u4f01\u4e1a\u8d26\u672c\u900f\u89c6\uff09",
};

const macroDashboard: MacroDashboardResponse = {
  as_of: "2026-06-24T09:30:00Z",
  cache_status: "partial",
  source_status: [
    { name: "macro_china_money_supply", status: "live", source: "akshare", detail: "", as_of: "2026-06-24T09:30:00Z" },
    { name: "cn.real_estate.loan_yoy", status: "unavailable", source: "unavailable", detail: zh.unavailable, as_of: null },
  ],
  rates: [{ name: "China 10Y", value: 1.85, unit: "%", as_of: "2026-06-24", source: "akshare", status: "live" }],
  indicators: [{ name: "PPI", value: -0.3, unit: "%", as_of: "2026-05", source: "akshare", status: "live" }],
  bond_yields: [{ name: "US 10Y", value: 4.2, unit: "%", as_of: "2026-06-24", source: "akshare", status: "live" }],
  fx_rates: [{ name: "USD/CNH", value: 7.18, unit: "", as_of: "2026-06-24", source: "akshare", status: "live" }],
  disclaimer: "\u516c\u5f00\u514d\u8d39\u6e90\u53ef\u80fd\u5ef6\u8fdf\u6216\u4e0d\u53ef\u7528",
};

const timeseriesResponse: MacroTimeseriesResponse = {
  ts: "2026-06-24T09:30:00Z",
  start: "2025-01-01",
  end: "2026-06-24",
  source_status: macroDashboard.source_status,
  disclaimer: "\u516c\u5f00\u514d\u8d39\u6e90\u53ef\u80fd\u5ef6\u8fdf\u6216\u4e0d\u53ef\u7528",
  series: [
    {
      series_id: "cn.money.m1_yoy",
      name: "M1 YoY",
      category: "money",
      frequency: "monthly",
      unit: "%",
      source: "akshare.macro_china_money_supply",
      status: "live",
      methodology: "\u516c\u5f00\u6e90",
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
      series_id: "cn.ppi.yoy",
      name: "PPI YoY",
      category: "inflation",
      frequency: "monthly",
      unit: "%",
      source: "akshare.macro_china_ppi",
      status: "live",
      methodology: "\u516c\u5f00\u6e90",
      is_derived: false,
      description: "",
      points: [{ date: "2026-04-01", point_date: "2026-04-01", release_date: null, value: -0.3 }],
    },
    {
      series_id: "fx.usdcnh",
      name: "USD/CNH",
      category: "fx",
      frequency: "daily",
      unit: "",
      source: "akshare.forex_hist_em",
      status: "live",
      methodology: "\u516c\u5f00\u6e90",
      is_derived: false,
      description: "",
      points: [{ date: "2026-04-01", point_date: "2026-04-01", release_date: null, value: 7.18 }],
    },
    {
      series_id: "cn.rates.repo.dr007",
      name: "DR007",
      category: "rates",
      frequency: "daily",
      unit: "%",
      source: "danginvest",
      status: "live",
      methodology: "\u516c\u5f00\u6e90",
      is_derived: false,
      description: "",
      points: [{ date: "2026-04-01", point_date: "2026-04-01", release_date: null, value: 1.36 }],
    },
    {
      series_id: "cn.real_estate.loan_yoy",
      name: "Real Estate Loan YoY",
      category: "property",
      frequency: "quarterly",
      unit: "%",
      source: "unavailable",
      status: "unavailable",
      methodology: zh.unavailable,
      is_derived: false,
      description: "",
      points: [],
    },
  ],
};

const xrayResponse = {
  ts: "2026-06-24T09:30:00Z",
  status: "live",
  index: { code: "000300.SH", name: "\u6caa\u6df1300\u6307\u6570" },
  universe: { type: "index", code: "000300.SH", name: "\u6caa\u6df1300", scope: "non_financial" },
  period: { latest: "2026 Q1", quarters: 40, lookback: 6, periodEnd: "2026-03-31", label: "2026 Q1" },
  sample: { count: 233, coverage: 0.94, source: "danginvest", currentConstituentCount: 248 },
  latest: {
    period: "2026 Q1",
    date: "2026-03-31",
    revenueYoy: 0.06,
    profitYoy: 0.04,
    profitRevenueGap: -0.02,
    inventoryYoy: 0.03,
    cashConversionRatio: 0.82,
    capexYoy: -0.047,
    distributionCashYoy: 0.069,
    lossCompanyRatio: 0.016,
    profitDeclineCompanyRatio: 0.287,
    equipmentRenewalRatio: 0.64,
  },
  points: [
    { period: "2025 Q4", date: "2025-12-31", revenueYoy: 0.052, profitYoy: 0.031, inventoryYoy: 0.035, cashConversionRatio: 0.78, capexYoy: -0.041, distributionCashYoy: 0.061 },
    { period: "2026 Q1", date: "2026-03-31", revenueYoy: 0.06, profitYoy: 0.04, inventoryYoy: 0.03, cashConversionRatio: 0.82, capexYoy: -0.047, distributionCashYoy: 0.069 },
  ],
  nominalGdp: [],
  crossIndex: [],
  insights: [{ level: "warning", title: "\u5229\u6da6\u5f39\u6027\u5f31\u4e8e\u6536\u5165", detail: "\u5229\u6da6-\u6536\u5165\u4ee3\u7406\u5dee\u4e3a -2.00%\u3002" }],
  diagnostics: [],
  source_status: [],
  methodology: "DangInvest X-Ray",
} as unknown as MacroXrayResponse;

const targetsResponse = {
  ts: "2026-06-24T09:30:00Z",
  status: "live",
  source_status: [],
  methodology: "targets",
  targets: [
    { id: "index:000300.SH", type: "index", code: "000300.SH", name: "\u6caa\u6df1300", label: "\u6caa\u6df1300", source: "static", status: "live" },
    { id: "industry:BK1036", type: "industry", code: "BK1036", name: "\u534a\u5bfc\u4f53", label: "\u534a\u5bfc\u4f53", source: "akshare", status: "live" },
    { id: "etf:512200.SH", type: "etf", code: "512200.SH", name: "\u623f\u5730\u4ea7ETF", label: "\u623f\u5730\u4ea7ETF", source: "danginvest", status: "live" },
  ],
  items: [
    { id: "index:000300.SH", type: "index", code: "000300.SH", name: "\u6caa\u6df1300", source: "static", status: "live" },
    { id: "industry:BK1036", type: "industry", code: "BK1036", name: "\u534a\u5bfc\u4f53", source: "akshare", status: "live" },
    { id: "etf:512200.SH", type: "etf", code: "512200.SH", name: "\u623f\u5730\u4ea7ETF", source: "danginvest", status: "live" },
  ],
} as unknown as MacroXrayTargetsResponse;

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
  beforeEach(() => {
    window.localStorage.clear();
    vi.clearAllMocks();
  });

  it("keeps MacroPage source encoded as UTF-8 Chinese text", () => {
    const source = readFileSync(`${process.cwd()}/src/pages/MacroPage.tsx`, "utf8");

    expect(source).toContain("\u5b8f\u89c2\u5929\u6c14");
    expect(source).not.toMatch(/锛|瀹忚|涓|鏈|鐘舵|鐎|娑|铻|鍟|鍛|浼佷笟|�/);
  });

  it("renders Chinese workbench copy and explains professional English abbreviations", async () => {
    vi.mocked(api.macroDashboard).mockResolvedValue(macroDashboard);
    vi.mocked(api.macroTimeseries).mockResolvedValue(timeseriesResponse);
    vi.mocked(api.macroXray).mockResolvedValue(xrayResponse);
    vi.mocked(api.macroXrayTargets).mockResolvedValue(targetsResponse);

    renderMacroPage();

    expect(await screen.findByText(zh.macroWeather)).toBeTruthy();
    expect(screen.getByText(zh.ledger)).toBeTruthy();
    expect(await screen.findByText(zh.profitGap)).toBeTruthy();
    expect(screen.getByText(zh.compass)).toBeTruthy();
    expect(screen.getByText(zh.thermometer)).toBeTruthy();
    expect(screen.getByText(zh.trendMap)).toBeTruthy();
    expect(screen.getByText(zh.sandbox)).toBeTruthy();
    expect(screen.getByText(zh.sourceStatus)).toBeTruthy();
    expect(await screen.findAllByText(zh.m1M2)).toHaveLength(2);
    expect(screen.getAllByText(zh.ppi).length).toBeGreaterThan(0);
    expect(screen.getAllByText(zh.usdcnh).length).toBeGreaterThan(0);
    expect(screen.getAllByText(zh.dr007).length).toBeGreaterThan(0);
    expect(screen.getAllByText(zh.xray).length).toBeGreaterThan(0);
    expect(screen.getAllByText(zh.unavailable).length).toBeGreaterThan(0);
    expect(screen.queryByText("M1-M2 YoY Spread")).toBeNull();
    expect(screen.queryByText("unavailable")).toBeNull();
    expect(api.macroDashboard).not.toHaveBeenCalled();
  });

  it("renders the DangInvest-style macro weather workbench modules and controls", async () => {
    vi.mocked(api.macroDashboard).mockResolvedValue(macroDashboard);
    vi.mocked(api.macroTimeseries).mockResolvedValue(timeseriesResponse);
    vi.mocked(api.macroXray).mockResolvedValue(xrayResponse);
    vi.mocked(api.macroXrayTargets).mockResolvedValue(targetsResponse);

    renderMacroPage();

    expect(await screen.findByText(zh.revenueProfit)).toBeTruthy();
    expect(screen.getByText(zh.inventoryIndex)).toBeTruthy();
    expect(screen.getByText(zh.lyingFlat)).toBeTruthy();
    expect(screen.getByText(zh.dividendCapex)).toBeTruthy();
    expect(screen.getByText(zh.inventoryClock)).toBeTruthy();
    expect(screen.getByText(zh.lossDiffusion)).toBeTruthy();
    expect(screen.getByText(zh.scissors)).toBeTruthy();
    expect(screen.getByText(zh.deflator)).toBeTruthy();
    expect(screen.getByText("PPI/CPI")).toBeTruthy();
    expect(screen.getByText(zh.financingRatio)).toBeTruthy();
    expect(screen.getByText(zh.broadIndex)).toBeTruthy();
    expect(screen.getByText(zh.industry)).toBeTruthy();
    expect(screen.getByText(zh.etf)).toBeTruthy();
    expect(screen.queryByText(zh.sampleCount)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: zh.dataQuality }));
    expect(screen.getByText(zh.sampleCount)).toBeTruthy();
    expect(screen.getByText(zh.coverage)).toBeTruthy();
    expect(screen.getByText("233")).toBeTruthy();
    expect(screen.getByText("94.0%")).toBeTruthy();
    for (const label of ["6\u671f", "16\u671f", "24\u671f", "32\u671f", "40\u671f"]) {
      expect(screen.getAllByText(label).length).toBeGreaterThan(0);
    }
    for (const preset of ["\u5916\u90e8\u538b\u529b", "\u5730\u4ea7\u8109\u51b2", "\u6d41\u52a8\u6027", "\u589e\u957f\u7a00\u91ca", "\u5e02\u573a\u60c5\u7eea"]) {
      expect(screen.getByRole("button", { name: preset })).toBeTruthy();
    }
  });

  it("re-requests X-Ray data when the analysis target changes", async () => {
    vi.mocked(api.macroDashboard).mockResolvedValue(macroDashboard);
    vi.mocked(api.macroTimeseries).mockResolvedValue(timeseriesResponse);
    vi.mocked(api.macroXray).mockResolvedValue(xrayResponse);
    vi.mocked(api.macroXrayTargets).mockResolvedValue(targetsResponse);

    renderMacroPage();

    const select = (await screen.findByLabelText(zh.target)) as HTMLSelectElement;
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
