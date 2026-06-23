import type { FundFlowSummary } from "../lib/types";
import { formatMoney, formatNumber, toneForPct } from "../lib/format";

interface FundFlowListProps {
  summary: FundFlowSummary | null;
}

export function FundFlowList({ summary }: FundFlowListProps) {
  if (!summary) {
    return (
      <div className="dashboard-empty compact-empty">
        <strong>资金流不可用</strong>
        <span>个股资金流无可用真实数据或缓存。</span>
      </div>
    );
  }

  const rows = [
    ...summary.top_inflows.map((item) => ({ ...item, side: "in" as const })),
    ...summary.top_outflows.map((item) => ({ ...item, side: "out" as const })),
  ].slice(0, 8);

  return (
    <div className="fund-flow-list">
      <div className="fund-flow-total">
        <span>主力净流入合计</span>
        <strong className={summary.net_amount >= 0 ? "tone-red" : "tone-green"}>{formatMoney(summary.net_amount)}</strong>
      </div>
      {rows.map((item) => (
        <div className="fund-flow-row" key={`${item.side}-${item.symbol}-${item.name}`}>
          <div>
            <strong>{item.name}</strong>
            <span>{item.symbol || "未披露代码"}</span>
          </div>
          <div>
            <strong className={item.net_amount >= 0 ? "tone-red" : "tone-green"}>{formatMoney(item.net_amount)}</strong>
            <span className={`tone-text ${toneForPct(item.change_pct)}`}>{formatNumber(item.change_pct, 2)}%</span>
          </div>
        </div>
      ))}
    </div>
  );
}
