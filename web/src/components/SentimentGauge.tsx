import type { AShareActivity } from "../lib/types";
import { formatNumber } from "../lib/format";

interface SentimentGaugeProps {
  activity: AShareActivity | null;
}

export function SentimentGauge({ activity }: SentimentGaugeProps) {
  if (!activity) {
    return (
      <div className="dashboard-empty">
        <strong>数据源暂不可用</strong>
        <span>赚钱效应源不可用，且没有可展示的真实缓存。</span>
      </div>
    );
  }

  const sentiment = Math.max(0, Math.min(100, activity.sentiment));
  const rotation = -90 + sentiment * 1.8;

  return (
    <div className="sentiment-gauge">
      <div className="gauge-arc">
        <div className="gauge-needle" style={{ transform: `rotate(${rotation}deg)` }} />
        <div className="gauge-value">
          <strong>{formatNumber(sentiment, 1)}</strong>
          <span>{sentiment >= 65 ? "偏乐观" : sentiment >= 45 ? "中性偏乐观" : "偏谨慎"}</span>
        </div>
      </div>
      <div className="gauge-scale">
        <span>0</span>
        <span>50</span>
        <span>100</span>
      </div>
      <div className="breadth-grid">
        <div>
          <span>上涨家数</span>
          <strong className="tone-red">{activity.advances}</strong>
        </div>
        <div>
          <span>平盘家数</span>
          <strong>{activity.unchanged}</strong>
        </div>
        <div>
          <span>下跌家数</span>
          <strong className="tone-green">{activity.declines}</strong>
        </div>
      </div>
      <div className="breadth-grid compact">
        <div>
          <span>涨停</span>
          <strong className="tone-red">{activity.limit_up}</strong>
        </div>
        <div>
          <span>跌停</span>
          <strong className="tone-green">{activity.limit_down}</strong>
        </div>
        <div>
          <span>停牌</span>
          <strong>{activity.suspended}</strong>
        </div>
      </div>
    </div>
  );
}
