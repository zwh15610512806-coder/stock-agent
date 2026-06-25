import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { api } from "../lib/api";
import { SearchPage } from "./SearchPage";

vi.mock("../lib/api", () => ({
  api: {
    searchSymbols: vi.fn(),
  },
  apiFailureMessage: (_error: unknown, label: string) => `${label}后端未连接`,
}));

function renderSearchPage() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <SearchPage />
    </QueryClientProvider>,
  );
}

describe("SearchPage", () => {
  it("shows a visible backend error when symbol search fails", async () => {
    vi.mocked(api.searchSymbols).mockRejectedValue(new Error("offline"));

    renderSearchPage();

    expect(await screen.findByText("检索加载失败")).toBeTruthy();
    expect(screen.getByText("股票检索后端未连接")).toBeTruthy();
  });
});
