import { FormEvent, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Bot, FileText, Sparkles } from "lucide-react";
import { EmptyState } from "../components/EmptyState";
import { api } from "../lib/api";
import { usePortfolioStore } from "../lib/store";
import type { AiReportAnalysisSkill, MarketCode } from "../lib/types";

export function AiPage() {
  const positions = usePortfolioStore((state) => state.positions);
  const [symbol, setSymbol] = useState("600519.SH");
  const [market, setMarket] = useState<MarketCode>("CN");
  const [analysisSkill, setAnalysisSkill] = useState<AiReportAnalysisSkill>("standard");
  const reportMutation = useMutation({
    mutationFn: async () => {
      const quoteResponse = await api.compatQuotes([symbol]);
      const candleResponse = await api.compatDailySeries([symbol], 120);
      return api.createAiReport({
        symbol,
        market,
        analysis_skill: analysisSkill,
        quote: quoteResponse.items[0] || null,
        candles: candleResponse.series[0]?.items || [],
        portfolio_positions: positions,
        horizon: "中短线波段",
        risk_profile: "稳健",
      });
    },
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    reportMutation.mutate();
  }

  const report = reportMutation.data;
  const selectedSkillLabel = analysisSkill === "serenity" ? "serenity-skill" : "标准分析";
  const reportSkillLabel =
    report?.metadata?.skill_label || (report?.metadata?.analysis_skill === "serenity" ? "serenity-skill" : "标准分析");

  return (
    <div className="page-stack ai-research-page">
      <section className="section-head">
        <div>
          <div className="eyebrow">DEEPSEEK REPORT</div>
          <h2>AI 研究报告</h2>
          <p>
            后端固定接入 DeepSeek，浏览器不接触 API Key。可启用 serenity-skill，让报告按网页 PPT
            式强结构分析输出。报告只做研究辅助，不输出承诺性交易信号。
          </p>
        </div>
        <form className="terminal-search" onSubmit={submit}>
          <select value={market} onChange={(event) => setMarket(event.target.value as MarketCode)}>
            <option value="CN">A股</option>
            <option value="HK">港股</option>
            <option value="US">美股</option>
          </select>
          <input value={symbol} onChange={(event) => setSymbol(event.target.value.toUpperCase())} />
          <label className={`skill-option ${analysisSkill === "serenity" ? "enabled" : ""}`}>
            <input
              checked={analysisSkill === "serenity"}
              onChange={(event) => setAnalysisSkill(event.target.checked ? "serenity" : "standard")}
              type="checkbox"
            />
            <Sparkles size={15} />
            <span>启用 serenity-skill</span>
          </label>
          <button className="terminal-button" type="submit" disabled={reportMutation.isPending}>
            <Bot size={16} />
            {reportMutation.isPending ? "生成中" : "生成报告"}
          </button>
        </form>
      </section>

      {reportMutation.isError ? <EmptyState title="报告生成失败" body="请检查后端、DeepSeek 配置或网络状态。" /> : null}

      <section className="data-panel report-panel">
        <div className="panel-head">
          <div>
            <h3>报告结果</h3>
            <span>{report ? `${report.status} / ${report.model} / ${reportSkillLabel}` : `等待生成 / ${selectedSkillLabel}`}</span>
          </div>
          <FileText size={18} />
        </div>
        {report ? (
          <>
            <div className={`report-status ${report.status}`}>{report.summary}</div>
            <div className="report-grid">
              <div>
                <h4>观察指标</h4>
                {report.watch_metrics.map((item) => (
                  <span className="pill" key={item}>{item}</span>
                ))}
              </div>
              <div>
                <h4>风险</h4>
                {report.risks.map((item) => (
                  <span className="pill warn" key={item}>{item}</span>
                ))}
              </div>
            </div>
            {report.sections.map((section) => (
              <article className="report-section" key={section.title}>
                <h4>{section.title}</h4>
                <p>{section.body}</p>
              </article>
            ))}
            <p className="notice-text">{report.disclaimer}</p>
          </>
        ) : (
          <EmptyState title="暂无报告" body="输入代码并生成，报告会结合行情、K线和本地组合上下文。" />
        )}
      </section>
    </div>
  );
}
