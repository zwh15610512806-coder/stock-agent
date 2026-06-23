import type { DashboardCacheStatus, DashboardSourceStatus } from "../lib/types";

interface SourceStatusBadgeProps {
  status: DashboardCacheStatus | DashboardSourceStatus["status"];
  label?: string;
}

const statusLabel: Record<DashboardCacheStatus | DashboardSourceStatus["status"], string> = {
  live: "实时",
  stale: "缓存",
  partial: "部分可用",
  unavailable: "不可用",
};

export function SourceStatusBadge({ status, label }: SourceStatusBadgeProps) {
  return (
    <span className={`source-badge source-${status}`}>
      {label || statusLabel[status]}
    </span>
  );
}
