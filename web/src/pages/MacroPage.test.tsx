import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { api } from "../lib/api";
import type { MacroDashboardResponse } from "../lib/types";
import { MacroPage } from "./MacroPage";

vi.mock("../lib/api", () => ({
  api: {
    macroDashboard: vi.fn(),
  },
}));

const macroDashboard: MacroDashboardResponse = {
  as_of: "2026-06-24T09:30:00Z",
  cache_status: "live",
  source_status: [
    { name: "macro_rates", status: "live", source: "akshare-macro", detail: "", as_of: "2026-06-24T09:30:00Z" },
  ],
  rates: [
    { name: "1Y LPR", value: 3.0, unit: "%", as_of: "2026-06-20", source: "akshare-macro", status: "live" },
    { name: "5Y LPR", value: 3.5, unit: "%", as_of: "2026-06-20", source: "akshare-macro", status: "live" },
  ],
  indicators: [
    { name: "CPI", value: 0.3, unit: "%", as_of: "2026-05", source: "akshare-macro", status: "live" },
    { name: "GDP", value: 5.4, unit: "%", as_of: "2026-Q1", source: "akshare-macro", status: "live" },
    { name: "PMI", value: 50.8, unit: "", as_of: "2026-05", source: "akshare-macro", status: "live" },
  ],
  bond_yields: [
    { name: "中国10Y", value: 2.15, unit: "%", as_of: "2026-06-23", source: "akshare-bond", status: "live" },
    { name: "美国10Y", value: 4.25, unit: "%", as_of: "2026-06-23", source: "akshare-bond", status: "live" },
  ],
  fx_rates: [
    { name: "USD/CNY", value: 7.18, unit: "", as_of: "2026-06-23", source: "bank-of-china", status: "live" },
  ],
  disclaimer: "免费公开源可能延迟。",
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

describe("MacroPage real dashboard", () => {
  it("renders real macro groups instead of market sentiment placeholders", async () => {
    vi.mocked(api.macroDashboard).mockResolvedValue(macroDashboard);

    renderMacroPage();

    expect(await screen.findByText("宏观仪表盘")).toBeTruthy();
    expect(await screen.findByText("1Y LPR")).toBeTruthy();
    expect(screen.getByText("CPI")).toBeTruthy();
    expect(screen.getByText("GDP")).toBeTruthy();
    expect(screen.getByText("PMI")).toBeTruthy();
    expect(screen.getByText("中国10Y")).toBeTruthy();
    expect(screen.getByText("USD/CNY")).toBeTruthy();
    expect(screen.getAllByText(/akshare-macro/).length).toBeGreaterThan(0);
    expect(screen.queryByText(/A股情绪温度/)).toBeNull();
    expect(api.macroDashboard).toHaveBeenCalledOnce();
  });
});
