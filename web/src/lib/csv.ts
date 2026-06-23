import Papa from "papaparse";
import type { MarketCode, PortfolioPosition } from "./types";

const HEADER_ALIASES: Record<string, keyof PortfolioPosition> = {
  symbol: "symbol",
  "代码": "symbol",
  "证券代码": "symbol",
  name: "name",
  "名称": "name",
  "证券名称": "name",
  market: "market",
  "市场": "market",
  quantity: "quantity",
  "数量": "quantity",
  "持仓": "quantity",
  cost_price: "cost_price",
  "成本价": "cost_price",
  "成本": "cost_price",
  current_price: "current_price",
  "现价": "current_price",
  "当前价": "current_price",
};

export function parsePositionsCsv(csv: string): PortfolioPosition[] {
  const parsed = Papa.parse<string[]>(csv.trim(), { skipEmptyLines: true });
  const rows = parsed.data;
  const positions: PortfolioPosition[] = [];
  let header: Array<keyof PortfolioPosition | null> | null = null;

  for (const row of rows) {
    const maybeHeader = row.map((cell) => HEADER_ALIASES[cell.trim()] ?? null);
    const headerScore = maybeHeader.filter(Boolean).length;
    if (headerScore >= 3) {
      header = maybeHeader;
      continue;
    }
    if (!header) {
      continue;
    }
    const record: Partial<PortfolioPosition> = {};
    row.forEach((cell, index) => {
      const key = header?.[index];
      if (!key) {
        return;
      }
      const clean = cell.trim();
      if (key === "quantity" || key === "cost_price" || key === "current_price") {
        record[key] = Number(clean);
        return;
      }
      if (key === "symbol") {
        record.symbol = clean;
      }
      if (key === "name") {
        record.name = clean;
      }
      if (key === "market") {
        record.market = clean as MarketCode;
      }
      if (key === "currency") {
        record.currency = clean;
      }
    });
    if (!record.symbol || !record.market || !record.quantity || record.cost_price === undefined) {
      continue;
    }
    const market = normalizeMarket(record.market);
    positions.push({
      symbol: String(record.symbol).trim().toUpperCase(),
      name: String(record.name || record.symbol).trim(),
      market,
      quantity: Number(record.quantity),
      cost_price: Number(record.cost_price),
      current_price: Number(record.current_price ?? record.cost_price),
      currency: currencyForMarket(market),
    });
  }
  return positions;
}

function normalizeMarket(value: unknown): MarketCode {
  const market = String(value || "").trim().toUpperCase();
  if (market === "HK" || market === "港股") {
    return "HK";
  }
  if (market === "US" || market === "美股") {
    return "US";
  }
  return "CN";
}

export function currencyForMarket(market: MarketCode): string {
  return { CN: "CNY", HK: "HKD", US: "USD" }[market];
}
