const MINUTE_MS = 60 * 1000;
const HOUR_MS = 60 * MINUTE_MS;
const SHANGHAI_UTC_OFFSET_MS = 8 * HOUR_MS;

const MORNING_OPEN_MINUTE = 9 * 60 + 30;
const MORNING_CLOSE_MINUTE = 11 * 60 + 30;
const AFTERNOON_OPEN_MINUTE = 13 * 60;
const AFTERNOON_CLOSE_MINUTE = 15 * 60;

export const A_SHARE_OPEN_REFRESH_INTERVAL_MS = 10 * MINUTE_MS;
export const A_SHARE_CLOSED_REFRESH_INTERVAL_MS = 12 * HOUR_MS;
export const A_SHARE_REFRESH_POLICY_LABEL = "A-share 10m open / 12h closed";
export const A_SHARE_REFRESH_POLICY_DETAIL =
  "Open sessions refresh every 10 minutes; pre-open and lunch wait until the next session; closed sessions refresh at most every 12 hours.";

export function getAshareRefreshIntervalMs(now = new Date()): number {
  const shanghaiNow = toShanghaiDate(now);
  const day = shanghaiNow.getUTCDay();
  const minuteOfDay = shanghaiNow.getUTCHours() * 60 + shanghaiNow.getUTCMinutes();
  const isWeekday = day >= 1 && day <= 5;

  if (
    isWeekday &&
    ((minuteOfDay >= MORNING_OPEN_MINUTE && minuteOfDay < MORNING_CLOSE_MINUTE) ||
      (minuteOfDay >= AFTERNOON_OPEN_MINUTE && minuteOfDay < AFTERNOON_CLOSE_MINUTE))
  ) {
    return A_SHARE_OPEN_REFRESH_INTERVAL_MS;
  }

  const nextOpenDelay = getNextAshareOpenDelayMs(now, shanghaiNow, day, minuteOfDay, isWeekday);
  return Math.min(nextOpenDelay, A_SHARE_CLOSED_REFRESH_INTERVAL_MS);
}

function getNextAshareOpenDelayMs(
  now: Date,
  shanghaiNow: Date,
  day: number,
  minuteOfDay: number,
  isWeekday: boolean,
): number {
  if (isWeekday && minuteOfDay < MORNING_OPEN_MINUTE) {
    return delayUntilShanghaiMinute(now, shanghaiNow, 0, MORNING_OPEN_MINUTE);
  }

  if (isWeekday && minuteOfDay >= MORNING_CLOSE_MINUTE && minuteOfDay < AFTERNOON_OPEN_MINUTE) {
    return delayUntilShanghaiMinute(now, shanghaiNow, 0, AFTERNOON_OPEN_MINUTE);
  }

  const daysUntilNextWeekday = day >= 5 ? 8 - day : 1;
  return delayUntilShanghaiMinute(now, shanghaiNow, daysUntilNextWeekday, MORNING_OPEN_MINUTE);
}

function delayUntilShanghaiMinute(now: Date, shanghaiNow: Date, daysToAdd: number, minuteOfDay: number): number {
  const targetUtcMs =
    Date.UTC(
      shanghaiNow.getUTCFullYear(),
      shanghaiNow.getUTCMonth(),
      shanghaiNow.getUTCDate() + daysToAdd,
      Math.floor(minuteOfDay / 60),
      minuteOfDay % 60,
    ) - SHANGHAI_UTC_OFFSET_MS;
  return Math.max(0, targetUtcMs - now.getTime());
}

function toShanghaiDate(value: Date): Date {
  return new Date(value.getTime() + SHANGHAI_UTC_OFFSET_MS);
}
