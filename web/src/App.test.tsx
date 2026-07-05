import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { App } from "./App";

function renderApp(initialEntry = "/") {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("App Xirang shell", () => {
  it("renders the Xirang top navigation and utility controls", () => {
    renderApp();

    expect(screen.getAllByText("裕见投研").length).toBeGreaterThan(0);
    const primaryNav = screen.getByLabelText("主导航");
    expect(within(primaryNav).getByRole("link", { name: "市场" }).getAttribute("href")).toBe("/market");
    expect(within(primaryNav).getByRole("link", { name: "宏观" }).getAttribute("href")).toBe("/macro");
    expect(within(primaryNav).getByRole("link", { name: "选股" }).getAttribute("href")).toBe("/stocks");
    expect(within(primaryNav).getByRole("link", { name: "我的持仓" }).getAttribute("href")).toBe("/portfolio");
    expect(within(primaryNav).queryByRole("link", { name: "检索" })).toBeNull();
    expect(screen.getByPlaceholderText("搜索股票、持仓、标签...")).toBeTruthy();
    expect(screen.getByRole("button", { name: "时光机" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "切换主题" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "组合沙箱" }).getAttribute("href")).toBe("/portfolio");
  });

  it("redirects the root route to the market overview", async () => {
    renderApp("/");

    expect(await screen.findByRole("heading", { name: "市场全景" })).toBeTruthy();
  });

  it("renders the stock center on /stocks", async () => {
    renderApp("/stocks");

    expect(await screen.findByRole("heading", { name: "选股中心" })).toBeTruthy();
    expect(screen.getByRole("tab", { name: /工作台/ })).toBeTruthy();
    expect(screen.getByRole("tab", { name: /选股器/ })).toBeTruthy();
    expect(screen.getByRole("tab", { name: /ETF/ })).toBeTruthy();
  });

  it("opens and closes the mobile navigation menu", () => {
    renderApp("/market");

    fireEvent.click(screen.getByRole("button", { name: "打开菜单" }));
    const mobileNav = screen.getByLabelText("移动导航");
    expect(within(mobileNav).getByRole("link", { name: "我的持仓" }).getAttribute("href")).toBe("/portfolio");

    fireEvent.click(screen.getByRole("button", { name: "关闭菜单" }));
    expect(screen.queryByLabelText("移动导航")).toBeNull();
  });
});
