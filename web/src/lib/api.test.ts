import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, apiFailureMessage, getApiErrorKind, isApiError } from "./api";

describe("api client error classification", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("classifies network failures as backend connectivity errors", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));

    await expect(api.health()).rejects.toMatchObject({ kind: "network" });

    try {
      await api.health();
    } catch (error) {
      expect(isApiError(error)).toBe(true);
      expect(getApiErrorKind(error)).toBe("network");
    }
  });

  it("classifies non-2xx responses as http errors and preserves body text", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("backend down", { status: 503, statusText: "Service Unavailable" })),
    );

    await expect(api.sourcesStatus()).rejects.toMatchObject({
      kind: "http",
      status: 503,
      body: "backend down",
    });
  });

  it("classifies OCR upload network failures as backend connectivity errors", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));

    await expect(api.uploadOcr(new File(["image"], "positions.png", { type: "image/png" }))).rejects.toMatchObject({
      kind: "network",
    });
  });

  it("exposes ApiError for direct construction in UI helpers", () => {
    const error = new ApiError("Bad JSON", "parse");

    expect(isApiError(error)).toBe(true);
    expect(getApiErrorKind(error)).toBe("parse");
  });

  it("maps network and http failures to reader-facing source messages", () => {
    expect(apiFailureMessage(new ApiError("offline", "network"), "宏观数据")).toContain("后端未连接");
    expect(apiFailureMessage(new ApiError("HTTP 503", "http", { status: 503 }), "选股器")).toContain("HTTP 503");
    expect(apiFailureMessage(new Error("boom"), "持仓分析")).toContain("持仓分析暂不可用");
  });
  it("requests macro timeseries and X-Ray endpoints with query parameters", async () => {
    const fetch = vi.fn().mockImplementation(() => Promise.resolve(new Response("{}", { status: 200 })));
    vi.stubGlobal("fetch", fetch);

    await api.macroTimeseries({
      series_ids: ["cn.money.m1_yoy", "cn.ppi.yoy"],
      start: "2026-01-01",
      end: "2026-06-30",
      max_points: 40,
    });
    await api.macroXray({ universe_type: "industry", universe_code: "BK1036", scope: "non_financial" });
    await api.macroXrayTargets({ universe_type: "all", lookback: 6 });

    expect(fetch).toHaveBeenNthCalledWith(
      1,
      "/api/market/macro-timeseries?series_ids=cn.money.m1_yoy%2Ccn.ppi.yoy&start=2026-01-01&end=2026-06-30&max_points=40",
      expect.any(Object),
    );
    expect(fetch).toHaveBeenNthCalledWith(
      2,
      "/api/market/macro-xray?universe_type=industry&universe_code=BK1036&scope=non_financial",
      expect.any(Object),
    );
    expect(fetch).toHaveBeenNthCalledWith(
      3,
      "/api/market/macro-xray/targets?universe_type=all&lookback=6",
      expect.any(Object),
    );
  });

  it("requests DangInvest-style market endpoints with stable query parameters", async () => {
    const fetch = vi.fn().mockImplementation(() => Promise.resolve(new Response("{}", { status: 200 })));
    vi.stubGlobal("fetch", fetch);

    await api.marketStatus();
    await api.marketDashboardRealtime();
    await api.marketIntraday(["indices-cn", "indices-hk"]);
    await api.marketNews(120, 40);
    await api.marketTopTurnover("cn", 20, "2026-07-02");
    await api.marketDateSnapshot("2026-07-02");

    expect(fetch).toHaveBeenNthCalledWith(1, "/api/market/status", expect.any(Object));
    expect(fetch).toHaveBeenNthCalledWith(2, "/api/market/dashboard/realtime", expect.any(Object));
    expect(fetch).toHaveBeenNthCalledWith(
      3,
      "/api/market/dashboard/intraday?groups=indices-cn%2Cindices-hk",
      expect.any(Object),
    );
    expect(fetch).toHaveBeenNthCalledWith(4, "/api/market/news?limit=120&offset=40", expect.any(Object));
    expect(fetch).toHaveBeenNthCalledWith(
      5,
      "/api/market/stocks/top-turnover?market=cn&limit=20&date=2026-07-02",
      expect.any(Object),
    );
    expect(fetch).toHaveBeenNthCalledWith(6, "/api/market?date=2026-07-02", expect.any(Object));
  });
});
