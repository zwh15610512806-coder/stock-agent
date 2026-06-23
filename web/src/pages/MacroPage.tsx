import { useQuery } from "@tanstack/react-query";
import { Activity, Landmark, RefreshCw, ShieldCheck, TrendingUp } from "lucide-react";
import { SourceStatusBadge } from "../components/SourceStatusBadge";
import { api } from "../lib/api";
import { formatNumber } from "../lib/format";
import type { SourceMetric } from "../lib/types";

export function MacroPage() {
  const dashboard = useQuery({
    queryKey: ["macro-dashboard"],
    queryFn: () => api.macroDashboard(),
  });
  const data = dashboard.data;

  return (
    <div className="page-stack macro-page">
      <section className="section-head macro-hero">
        <div>
          <div className="eyebrow">MACRO BOARD</div>
          <h2>宏观仪表盘</h2>
          <p>用免费公开源跟踪利率、通胀、增长、信用、债券和汇率，所有项目都保留来源与状态。</p>
        </div>
        <div className="market-hero-actions">
          <span className="market-clock">更新 {data ? new Date(data.as_of).toLocaleString("zh-CN", { hour12: false }) : "加载中"}</span>
          <SourceStatusBadge status={dashboard.isPending ? "loading" : data?.cache_status || "unavailable"} />
          <button className="terminal-button soft market-refresh" onClick={() => dashboard.refetch()} type="button">
            <RefreshCw size={15} />
            刷新
          </button>
        </div>
      </section>

      {dashboard.isError ? <div className="source-warning">宏观数据源暂不可用；页面不会展示模拟数据。</div> : null}

      <div className="metric-grid">
        <MacroMetric title="利率" icon={Landmark} items={data?.rates || []} loading={dashboard.isPending} />
        <MacroMetric title="经济指标" icon={Activity} items={data?.indicators || []} loading={dashboard.isPending} />
        <MacroMetric title="债券收益率" icon={TrendingUp} items={data?.bond_yields || []} loading={dashboard.isPending} />
        <MacroMetric title="汇率" icon={ShieldCheck} items={data?.fx_rates || []} loading={dashboard.isPending} />
      </div>

      <section className="data-panel macro-source-panel">
        <div className="panel-head">
          <div>
            <h3>数据源状态</h3>
            <span>{data?.disclaimer || "免费公开源可能延迟、缺失或被缓存。"}</span>
          </div>
        </div>
        <div className="quote-list">
          {(data?.source_status || []).map((status) => (
            <div className="quote-row" key={`${status.name}-${status.source}`}>
              <div>
                <strong>{status.name}</strong>
                <span>{status.detail || status.source}</span>
              </div>
              <div className="quote-price">
                <strong>{status.status}</strong>
                <span>{status.as_of ? new Date(status.as_of).toLocaleString("zh-CN", { hour12: false }) : "--"}</span>
              </div>
            </div>
          ))}
          {!dashboard.isPending && !data?.source_status.length ? <div className="market-empty compact">暂无真实宏观数据源状态</div> : null}
        </div>
      </section>
    </div>
  );
}

function MacroMetric({
  title,
  icon: Icon,
  items,
  loading,
}: {
  title: string;
  icon: typeof Activity;
  items: SourceMetric[];
  loading: boolean;
}) {
  return (
    <section className="data-panel macro-metric-panel">
      <div className="panel-head">
        <div>
          <h3>
            <Icon size={15} />
            {title}
          </h3>
          <span>{loading ? "加载中" : items[0]?.source || "无可用真实源"}</span>
        </div>
      </div>
      <div className="macro-metric-list">
        {loading ? <div className="market-empty compact">正在连接免费宏观源</div> : null}
        {!loading && !items.length ? <div className="market-empty compact">暂无真实数据</div> : null}
        {items.map((item) => (
          <article className="macro-metric-row" key={`${title}-${item.name}`}>
            <span>{item.name}</span>
            <strong>{item.value === null ? "--" : `${formatNumber(item.value, 2)}${item.unit}`}</strong>
            <small>
              {item.source} / {item.status} / {item.as_of || "--"}
            </small>
          </article>
        ))}
      </div>
    </section>
  );
}
