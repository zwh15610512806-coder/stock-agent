import { create } from "zustand";
import type { PortfolioPosition } from "./types";
import {
  PORTFOLIO_STORAGE_KEY,
  deserializePortfolio,
  serializePortfolio,
} from "./portfolio-storage";

interface PortfolioState {
  positions: PortfolioPosition[];
  setPositions: (positions: PortfolioPosition[]) => void;
  addPosition: (position: PortfolioPosition) => void;
  removePosition: (symbol: string) => void;
  clear: () => void;
}

const initialPositions =
  typeof window === "undefined"
    ? []
    : deserializePortfolio(window.localStorage.getItem(PORTFOLIO_STORAGE_KEY));

export const usePortfolioStore = create<PortfolioState>((set, get) => ({
  positions: initialPositions,
  setPositions: (positions) => {
    persist(positions);
    set({ positions });
  },
  addPosition: (position) => {
    const next = [...get().positions.filter((item) => item.symbol !== position.symbol), position];
    persist(next);
    set({ positions: next });
  },
  removePosition: (symbol) => {
    const next = get().positions.filter((item) => item.symbol !== symbol);
    persist(next);
    set({ positions: next });
  },
  clear: () => {
    persist([]);
    set({ positions: [] });
  },
}));

function persist(positions: PortfolioPosition[]): void {
  if (typeof window !== "undefined") {
    window.localStorage.setItem(PORTFOLIO_STORAGE_KEY, serializePortfolio(positions));
  }
}
