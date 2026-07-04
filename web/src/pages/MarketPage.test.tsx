import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../lib/api";
import type { MarketDashboardResponse, MarketNewsResponse, MarketStatusResponse, TopTurnoverResponse } from "../lib/types";
import { MarketPage } from "./MarketPage";

vi.mock("../lib/api", () => ({
  api: {
    marketDashboard: vi.fn(),
    marketStatus: vi.fn(),
    marketNews: vi.fn(),
    marketTopTurnover: vi.fn(),
  },
}));

vi.mock("../components/Heatmap", () => ({
  Heatmap: ({ data }: { data: Array<{ name: string }> }) => (
    <div data-testid="heatmap">
      heat:{data.length}
      {data.map((item) => (
        <span key={item.name}>{item.name}</span>
      ))}
    </div>
  ),
}));

const dashboard: MarketDashboardResponse = {
  as_of: "2026-06-23T15:00:00Z",
  cache_status: "stale",
  source_status: [
    { name: "a_share_activity", status: "live", source: "legulegu-market-activity", detail: "", as_of: "2026-06-23T15:00:00Z" },
    { name: "etf_heatmap", status: "live", source: "akshare-eastmoney-etf-spot", detail: "", as_of: "2026-06-23T15:00:00Z" },
    { name: "sector_heatmap", status: "live", source: "eastmoney-sector-fund-flow", detail: "", as_of: "2026-06-23T15:00:00Z" },
    { name: "region_heatmap", status: "stale", source: "eastmoney-sector-fund-flow", detail: "source down", as_of: "2026-06-23T14:40:00Z" },
    { name: "market_news", status: "live", source: "cls-telegraph", detail: "", as_of: "2026-06-23T14:57:00Z" },
    { name: "commodity_quotes", status: "live", source: "akshare-commodity", detail: "", as_of: "2026-06-23T14:57:00Z" },
    { name: "dragon_tiger", status: "live", source: "eastmoney-lhb", detail: "", as_of: "2026-06-23T15:00:00Z" },
  ],
  primary_quote: {
    symbol: "000001.SH",
    name: "上证指数",
    market: "CN",
    price: 3011.05,
    change: -18.6,
    change_pct: -0.61,
    volume: 100,
    turnover: 416310000000,
    currency: "CNY",
    source: "tencent-free-delayed",
    as_of: "2026-06-23T15:00:00Z",
    delay_label: "免费公开源",
  },
  primary_candles: [
    {
      symbol: "000001.SH",
      date: "2026-06-23",
      open: 3000,
      high: 3020,
      low: 2980,
      close: 3011.05,
      volume: 100000,
      source: "Yahoo Finance/free delayed fallback",
      delay_label: "免费公开源",
    },
  ],
  markets: [
    {
      market: "CN",
      label: "A股",
      indices: [
        {
          symbol: "000001.SH",
          name: "上证指数",
          market: "CN",
          price: 3011.05,
          change: -18.6,
          change_pct: -0.61,
          volume: 100,
          turnover: 416310000000,
          currency: "CNY",
          source: "tencent-free-delayed",
          as_of: "2026-06-23T15:00:00Z",
          delay_label: "免费公开源",
        },
      ],
      turnover: 4163.1,
      sentiment: 57.7,
      breadth: { advances: 2600, declines: 2300, unchanged: 120, limit_up: 88, limit_down: 12 },
      heatmap: [],
      source: "tencent-free-delayed",
      delay_label: "免费公开源",
      as_of: "2026-06-23T15:00:00Z",
    },
  ],
  a_share_activity: {
    advances: 2600,
    declines: 2300,
    unchanged: 120,
    limit_up: 88,
    limit_down: 12,
    suspended: 14,
    sentiment: 57.7,
    source: "legulegu-market-activity",
    as_of: "2026-06-23T15:00:00Z",
  },
  a_share_turnover: {
    value: 1024300000000,
    source: "sse-szse-summary",
    status: "live",
    as_of: "2026-06-23T15:00:00Z",
  },
  fund_flow_summary: {
    top_inflows: [{ symbol: "600519", name: "贵州茅台", change_pct: 1.2, net_amount: 346000000, turnover: 4020000000, source: "ths-fund-flow" }],
    top_outflows: [{ symbol: "300750", name: "宁德时代", change_pct: -0.5, net_amount: -20464500, turnover: 3200000000, source: "ths-fund-flow" }],
    net_amount: 325535500,
    source: "ths-fund-flow",
    as_of: "2026-06-23T15:00:00Z",
  },
  etf_heatmap: [{ name: "沪深300ETF", change_pct: 0.73, turnover: 1250000000, net_amount: 0, direction: "up", source: "akshare-eastmoney-etf-spot" }],
  industry_heatmap: [{ name: "银行", change_pct: 1.12, turnover: 21850000000, net_amount: 2250000000, direction: "up", source: "ths-fund-flow" }],
  sector_heatmap: [{ name: "软件服务", change_pct: 1.88, turnover: 28000000000, net_amount: 660000000, direction: "up", source: "eastmoney-sector-fund-flow" }],
  concept_heatmap: [{ name: "人工智能", change_pct: 2.35, turnover: 39000000000, net_amount: 3000000000, direction: "up", source: "ths-fund-flow" }],
  region_heatmap: [{ name: "上海", change_pct: 0.92, turnover: 33330000000, net_amount: 1220000000, direction: "up", source: "eastmoney-sector-fund-flow" }],
  market_news: [
    {
      title: "模型搜索快讯",
      content: "来自模型联网搜索的财经快讯",
      published_at: "2026-06-23T15:10:00+08:00",
      source: "model-web-search",
      url: "https://example.com/news/model-search",
    },
    {
      title: "央行开展公开市场操作",
      content: "维护银行体系流动性合理充裕",
      published_at: "2026-06-23T14:57:00+08:00",
      source: "cls-telegraph",
      url: "",
    },
  ],
  commodity_quotes: [
    {
      symbol: "Au99.99",
      name: "黄金连续",
      price: 917.84,
      change: 0.37,
      change_pct: 0.04,
      unit: "CNY/g",
      source: "sge-spot",
      as_of: "2026-06-23T14:57:00+08:00",
      sparkline: [917.84, 918.21],
    },
    {
      symbol: "CL00Y",
      name: "NYMEX原油",
      price: 81.4,
      change: -0.7,
      change_pct: -0.85,
      unit: "USD/bbl",
      source: "eastmoney-global-futures",
      as_of: "2026-06-23T14:57:00+08:00",
      sparkline: [82.1, 81.8, 81.4],
    },
  ],
  dragon_tiger: [
    {
      symbol: "002765",
      name: "蓝黛科技",
      sector: "汽车零部件",
      market_segment: "深主板",
      trade_date: "2026-06-23",
      close: 110.43,
      change_pct: 30,
      turnover: 4112000000,
      net_amount: 220000000,
      buy_amount: 350000000,
      sell_amount: 130000000,
      reason: "日涨幅偏离值达7%",
      source: "eastmoney-lhb",
    },
    {
      symbol: "300770",
      name: "新媒股份",
      sector: "传媒",
      market_segment: "创业板",
      trade_date: "2026-06-23",
      close: 26.1,
      change_pct: 30,
      net_amount: 120000000,
      buy_amount: 200000000,
      sell_amount: 80000000,
      turnover: 2833000000,
      reason: "日换手率达20%",
      source: "eastmoney-lhb",
    },
    {
      symbol: "000777",
      name: "流出股份",
      sector: "机械设备",
      market_segment: "深主板",
      trade_date: "2026-06-23",
      close: 8.6,
      change_pct: -7.8,
      net_amount: -530000000,
      buy_amount: 100000000,
      sell_amount: 630000000,
      turnover: 1860000000,
      reason: "日跌幅偏离值达7%",
      source: "eastmoney-lhb",
    },
    {
      symbol: "600888",
      name: "成交股份",
      sector: "高端制造",
      market_segment: "沪主板",
      trade_date: "2026-06-23",
      close: 18.4,
      change_pct: -2.1,
      net_amount: -30000000,
      buy_amount: 120000000,
      sell_amount: 150000000,
      turnover: 8890000000,
      reason: "日振幅值达15%",
      source: "eastmoney-lhb",
    },
  ],
  index_sparklines: {
    "000001.SH": [3001, 3008, 3011],
  },
  disclaimer: "免费公开源可能延迟、缺失或被缓存。",
};

const marketStatus: MarketStatusResponse = {
  ts: "2026-06-23T15:00:00Z",
  timestamp: 1782207600000,
  weekday: 2,
  weekday_name: "周二",
  data: [
    {
      market: "cn",
      name: "A股",
      is_trading: false,
      status: "closed",
      status_text: "休市",
      calendar_ok: true,
      calendar_market: "cn",
      is_trade_day: true,
      trade_date: "2026-06-23",
      prev_trade_date: "2026-06-22",
    },
    {
      market: "hk",
      name: "港股",
      is_trading: false,
      status: "closed",
      status_text: "休市",
      calendar_ok: true,
      calendar_market: "hk",
      is_trade_day: true,
      trade_date: "2026-06-23",
      prev_trade_date: "2026-06-22",
    },
  ],
};

const marketNews: MarketNewsResponse = {
  ts: "2026-06-23T15:10:00Z",
  count: 2,
  limit: 120,
  offset: 0,
  has_more: false,
  data: dashboard.market_news.map((item, index) => ({ ...item, id: `news-${index}` })),
};

const topTurnover: TopTurnoverResponse = {
  mode: "top-turnover",
  limit: 10,
  stale: false,
  tradeDate: "2026-06-23",
  data: {
    count: 2,
    items: [
      {
        code: "600519",
        symbol: "600519.SH",
        name: "贵州茅台",
        price: 1520.5,
        changePct: 1.2,
        turnoverYuan: 4020000000,
        source: "akshare-eastmoney-a-spot",
      },
      {
        code: "300750",
        symbol: "300750.SZ",
        name: "宁德时代",
        price: 210,
        changePct: -0.5,
        turnoverYuan: 3200000000,
        source: "akshare-eastmoney-a-spot",
      },
    ],
  },
  asOf: "2026-06-23T15:00:00Z",
};

function renderMarketPage() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MarketPage />
    </QueryClientProvider>,
  );
}

describe("MarketPage dashboard", () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.clearAllMocks();
    vi.mocked(api.marketStatus).mockResolvedValue(marketStatus);
    vi.mocked(api.marketNews).mockResolvedValue(marketNews);
    vi.mocked(api.marketTopTurnover).mockResolvedValue(topTurnover);
  });

  it("shows a loading state while the dashboard request is still pending", () => {
    vi.mocked(api.marketDashboard).mockReturnValue(new Promise(() => {}));

    renderMarketPage();

    expect(screen.getByText("正在加载真实市场数据")).toBeTruthy();
    expect(screen.getAllByText("正在连接免费行情源和本地 SQLite 缓存。").length).toBeGreaterThan(0);
    expect(screen.queryByText("不可用")).toBeNull();
    expect(screen.queryByText("暂无真实指数行情")).toBeNull();
  });

  it("renders the reference-style market overview from real dashboard data", async () => {
    vi.mocked(api.marketDashboard).mockResolvedValue(dashboard);

    renderMarketPage();

    expect(await screen.findByText("市场全景")).toBeTruthy();
    expect(await screen.findByText("A股")).toBeTruthy();
    expect(screen.getAllByText("休市").length).toBeGreaterThan(0);
    expect(screen.getByText("全球指数")).toBeTruthy();
    expect(screen.getByText("市场脉搏")).toBeTruthy();
    expect(await screen.findByText("1.02万亿")).toBeTruthy();
    expect(screen.getByText("成交额榜")).toBeTruthy();
    expect(screen.getAllByText("贵州茅台").length).toBeGreaterThan(0);
    expect(screen.getByText("7x24快讯")).toBeTruthy();
    expect(screen.getByText("板块热力图")).toBeTruthy();
    const heatmapLimitSelect = screen.getByLabelText("热力图显示数量") as HTMLSelectElement;
    expect(Array.from(heatmapLimitSelect.options).map((option) => option.value)).toEqual(["30", "60", "120"]);
    expect(heatmapLimitSelect.value).toBe("60");
    expect(screen.getByText("大宗商品")).toBeTruthy();
    expect(screen.getByText("龙虎榜")).toBeTruthy();
    expect((await screen.findAllByText("贵州茅台")).length).toBeGreaterThan(0);
    expect(screen.getByText("上证指数")).toBeTruthy();
    expect(screen.getAllByText(/银行/).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("tab", { name: "ETF" }));
    expect(screen.getByTestId("heatmap").textContent).toContain("沪深300ETF");
    fireEvent.click(screen.getByRole("tab", { name: "细分行业" }));
    expect(screen.getByTestId("heatmap").textContent).toContain("软件服务");
    fireEvent.click(screen.getByRole("tab", { name: "地域" }));
    expect(screen.getByTestId("heatmap").textContent).toContain("上海");
    fireEvent.click(screen.getByRole("tab", { name: "概念" }));
    expect(screen.getByTestId("heatmap").textContent).toContain("人工智能");
    expect(screen.getByText("近24小时")).toBeTruthy();
    expect(screen.getByText("已加载 2 条")).toBeTruthy();
    expect(screen.getByText("model-web-search")).toBeTruthy();
    expect(screen.getByText("模型搜索快讯")).toBeTruthy();
    expect(screen.getByText("央行开展公开市场操作")).toBeTruthy();
    expect(screen.getByText("黄金连续")).toBeTruthy();
    expect(screen.getByText("NYMEX原油")).toBeTruthy();
    expect(screen.getByText("蓝黛科技")).toBeTruthy();
    expect(screen.getAllByText(/缓存/).length).toBeGreaterThan(0);
    expect(screen.getByText(/部分免费数据源超时/)).toBeTruthy();
    expect(screen.queryByText(/数据源暂不可用/)).toBeNull();
    expect(screen.queryByText("大盘趋势")).toBeNull();
    expect(screen.queryByText("市场情绪")).toBeNull();
  });

  it("supports news paging, timeline slider, and commodity controls", async () => {
    vi.mocked(api.marketDashboard).mockResolvedValue(dashboard);
    vi.mocked(api.marketNews)
      .mockResolvedValueOnce({ ...marketNews, has_more: true })
      .mockResolvedValueOnce({
        ...marketNews,
        count: 3,
        offset: 2,
        has_more: false,
        data: [
          {
            id: "news-2",
            title: "补充快讯",
            content: "加载更多返回的真实快讯",
            published_at: "2026-06-23T13:00:00+08:00",
            source: "danginvest-public-fallback",
            url: "",
          },
        ],
      });

    renderMarketPage();

    expect(await screen.findByLabelText("快讯时间轴")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("快讯时间轴"), { target: { value: "50" } });
    expect(screen.getByText(/定位 50%/)).toBeTruthy();

    fireEvent.click(await screen.findByRole("button", { name: "加载更多" }));
    expect(api.marketNews).toHaveBeenLastCalledWith(120, 2);
    expect(await screen.findByText("补充快讯")).toBeTruthy();

    expect(screen.getByRole("button", { name: "贵金属" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "海外" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "海外" }));
    expect(screen.getByText("NYMEX原油")).toBeTruthy();
    expect(screen.queryByText("黄金连续")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "周线" }));
    expect(screen.getByText("周期 周线")).toBeTruthy();
  });

  it("refreshes dashboard side queries including news", async () => {
    vi.mocked(api.marketDashboard).mockResolvedValue(dashboard);

    renderMarketPage();

    await screen.findByText("市场全景");
    const newsCalls = vi.mocked(api.marketNews).mock.calls.length;
    const statusCalls = vi.mocked(api.marketStatus).mock.calls.length;
    const turnoverCalls = vi.mocked(api.marketTopTurnover).mock.calls.length;

    fireEvent.click(screen.getByRole("button", { name: "刷新" }));

    await waitFor(() => {
      expect(vi.mocked(api.marketNews).mock.calls.length).toBeGreaterThan(newsCalls);
      expect(vi.mocked(api.marketStatus).mock.calls.length).toBeGreaterThan(statusCalls);
      expect(vi.mocked(api.marketTopTurnover).mock.calls.length).toBeGreaterThan(turnoverCalls);
    });
  });

  it("does not show page warning when only optional sources are unavailable", async () => {
    vi.mocked(api.marketDashboard).mockResolvedValue({
      ...dashboard,
      cache_status: "live",
      market_news: [],
      source_status: [
        ...dashboard.source_status
          .filter((status) => status.name !== "market_news")
          .map((status) => ({ ...status, status: "live" as const, detail: "" })),
        { name: "market_news", status: "unavailable", source: "model-web-search/akshare-news", detail: "source down", as_of: null },
      ],
    });

    const view = renderMarketPage();

    await screen.findByText(dashboard.primary_quote!.name);
    expect(view.container.querySelector(".source-warning")).toBeNull();
  });

  it("shows unavailable modules without fake data", async () => {
    vi.mocked(api.marketDashboard).mockResolvedValue({
      ...dashboard,
      cache_status: "partial",
      a_share_activity: null,
      fund_flow_summary: null,
      etf_heatmap: [],
      industry_heatmap: [],
      sector_heatmap: [],
      concept_heatmap: [],
      region_heatmap: [],
      market_news: [],
      commodity_quotes: [],
      dragon_tiger: [],
      index_sparklines: {},
      source_status: [
        { name: "industry_heatmap", status: "unavailable", source: "ths-fund-flow", detail: "source down", as_of: null },
      ],
    });

    renderMarketPage();

    expect(await screen.findByText(/部分免费数据源暂不可用/)).toBeTruthy();
    expect(screen.getByText("暂无真实快讯")).toBeTruthy();
    expect(screen.getByText("暂无真实商品行情")).toBeTruthy();
    expect(screen.getByText("暂无真实龙虎榜")).toBeTruthy();
    expect(screen.queryByText("样例")).toBeNull();
  });

  it("sorts the dragon tiger list by fund flow, price move, and turnover", async () => {
    vi.mocked(api.marketDashboard).mockResolvedValue(dashboard);

    renderMarketPage();

    expect(await screen.findByText("蓝黛科技")).toBeTruthy();
    expect(firstDragonName()).toBe("蓝黛科技");
    expect(within(screen.getAllByTestId("dragon-row")[0]).getByText("汽车零部件")).toBeTruthy();
    expect(within(screen.getAllByTestId("dragon-row")[0]).getByText("深主板")).toBeTruthy();
    expect(screen.queryByTestId("mini-kline")).toBeNull();
    expect(screen.queryByText("暂无K线")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "净流出" }));
    expect(firstDragonName()).toBe("流出股份");

    fireEvent.click(screen.getByRole("button", { name: "上涨%" }));
    expect(firstDragonName()).toBe("蓝黛科技");
    expect(screen.queryByText("流出股份")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "下跌%" }));
    expect(firstDragonName()).toBe("流出股份");

    fireEvent.click(screen.getByRole("button", { name: "成交额" }));
    expect(firstDragonName()).toBe("成交股份");
    expect(screen.getAllByText("成交额").length).toBeGreaterThan(1);
    expect(screen.getByText("88.90 亿")).toBeTruthy();
    expect(within(screen.getAllByTestId("dragon-row")[0]).getByText("沪主板")).toBeTruthy();
  });
});

function firstDragonName(): string {
  return screen.getAllByTestId("dragon-row")[0].querySelector("strong")?.textContent || "";
}
