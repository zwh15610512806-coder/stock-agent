import type { PortfolioPosition } from "./types";

export const PORTFOLIO_STORAGE_KEY = "zhi-tou-terminal:portfolio";

export function serializePortfolio(positions: PortfolioPosition[]): string {
  return JSON.stringify(positions);
}

export function deserializePortfolio(payload: string | null): PortfolioPosition[] {
  if (!payload) {
    return [];
  }
  try {
    const parsed = JSON.parse(payload);
    if (!Array.isArray(parsed)) {
      return [];
    }
    return parsed.filter(isPortfolioPosition);
  } catch {
    return [];
  }
}

function isPortfolioPosition(value: unknown): value is PortfolioPosition {
  if (!value || typeof value !== "object") {
    return false;
  }
  const row = value as Record<string, unknown>;
  return (
    typeof row.symbol === "string" &&
    typeof row.name === "string" &&
    (row.market === "CN" || row.market === "HK" || row.market === "US") &&
    typeof row.quantity === "number" &&
    typeof row.cost_price === "number" &&
    typeof row.current_price === "number" &&
    typeof row.currency === "string"
  );
}
