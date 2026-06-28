import { describe, expect, it } from "vitest";
import { deserializePortfolio, serializePortfolio } from "./portfolio-storage";
import type { PortfolioPosition } from "./types";

describe("portfolio storage helpers", () => {
  it("round trips local portfolio positions", () => {
    const positions: PortfolioPosition[] = [
      {
        symbol: "AAPL",
        name: "Apple",
        market: "US",
        quantity: 3,
        cost_price: 180,
        current_price: 200,
        currency: "USD",
        available_quantity: 2,
        market_value: 600,
        cost_value: 540,
        pnl: 60,
        pnl_pct: 0.111111,
        source: "ocr",
        source_snapshot_at: "2026-06-28T00:00:00Z",
        raw_fields: { broker_column: "raw value" },
      },
    ];

    expect(deserializePortfolio(serializePortfolio(positions))).toEqual(positions);
  });

  it("keeps old six-field local portfolio positions valid", () => {
    const payload = JSON.stringify([
      {
        symbol: "600519.SH",
        name: "贵州茅台",
        market: "CN",
        quantity: 10,
        cost_price: 1000,
        current_price: 1200,
        currency: "CNY",
      },
    ]);

    expect(deserializePortfolio(payload)).toEqual([
      {
        symbol: "600519.SH",
        name: "贵州茅台",
        market: "CN",
        quantity: 10,
        cost_price: 1000,
        current_price: 1200,
        currency: "CNY",
      },
    ]);
  });

  it("returns empty list for corrupted local storage payload", () => {
    expect(deserializePortfolio("{broken")).toEqual([]);
    expect(deserializePortfolio(JSON.stringify({ not: "an array" }))).toEqual([]);
  });
});
