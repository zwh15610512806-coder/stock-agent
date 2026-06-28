import { ChangeEvent, FormEvent, useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Bot, FileUp, Plus, Trash2, UploadCloud } from "lucide-react";
import { MetricCard } from "../components/MetricCard";
import { api, apiFailureMessage } from "../lib/api";
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
  const [ocrSyncNotice, setOcrSyncNotice] = useState("");
  const [insightTarget, setInsightTarget] = useState<PortfolioPosition | null>(null);
  const analysis = useQuery({
    queryKey: ["portfolio-analysis", positions],
    queryFn: () => api.analyzePortfolio(positions),
  });
  const insightMutation = useMutation({
    mutationFn: (position: PortfolioPosition) => api.stockInsight({ position, horizon_days: 30 }),
  });
  const ocrMutation = useMutation({
    mutationFn: (file: File) => api.uploadOcr(file),
    onSuccess: (result) => {
      if (result.positions.length) {
        const syncResult = syncOcrPositionsBySymbol(positions, result.positions);
        setPositions(syncResult.positions);
        setOcrSyncNotice(
          `已同步 ${result.positions.length} 条持仓，更新 ${syncResult.updated} 条，新增 ${syncResult.added} 条，保留 ${syncResult.preserved} 条本地持仓。`,
        );
      } else {
        setOcrSyncNotice("");
      }
    },
  });

  const topWeight = useMemo(() => analysis.data?.weights[0], [analysis.data]);
  const ocrNotice = useMemo(() => {
    if (ocrMutation.isPending) {
      return "OCR 识别中...";
    }
    if (ocrMutation.isError) {
      return apiFailureMessage(ocrMutation.error, "OCR 识别");
    }
    if (!ocrMutation.data) {
      return "";
    }
    if (ocrMutation.data.positions.length) {
      return ocrSyncNotice || `已同步 ${ocrMutation.data.positions.length} 条持仓。`;
    }
    if (ocrMutation.data.message) {
      return ocrMutation.data.message;
    }
    return "OCR 未识别到可用持仓，请换一张更清晰的券商持仓截图。";
  }, [ocrMutation.data, ocrMutation.error, ocrMutation.isError, ocrMutation.isPending, ocrSyncNotice]);
  const ocrRawPreview = useMemo(() => {
    if (!ocrMutation.data || ocrMutation.data.positions.length || !ocrMutation.data.raw_lines?.length) {
      return "";
    }
    return ocrMutation.data.raw_lines
      .map((line) => line.trim())
      .filter(Boolean)
      .join("\n")
      .slice(0, 1200);
  }, [ocrMutation.data]);

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

  function analyzePosition(position: PortfolioPosition) {
    setInsightTarget(position);
    insightMutation.mutate(position);
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

      {analysis.isError ? <div className="source-warning">{apiFailureMessage(analysis.error, "持仓分析")}</div> : null}

      {(analysis.data?.data_warnings?.length || analysis.data?.quote_status?.length) ? (
        <section className="data-panel portfolio-source-panel">
          <div className="panel-head portfolio-panel-head">
            <div>
              <h3>行情刷新状态</h3>
              <span>真实源失败时保留本地现价，不使用演示兜底数据。</span>
            </div>
          </div>
          <div className="portfolio-warning-list">
            {analysis.data?.data_warnings?.map((warning) => (
              <p className="notice-text portfolio-notice" key={warning}>
                {warning}
              </p>
            ))}
          </div>
          <div className="quote-list portfolio-source-list">
            {analysis.data?.quote_status?.map((status) => (
              <div className="quote-row" key={`${status.symbol}-${status.source}`}>
                <div>
                  <strong>{status.symbol}</strong>
                  <span>{status.detail || status.source}</span>
                </div>
                <div className="quote-price">
                  <strong>{status.status}</strong>
                  <span>{status.as_of ? new Date(status.as_of).toLocaleString("zh-CN", { hour12: false }) : status.source}</span>
                </div>
              </div>
            ))}
          </div>
        </section>
      ) : null}

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
          {ocrRawPreview ? (
            <details className="portfolio-ocr-raw" open>
              <summary>AI 原始识别结果</summary>
              <pre>{ocrRawPreview}</pre>
            </details>
          ) : null}
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
                <th>可用</th>
                <th>成本价</th>
                <th>现价</th>
                <th>市值</th>
                <th>浮盈</th>
                <th>盈亏率</th>
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
                  <td>{formatOptionalNumber(position.available_quantity, 0)}</td>
                  <td>{formatNumber(position.cost_price)}</td>
                  <td>{formatNumber(position.current_price)}</td>
                  <td>{formatOptionalNumber(position.market_value)}</td>
                  <td className={`tone-text ${toneForOptional(position.pnl)}`}>{formatOptionalNumber(position.pnl)}</td>
                  <td className={`tone-text ${toneForOptional(position.pnl_pct)}`}>{formatOptionalPct(position.pnl_pct)}</td>
                  <td>
                    <button className="icon-action" onClick={() => analyzePosition(position)} aria-label={`AI分析 ${position.name || position.symbol}`}>
                      <Bot size={15} />
                    </button>
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

      {insightTarget ? (
        <section className="data-panel portfolio-insight-panel">
          <div className="panel-head portfolio-panel-head portfolio-insight-head">
            <div>
              <h3>{insightTarget.name || insightTarget.symbol} AI分析</h3>
              <span>{insightMutation.data ? `${insightMutation.data.status} / ${insightMutation.data.model}` : "联网获取最近30天走势、财报与公告"}</span>
            </div>
            <Bot size={18} />
          </div>
          {insightMutation.isPending ? <p className="notice-text portfolio-notice">正在联网分析 {insightTarget.symbol}...</p> : null}
          {insightMutation.isError ? <p className="notice-text portfolio-notice">{apiFailureMessage(insightMutation.error, "AI分析")}</p> : null}
          {insightMutation.data ? (
            <div className="portfolio-insight-body">
              <div className={`report-status ${insightMutation.data.status}`}>{insightMutation.data.summary}</div>
              <InsightList title="30日走势" items={insightMutation.data.trend} />
              <InsightList title="财报要点" items={insightMutation.data.financials} />
              <InsightList title="重要事件" items={insightMutation.data.events} />
              <InsightList title="风险提示" items={insightMutation.data.risks} warn />
              {insightMutation.data.data_warnings.length ? (
                <div className="portfolio-insight-warnings">
                  {insightMutation.data.data_warnings.map((warning) => (
                    <p className="notice-text portfolio-notice" key={warning}>
                      {warning}
                    </p>
                  ))}
                </div>
              ) : null}
              {insightMutation.data.citations.length ? (
                <div className="portfolio-insight-citations">
                  <h4>来源</h4>
                  {insightMutation.data.citations.map((citation) => (
                    <a href={citation.url} key={`${citation.url}-${citation.title}`} rel="noreferrer" target="_blank">
                      {citation.title}
                      {citation.source ? <span>{citation.source}</span> : null}
                    </a>
                  ))}
                </div>
              ) : null}
              <p className="notice-text">{insightMutation.data.disclaimer}</p>
            </div>
          ) : null}
        </section>
      ) : null}
    </div>
  );
}

function InsightList({ title, items, warn = false }: { title: string; items: string[]; warn?: boolean }) {
  if (!items.length) {
    return null;
  }
  return (
    <div className="portfolio-insight-list">
      <h4>{title}</h4>
      {items.map((item) => (
        <span className={`pill${warn ? " warn" : ""}`} key={item}>
          {item}
        </span>
      ))}
    </div>
  );
}

function syncOcrPositionsBySymbol(current: PortfolioPosition[], incoming: PortfolioPosition[]) {
  const currentSymbols = new Set(current.map((item) => normalizePortfolioSymbol(item.symbol)));
  const incomingSymbols = new Set<string>();
  const syncedIncoming: PortfolioPosition[] = [];
  let updated = 0;
  let added = 0;

  for (const position of incoming) {
    const symbol = normalizePortfolioSymbol(position.symbol);
    if (incomingSymbols.has(symbol)) {
      continue;
    }
    incomingSymbols.add(symbol);
    syncedIncoming.push({ ...position, symbol });
    if (currentSymbols.has(symbol)) {
      updated += 1;
    } else {
      added += 1;
    }
  }

  const preservedPositions = current.filter((position) => !incomingSymbols.has(normalizePortfolioSymbol(position.symbol)));
  return {
    positions: [...syncedIncoming, ...preservedPositions],
    updated,
    added,
    preserved: preservedPositions.length,
  };
}

function normalizePortfolioSymbol(symbol: string): string {
  return symbol.trim().toUpperCase();
}

function formatOptionalNumber(value: number | null | undefined, digits = 2): string {
  return typeof value === "number" && Number.isFinite(value) ? formatNumber(value, digits) : "--";
}

function formatOptionalPct(value: number | null | undefined): string {
  return typeof value === "number" && Number.isFinite(value) ? `${formatNumber(value * 100)}%` : "--";
}

function toneForOptional(value: number | null | undefined): "up" | "down" | "neutral" {
  return typeof value === "number" && Number.isFinite(value) ? toneForPct(value) : "neutral";
}
