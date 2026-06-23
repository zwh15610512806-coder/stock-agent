import { describe, expect, it } from "vitest";
import { parsePositionsCsv } from "./csv";

describe("parsePositionsCsv", () => {
  it("parses english and chinese portfolio columns", () => {
    const csv = [
      "symbol,name,market,quantity,cost_price,current_price",
      "600519.SH,贵州茅台,CN,10,1000,1200",
      "代码,名称,市场,数量,成本价,现价",
      "00700.HK,腾讯控股,HK,20,300,250",
    ].join("\n");

    expect(parsePositionsCsv(csv)).toEqual([
      {
        symbol: "600519.SH",
        name: "贵州茅台",
        market: "CN",
        quantity: 10,
        cost_price: 1000,
        current_price: 1200,
        currency: "CNY",
      },
      {
        symbol: "00700.HK",
        name: "腾讯控股",
        market: "HK",
        quantity: 20,
        cost_price: 300,
        current_price: 250,
        currency: "HKD",
      },
    ]);
  });
});
