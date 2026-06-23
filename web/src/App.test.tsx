import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { App } from "./App";

function renderApp() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("App broker terminal shell", () => {
  it("renders reference-style navigation and top command controls", () => {
    renderApp();

    expect(screen.getByText("市场总览")).toBeTruthy();
    expect(screen.getByText("AI 投顾")).toBeTruthy();
    expect(screen.getByPlaceholderText("搜索股票 / 指数 / 板块 / 资讯")).toBeTruthy();
    expect(screen.getByDisplayValue("2024-06-20")).toBeTruthy();
    expect(screen.getByText("自定义视图")).toBeTruthy();
  });

  it("opens local menus for quick actions, notifications, and user profile", () => {
    renderApp();

    fireEvent.click(screen.getByText("快捷操作"));
    expect(screen.getByText("刷新行情")).toBeTruthy();

    fireEvent.click(screen.getByLabelText("通知"));
    expect(screen.getByText("暂无新的真实告警")).toBeTruthy();

    fireEvent.click(screen.getByText("投资者Z"));
    expect(screen.getByText("本地研究终端")).toBeTruthy();
  });
});
