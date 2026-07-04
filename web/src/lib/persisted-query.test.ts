import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  clearPersistedQuery,
  readPersistedQuery,
  persistedQueryStorageKey,
  writePersistedQuery,
} from "./persisted-query";

describe("persisted query snapshots", () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-07-02T12:00:00Z"));
  });

  it("reads recently persisted data with its original update time", () => {
    writePersistedQuery("market-dashboard", { status: "cached" });

    const snapshot = readPersistedQuery<{ status: string }>("market-dashboard", {
      maxAgeMs: 60_000,
    });

    expect(snapshot).toEqual({
      data: { status: "cached" },
      updatedAt: new Date("2026-07-02T12:00:00Z").getTime(),
    });
  });

  it("drops expired snapshots instead of showing old market data", () => {
    writePersistedQuery("market-dashboard", { status: "too-old" }, new Date("2026-07-02T11:00:00Z").getTime());

    const snapshot = readPersistedQuery<{ status: string }>("market-dashboard", {
      maxAgeMs: 5 * 60_000,
    });

    expect(snapshot).toBeUndefined();
    expect(window.localStorage.getItem(persistedQueryStorageKey("market-dashboard"))).toBeNull();
  });

  it("ignores corrupt storage entries without breaking page render", () => {
    window.localStorage.setItem(persistedQueryStorageKey("macro-dashboard"), "{bad json");

    expect(readPersistedQuery("macro-dashboard", { maxAgeMs: 60_000 })).toBeUndefined();
    expect(window.localStorage.getItem(persistedQueryStorageKey("macro-dashboard"))).toBeNull();
  });

  it("can clear a persisted snapshot after a manual reset", () => {
    writePersistedQuery("macro-dashboard", { status: "cached" });

    clearPersistedQuery("macro-dashboard");

    expect(readPersistedQuery("macro-dashboard", { maxAgeMs: 60_000 })).toBeUndefined();
  });
});
