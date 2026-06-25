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
});
