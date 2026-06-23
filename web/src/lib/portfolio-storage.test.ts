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
      },
    ];

    expect(deserializePortfolio(serializePortfolio(positions))).toEqual(positions);
  });

  it("returns empty list for corrupted local storage payload", () => {
    expect(deserializePortfolio("{broken")).toEqual([]);
    expect(deserializePortfolio(JSON.stringify({ not: "an array" }))).toEqual([]);
  });
});
