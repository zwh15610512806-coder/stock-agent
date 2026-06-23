import { ChangeEvent, FormEvent, useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { FileUp, Plus, Trash2, UploadCloud } from "lucide-react";
import { MetricCard } from "../components/MetricCard";
import { api } from "../lib/api";
import { parsePositionsCsv } from "../lib/csv";
import { currencyForMarket } from "../lib/csv";
import { formatNumber, toneForPct } from "../lib/format";
import { usePortfolioStore } from "../lib/store";
import type { MarketCode, PortfolioPosition } from "../lib/types";

export function PortfolioPage() {
  const { positions, addPosition, removePosition, setPositions, clear } = usePortfolioStore();
  const [draft, setDraft] = useState<PortfolioPosition>({
    symbol: "600519.SH",
    name: "贵州茅台",
    market: "CN",
    quantity: 10,
    cost_price: 1000,
    current_price: 1200,
    currency: "CNY",
  });
  const analysis = useQuery({
    queryKey: ["portfolio-analysis", positions],
    queryFn: () => api.analyzePortfolio(positions),
  });
  const ocrMutation = useMutation({
    mutationFn: (file: File) => api.uploadOcr(file),
    onSuccess: (result) => {
      if (result.positions.length) {
        setPositions([...positions, ...result.positions]);
      }
    },
  });

  const topWeight = useMemo(() => analysis.data?.weights[0], [analysis.data]);
  const ocrNotice = useMemo(() => {
    if (ocrMutation.isPending) {
      return "OCR 识别中...";
    }
    if (ocrMutation.isError) {
      return "OCR 上传失败，请检查后端服务或网络连接。";
    }
    if (!ocrMutation.data) {
      return "";
    }
    if (ocrMutation.data.message) {
      return ocrMutation.data.message;
    }
    if (ocrMutation.data.positions.length) {
      return `OCR 已导入 ${ocrMutation.data.positions.length} 条持仓草稿。`;
    }
    return "OCR 未识别到可用持仓，请换一张更清晰的券商持仓截图。";
  }, [ocrMutation.data, ocrMutation.isError, ocrMutation.isPending]);

  function submit(event: FormEvent) {
    event.preventDefault();
    addPosition({ ...draft, symbol: draft.symbol.toUpperCase(), currency: currencyForMarket(draft.market) });
  }

  function onCsvFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }
    file.text().then((text) => setPositions([...positions, ...parsePositionsCsv(text)]));
    event.target.value = "";
  }

  function onOcrFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (file) {
      ocrMutation.mutate(file);
    }
    event.target.value = "";
  }

  return (
    <div className="page-stack portfolio-page">
      <section className="section-head portfolio-hero">
        <div className="portfolio-hero-copy">
          <div className="eyebrow">LOCAL PORTFOLIO</div>
          <h2>组合分析</h2>
          <p>持仓仅保存在本地浏览器。后端只接收当前请求用于计算、OCR 或 AI 报告上下文。</p>
        </div>
        <div className="button-cluster portfolio-import-controls">
          <label className="terminal-button ghost portfolio-import-action">
            <FileUp size={16} />
            CSV
            <input hidden type="file" accept=".csv,text/csv" onChange={onCsvFile} />
          </label>
          <label className="terminal-button ghost portfolio-import-action">
            <UploadCloud size={16} />
            截图AI识别
            <input hidden type="file" accept="image/*" onChange={onOcrFile} />
          </label>
        </div>
      </section>

      <div className="metric-grid portfolio-metrics">
        <MetricCard label="总市值" value={formatNumber(analysis.data?.total_value || 0)} detail="后端免费行情刷新" />
        <MetricCard
          label="浮动盈亏"
          value={formatNumber(analysis.data?.pnl || 0)}
          detail={`${formatNumber((analysis.data?.pnl_pct || 0) * 100)}%`}
          tone={toneForPct(analysis.data?.pnl || 0)}
        />
        <MetricCard label="持仓数" value={positions.length} detail="本地浏览器存储" />
        <MetricCard label="最大权重" value={topWeight ? `${formatNumber(topWeight.weight * 100)}%` : "--"} detail={topWeight?.name || "--"} />
      </div>

      <div className="two-column portfolio-tool-grid">
        <section className="data-panel portfolio-entry-panel">
          <div className="panel-head portfolio-panel-head">
            <div>
              <h3>新增持仓</h3>
              <span>手动录入</span>
            </div>
          </div>
          <form className="position-form portfolio-position-form" onSubmit={submit}>
            <input value={draft.symbol} onChange={(event) => setDraft({ ...draft, symbol: event.target.value })} placeholder="代码" />
            <input value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} placeholder="名称" />
            <select
              value={draft.market}
              onChange={(event) =>
                setDraft({ ...draft, market: event.target.value as MarketCode, currency: currencyForMarket(event.target.value as MarketCode) })
              }
            >
              <option value="CN">A股</option>
              <option value="HK">港股</option>
              <option value="US">美股</option>
            </select>
            <input type="number" value={draft.quantity} onChange={(event) => setDraft({ ...draft, quantity: Number(event.target.value) })} />
            <input type="number" value={draft.cost_price} onChange={(event) => setDraft({ ...draft, cost_price: Number(event.target.value) })} />
            <input type="number" value={draft.current_price} onChange={(event) => setDraft({ ...draft, current_price: Number(event.target.value) })} />
            <button className="terminal-button portfolio-submit-action" type="submit">
              <Plus size={16} />
              添加
            </button>
          </form>
          {ocrNotice ? <p className="notice-text portfolio-notice">{ocrNotice}</p> : null}
        </section>

        <section className="data-panel portfolio-risk-panel">
          <div className="panel-head portfolio-panel-head">
            <div>
              <h3>风险提示</h3>
              <span>{analysis.data?.disclaimer || "仅供研究参考"}</span>
            </div>
          </div>
          <div className="risk-list portfolio-risk-list">
            {analysis.data?.risks.map((risk) => (
              <div className={`risk-item portfolio-risk-item ${risk.level}`} key={risk.title}>
                <strong>{risk.title}</strong>
                <span>{risk.detail}</span>
              </div>
            ))}
            {analysis.data?.suggestions.map((item) => (
              <div className="risk-item portfolio-risk-item" key={item}>
                <strong>观察建议</strong>
                <span>{item}</span>
              </div>
            ))}
          </div>
        </section>
      </div>

      <section className="data-panel portfolio-holdings-panel">
        <div className="panel-head portfolio-panel-head portfolio-holdings-head">
          <div>
            <h3>持仓明细</h3>
            <span>{positions.length} 条本地记录</span>
          </div>
          <button className="terminal-button ghost portfolio-clear-action" onClick={clear}>
            清空
          </button>
        </div>
        <div className="table-wrap portfolio-table-wrap">
          <table className="portfolio-table">
            <thead>
              <tr>
                <th>代码</th>
                <th>名称</th>
                <th>市场</th>
                <th>数量</th>
                <th>成本价</th>
                <th>现价</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {positions.map((position) => (
                <tr key={position.symbol}>
                  <td>{position.symbol}</td>
                  <td>{position.name}</td>
                  <td>{position.market}</td>
                  <td>{formatNumber(position.quantity, 0)}</td>
                  <td>{formatNumber(position.cost_price)}</td>
                  <td>{formatNumber(position.current_price)}</td>
                  <td>
                    <button className="icon-action" onClick={() => removePosition(position.symbol)} aria-label="删除持仓">
                      <Trash2 size={15} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
