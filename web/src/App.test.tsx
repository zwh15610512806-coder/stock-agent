import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
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

describe("App broker terminal shell", () => {
  it("renders reference-style navigation and top command controls", () => {
    renderApp();

    expect(screen.getByText("市场总览")).toBeTruthy();
    expect(screen.queryByText("市场")).toBeNull();
    expect(screen.getByText("AI 投顾")).toBeTruthy();
    expect(screen.getByPlaceholderText("搜索股票 / 指数 / 板块 / 资讯")).toBeTruthy();
    expect(screen.getByDisplayValue("2024-06-20")).toBeTruthy();
    expect(screen.getByText("自定义视图")).toBeTruthy();
  });

  it("redirects the removed market page route back to the overview", async () => {
    renderApp("/macro");

    expect(await screen.findByText("市场全景")).toBeTruthy();
    expect(screen.queryByText("宏观与跨市场观察")).toBeNull();
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
