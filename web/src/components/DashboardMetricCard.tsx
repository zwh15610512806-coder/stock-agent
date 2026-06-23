import type { ReactNode } from "react";

interface DashboardMetricCardProps {
  title: string;
  value: ReactNode;
  detail?: ReactNode;
  accent?: "red" | "green" | "blue" | "neutral";
  children?: ReactNode;
}

export function DashboardMetricCard({ title, value, detail, accent = "neutral", children }: DashboardMetricCardProps) {
  return (
    <section className={`dashboard-metric metric-${accent}`}>
      <div className="dashboard-metric-title">{title}</div>
      <div className="dashboard-metric-value">{value}</div>
      {detail ? <div className="dashboard-metric-detail">{detail}</div> : null}
      {children}
    </section>
  );
}
