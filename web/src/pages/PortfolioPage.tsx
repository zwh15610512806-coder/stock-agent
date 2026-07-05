import { ChangeEvent, FormEvent, Fragment, useMemo, useState } from "react";
import { useMutation, useQuery, type UseMutationResult } from "@tanstack/react-query";
import { Bot, Plus, Trash2, UploadCloud } from "lucide-react";
import { MetricCard } from "../components/MetricCard";
import { api, apiFailureMessage } from "../lib/api";
import { currencyForMarket } from "../lib/csv";
import { formatNumber, toneForPct } from "../lib/format";
import { usePortfolioStore } from "../lib/store";
import type { MarketCode, OcrPortfolioSummary, PortfolioPosition, StockInsightResponse } from "../lib/types";

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
        const suffix = result.message ? ` ${result.message}` : "";
        setOcrSyncNotice(
          `已同步 ${result.positions.length} 条持仓，更新 ${syncResult.updated} 条，新增 ${syncResult.added} 条，保留 ${syncResult.preserved} 条本地持仓。${suffix}`,
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
  const watchlistMetricPositions = useMemo(() => {
    const recentOcrWatchlist = ocrMutation.data?.positions.filter(isWatchlistPosition) || [];
    return recentOcrWatchlist.length ? recentOcrWatchlist : positions.filter(isWatchlistPosition);
  }, [ocrMutation.data, positions]);
  const ocrPortfolioSummary = ocrMutation.data?.portfolio_summary ?? null;
  const ocrUnmatchedRows = ocrMutation.data?.unmatched_rows || [];
  const screenshotSummary = useMemo(
    () => (watchlistMetricPositions.length ? buildScreenshotSummary(watchlistMetricPositions) : null),
    [watchlistMetricPositions],
  );

  function submit(event: FormEvent) {
    event.preventDefault();
    addPosition({ ...draft, symbol: draft.symbol.toUpperCase(), currency: currencyForMarket(draft.market) });
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
            <UploadCloud size={16} />
            截图AI识别
            <input hidden type="file" accept="image/*" onChange={onOcrFile} />
          </label>
        </div>
      </section>

      <div className="metric-grid portfolio-metrics">
        {ocrPortfolioSummary ? (
          <BrokerOcrMetrics summary={ocrPortfolioSummary} unmatchedCount={ocrUnmatchedRows.length} positionsCount={positions.length} topWeight={topWeight} />
        ) : screenshotSummary ? (
          <>
            <MetricCard label="识别股票" value={screenshotSummary.count} detail="截图AI识别" />
            <MetricCard label="最新价合计" value={formatNumber(screenshotSummary.latestTotal)} detail="非市值，仅为截图价格求和" />
            <MetricCard
              label="上涨/下跌"
              value={`${screenshotSummary.upCount} / ${screenshotSummary.downCount}`}
              detail={`${screenshotSummary.flatCount} 只平盘或未知`}
              tone={screenshotSummary.upCount >= screenshotSummary.downCount ? "up" : "down"}
            />
            <MetricCard label="数据完整度" value="行情列表" detail="缺少数量/成本，请补充真实持仓" />
          </>
        ) : (
          <>
            <MetricCard label="总市值" value={formatNumber(analysis.data?.total_value || 0)} detail="后端免费行情刷新" />
            <MetricCard
              label="浮动盈亏"
              value={formatNumber(analysis.data?.pnl || 0)}
              detail={`${formatNumber((analysis.data?.pnl_pct || 0) * 100)}%`}
              tone={toneForPct(analysis.data?.pnl || 0)}
            />
            <MetricCard label="持仓数" value={positions.length} detail="本地浏览器存储" />
            <MetricCard label="最大权重" value={topWeight ? `${formatNumber(topWeight.weight * 100)}%` : "--"} detail={topWeight?.name || "--"} />
          </>
        )}
      </div>

      <section className="data-panel portfolio-main-workspace">
        {analysis.isError ? <div className="source-warning">{apiFailureMessage(analysis.error, "持仓分析")}</div> : null}

        <section className="portfolio-holdings-panel portfolio-workspace-section">
          <div className="panel-head portfolio-panel-head portfolio-holdings-head">
            <div>
              <h3>持仓明细</h3>
              <span>{positions.length} 条本地记录</span>
            </div>
            <button className="terminal-button ghost portfolio-clear-action" onClick={clear}>
              清空
            </button>
          </div>
          <div className="table-wrap portfolio-table-wrap portfolio-holdings-table-wrap">
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
                {positions.map((position) => {
                  const key = positionKey(position);
                  const isInsightActive = insightTarget ? positionKey(insightTarget) === key : false;
                  const isInsightPending = isInsightActive && insightMutation.isPending;
                  return (
                    <Fragment key={key}>
                      <tr data-insight-active={isInsightActive ? "true" : undefined}>
                    <td className="portfolio-code-cell">{position.symbol}</td>
                    <td className="portfolio-name-cell">{position.name}</td>
                    <td>{position.market}</td>
                    <td>{formatNumber(position.quantity, 0)}</td>
                    <td>{formatOptionalNumber(position.available_quantity, 0)}</td>
                    <td>{formatNumber(position.cost_price)}</td>
                    <td>{formatNumber(position.current_price)}</td>
                    <td>{formatOptionalNumber(position.market_value)}</td>
                    <td className={`tone-text ${toneForOptional(position.pnl)}`}>{formatOptionalNumber(position.pnl)}</td>
                    <td className={`tone-text ${toneForOptional(position.pnl_pct)}`}>{formatOptionalPct(position.pnl_pct)}</td>
                    <td>
                      <button
                        className={`icon-action${isInsightActive ? " active" : ""}`}
                        onClick={() => analyzePosition(position)}
                        aria-label={`AI分析 ${position.name || position.symbol}`}
                        aria-pressed={isInsightActive}
                        disabled={isInsightPending}
                      >
                        <Bot size={15} />
                      </button>
                      <button className="icon-action" onClick={() => removePosition(position.symbol)} aria-label="删除持仓">
                        <Trash2 size={15} />
                      </button>
                    </td>
                  </tr>
                      {isInsightActive ? (
                        <tr className="portfolio-inline-insight-row">
                          <td colSpan={11}>
                            <StockInsightPanel target={position} mutation={insightMutation} />
                          </td>
                        </tr>
                      ) : null}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>

        {(analysis.data?.data_warnings?.length || analysis.data?.quote_status?.length) ? (
          <div className="portfolio-refresh-inline">
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
          </div>
        ) : null}

        <div className="portfolio-workspace-lower">
          <section className="portfolio-entry-panel portfolio-workspace-section">
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
            {ocrUnmatchedRows.length ? (
              <div className="portfolio-ocr-unmatched">
                {ocrUnmatchedRows.map((row) => (
                  <div className="risk-item portfolio-risk-item warn" key={`${row.name}-${row.reason}`}>
                    <strong>{row.name}</strong>
                    <span>{row.reason}</span>
                  </div>
                ))}
              </div>
            ) : null}
            {ocrRawPreview ? (
              <details className="portfolio-ocr-raw" open>
                <summary>AI 原始识别结果</summary>
                <pre>{ocrRawPreview}</pre>
              </details>
            ) : null}
          </section>

          <section className="portfolio-risk-panel portfolio-workspace-section">
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
      </section>

    </div>
  );
}

function BrokerOcrMetrics({
  summary,
  unmatchedCount,
  positionsCount,
  topWeight,
}: {
  summary: OcrPortfolioSummary;
  unmatchedCount: number;
  positionsCount: number;
  topWeight?: { name: string; weight: number };
}) {
  const positionRatioText = formatOptionalPct(summary.position_ratio);
  return (
    <>
      <MetricCard label="总资产" value={formatOptionalNumber(summary.total_assets)} detail={summary.currency || "截图账户摘要"} />
      <MetricCard
        label="总盈亏"
        value={formatOptionalNumber(summary.total_pnl)}
        detail={`${formatOptionalNumber(summary.day_pnl)} / ${formatOptionalPct(summary.day_pnl_pct)}`}
        tone={toneForOptional(summary.total_pnl)}
      />
      <MetricCard label="持仓数" value={positionsCount} detail={unmatchedCount ? `待确认 ${unmatchedCount} 行` : "已全部导入"} />
      <MetricCard
        label="最大权重"
        value={topWeight ? `${formatNumber(topWeight.weight * 100)}%` : positionRatioText}
        detail={topWeight?.name || `截图仓位 ${positionRatioText}`}
      />
    </>
  );
}

function StockInsightPanel({
  target,
  mutation,
}: {
  target: PortfolioPosition;
  mutation: UseMutationResult<StockInsightResponse, unknown, PortfolioPosition, unknown>;
}) {
  return (
    <div className="portfolio-inline-insight" data-testid="portfolio-inline-insight">
      <div className="panel-head portfolio-panel-head portfolio-insight-head">
        <div>
          <h3>{target.name || target.symbol} AI分析</h3>
          <span>{mutation.data ? `${mutation.data.status} / ${mutation.data.model}` : "生成单股分析，缺少联网 Key 时使用本地行情"}</span>
        </div>
        <Bot size={18} />
      </div>
      {mutation.isPending ? <p className="notice-text portfolio-notice">正在分析 {target.symbol}...</p> : null}
      {mutation.isError ? <p className="notice-text portfolio-notice">{apiFailureMessage(mutation.error, "AI分析")}</p> : null}
      {mutation.data ? (
        <div className="portfolio-insight-body">
          <div className={`report-status ${mutation.data.status}`}>{mutation.data.summary}</div>
          <InsightList title="30日走势" items={mutation.data.trend} />
          <InsightList title="财报要点" items={mutation.data.financials} />
          <InsightList title="重要事件" items={mutation.data.events} />
          <InsightList title="风险提示" items={mutation.data.risks} warn />
          {mutation.data.data_warnings.length ? (
            <div className="portfolio-insight-warnings">
              {mutation.data.data_warnings.map((warning) => (
                <p className="notice-text portfolio-notice" key={warning}>
                  {warning}
                </p>
              ))}
            </div>
          ) : null}
          {mutation.data.citations.length ? (
            <div className="portfolio-insight-citations">
              <h4>来源</h4>
              {mutation.data.citations.map((citation) => (
                <a href={citation.url} key={`${citation.url}-${citation.title}`} rel="noreferrer" target="_blank">
                  {citation.title}
                  {citation.source ? <span>{citation.source}</span> : null}
                </a>
              ))}
            </div>
          ) : null}
          <p className="notice-text">{mutation.data.disclaimer}</p>
        </div>
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

function positionKey(position: PortfolioPosition): string {
  return `${position.market}:${normalizePortfolioSymbol(position.symbol)}`;
}

function isWatchlistPosition(position: PortfolioPosition): boolean {
  return position.source === "ocr-watchlist" || position.raw_fields?.["识别类型"] === "自选/行情列表";
}

function buildScreenshotSummary(positions: PortfolioPosition[]) {
  let upCount = 0;
  let downCount = 0;
  let flatCount = 0;

  for (const position of positions) {
    const change = parseWatchlistChange(position.raw_fields?.["涨幅"]);
    if (change === null || change === 0) {
      flatCount += 1;
    } else if (change > 0) {
      upCount += 1;
    } else {
      downCount += 1;
    }
  }

  return {
    count: positions.length,
    latestTotal: positions.reduce((total, position) => total + (Number.isFinite(position.current_price) ? position.current_price : 0), 0),
    upCount,
    downCount,
    flatCount,
  };
}

function parseWatchlistChange(value: string | undefined): number | null {
  if (!value) {
    return null;
  }
  const parsed = Number(value.replace("%", "").replace("▲", "").replace("▼", "").trim());
  return Number.isFinite(parsed) ? parsed : null;
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
