import { describe, expect, it } from "vitest";
import {
  A_SHARE_CLOSED_REFRESH_INTERVAL_MS,
  A_SHARE_OPEN_REFRESH_INTERVAL_MS,
  getAshareRefreshIntervalMs,
} from "./refresh-schedule";

const minutes = (value: number) => value * 60 * 1000;

describe("getAshareRefreshIntervalMs", () => {
  it("refreshes every 10 minutes during A-share trading hours", () => {
    expect(getAshareRefreshIntervalMs(new Date("2026-06-22T10:00:00+08:00"))).toBe(
      A_SHARE_OPEN_REFRESH_INTERVAL_MS,
    );
    expect(getAshareRefreshIntervalMs(new Date("2026-06-22T14:30:00+08:00"))).toBe(
      A_SHARE_OPEN_REFRESH_INTERVAL_MS,
    );
  });

  it("refreshes every half day when the next A-share open is farther away", () => {
    expect(getAshareRefreshIntervalMs(new Date("2026-06-20T10:00:00+08:00"))).toBe(
      A_SHARE_CLOSED_REFRESH_INTERVAL_MS,
    );
  });

  it("waits until the next A-share session when it starts before half-day refresh", () => {
    expect(getAshareRefreshIntervalMs(new Date("2026-06-22T09:20:00+08:00"))).toBe(minutes(10));
    expect(getAshareRefreshIntervalMs(new Date("2026-06-22T12:00:00+08:00"))).toBe(minutes(60));
  });
});
