import { useQuery } from "@tanstack/react-query";
import { MetricCard } from "../components/MetricCard";
import { api } from "../lib/api";
import { formatNumber } from "../lib/format";

export function MacroPage() {
  const overview = useQuery({
    queryKey: ["macro-overview"],
    queryFn: () => api.marketOverview(),
  });

  const cn = overview.data?.markets.find((item) => item.market === "CN");
  const hk = overview.data?.markets.find((item) => item.market === "HK");
  const us = overview.data?.markets.find((item) => item.market === "US");

  return (
    <div className="page-stack">
      <section className="section-head">
        <div>
          <div className="eyebrow">MACRO BOARD</div>
          <h2>宏观与跨市场观察</h2>
          <p>首版以跨市场指数、情绪温度和风险提示为主，利率、汇率、期货扩展口径保留在后端接口之后迭代。</p>
        </div>
      </section>

      <div className="metric-grid">
        <MetricCard label="A股情绪温度" value={formatNumber(cn?.sentiment || 0, 1)} detail={cn?.delay_label} />
        <MetricCard label="港股情绪温度" value={formatNumber(hk?.sentiment || 0, 1)} detail={hk?.delay_label} />
        <MetricCard label="美股情绪温度" value={formatNumber(us?.sentiment || 0, 1)} detail={us?.delay_label} />
      </div>

      <section className="data-panel">
        <div className="panel-head">
          <div>
            <h3>宏观观察清单</h3>
            <span>用于 AI 报告和人工复核的观察项</span>
          </div>
        </div>
        <div className="checklist-grid">
          {[
            "A/H/US 指数是否同向突破或背离",
            "两地互联网、半导体、金融板块是否共振",
            "组合最大持仓是否与市场主线一致",
            "免费行情出现缺失时是否回退到演示数据",
            "AI 报告是否明确列出风险和观察指标",
            "公网访问不展示任何后端密钥",
          ].map((item) => (
            <div className="check-item" key={item}>
              <span />
              {item}
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
