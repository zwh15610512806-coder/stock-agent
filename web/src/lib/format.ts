export function formatNumber(value: number, digits = 2): string {
  return Number(value || 0).toLocaleString("zh-CN", {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  });
}

export function formatCompact(value: number): string {
  return Number(value || 0).toLocaleString("zh-CN", {
    notation: "compact",
    maximumFractionDigits: 2,
  });
}

export function formatMoney(value: number): string {
  const abs = Math.abs(value || 0);
  if (abs >= 100000000) {
    return `${formatNumber(value / 100000000, 2)} 亿`;
  }
  if (abs >= 10000) {
    return `${formatNumber(value / 10000, 2)} 万`;
  }
  return formatNumber(value, 2);
}

export function toneForPct(value: number): "up" | "down" | "neutral" {
  if (value > 0) {
    return "up";
  }
  if (value < 0) {
    return "down";
  }
  return "neutral";
}
