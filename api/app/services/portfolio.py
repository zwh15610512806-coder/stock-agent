from dataclasses import dataclass
from typing import Protocol

from app.schemas.market import QuoteSnapshot
from app.schemas.portfolio import (
    PortfolioAnalysis,
    PortfolioPosition,
    PortfolioPositionAnalysis,
    PortfolioQuoteStatus,
    PortfolioRisk,
    PortfolioWeight,
)
from app.services.symbols import normalize_symbol

DISCLAIMER = "仅供研究参考，不构成任何证券买卖建议。"


class QuoteProvider(Protocol):
    async def quotes(self, symbols: list[str]) -> list[QuoteSnapshot]:
        pass


@dataclass(frozen=True)
class PortfolioRefreshResult:
    positions: list[PortfolioPosition]
    quote_status: list[PortfolioQuoteStatus]
    data_warnings: list[str]


async def refresh_portfolio_prices(
    positions: list[PortfolioPosition],
    quote_provider: QuoteProvider,
) -> PortfolioRefreshResult:
    if not positions:
        return PortfolioRefreshResult(positions=[], quote_status=[], data_warnings=[])
    try:
        quotes = await quote_provider.quotes([position.symbol for position in positions])
    except Exception as exc:
        detail = f"quote refresh failed: {_error_detail(exc)}"
        return PortfolioRefreshResult(
            positions=positions,
            quote_status=[
                PortfolioQuoteStatus(
                    symbol=normalize_symbol(position.symbol, position.market),
                    status="unavailable",
                    source="market-quote",
                    detail=detail,
                )
                for position in positions
            ],
            data_warnings=[
                f"{normalize_symbol(position.symbol, position.market)}: {detail}; kept local current_price"
                for position in positions
            ],
        )

    quote_by_symbol: dict[str, QuoteSnapshot] = {}
    for quote in quotes:
        quote_by_symbol[quote.symbol] = quote
        quote_by_symbol[normalize_symbol(quote.symbol, quote.market)] = quote

    refreshed: list[PortfolioPosition] = []
    quote_status: list[PortfolioQuoteStatus] = []
    data_warnings: list[str] = []
    for position in positions:
        normalized_symbol = normalize_symbol(position.symbol, position.market)
        quote = quote_by_symbol.get(normalized_symbol) or quote_by_symbol.get(position.symbol)
        if quote is None:
            detail = "quote unavailable; kept local current_price"
            refreshed.append(position)
            quote_status.append(
                PortfolioQuoteStatus(
                    symbol=normalized_symbol,
                    status="unavailable",
                    source="market-quote",
                    detail=detail,
                )
            )
            data_warnings.append(f"{normalized_symbol}: {detail}")
            continue
        if _is_sample_fallback(quote):
            detail = "sample fallback quote rejected; kept local current_price"
            refreshed.append(position)
            quote_status.append(
                PortfolioQuoteStatus(
                    symbol=quote.symbol,
                    status="unavailable",
                    source=quote.source,
                    detail=detail,
                    as_of=quote.as_of,
                )
            )
            data_warnings.append(f"{normalized_symbol}: {detail}")
            continue
        if quote.price <= 0:
            detail = "invalid quote price; kept local current_price"
            refreshed.append(position)
            quote_status.append(
                PortfolioQuoteStatus(
                    symbol=quote.symbol,
                    status="unavailable",
                    source=quote.source,
                    detail=detail,
                    as_of=quote.as_of,
                )
            )
            data_warnings.append(f"{normalized_symbol}: {detail}")
            continue
        refreshed.append(
            position.model_copy(
                update={
                    "symbol": quote.symbol,
                    "name": position.name or quote.name,
                    "market": quote.market,
                    "current_price": quote.price,
                    "currency": quote.currency,
                }
            )
        )
        quote_status.append(
            PortfolioQuoteStatus(
                symbol=quote.symbol,
                status="live",
                source=quote.source,
                detail=quote.delay_label,
                as_of=quote.as_of,
            )
        )
    return PortfolioRefreshResult(positions=refreshed, quote_status=quote_status, data_warnings=data_warnings)


async def refresh_positions_with_quotes(
    positions: list[PortfolioPosition],
    quote_provider: QuoteProvider,
) -> list[PortfolioPosition]:
    result = await refresh_portfolio_prices(positions, quote_provider)
    return result.positions


def analyze_portfolio(
    positions: list[PortfolioPosition],
    quote_status: list[PortfolioQuoteStatus] | None = None,
    data_warnings: list[str] | None = None,
) -> PortfolioAnalysis:
    analyzed: list[PortfolioPositionAnalysis] = []
    for position in positions:
        market_value = round(position.quantity * position.current_price, 4)
        cost_value = round(position.quantity * position.cost_price, 4)
        pnl = round(market_value - cost_value, 4)
        pnl_pct = round(pnl / cost_value, 6) if cost_value else 0
        analyzed.append(
            PortfolioPositionAnalysis(
                **position.model_dump(),
                market_value=market_value,
                cost_value=cost_value,
                pnl=pnl,
                pnl_pct=pnl_pct,
            )
        )

    total_value = round(sum(item.market_value for item in analyzed), 4)
    total_cost = round(sum(item.cost_value for item in analyzed), 4)
    pnl = round(total_value - total_cost, 4)
    pnl_pct = round(pnl / total_cost, 6) if total_cost else 0
    weights = [
        PortfolioWeight(
            symbol=item.symbol,
            name=item.name,
            market=item.market,
            value=item.market_value,
            weight=round(item.market_value / total_value, 6) if total_value else 0,
        )
        for item in sorted(analyzed, key=lambda row: row.market_value, reverse=True)
    ]

    risks = _portfolio_risks(weights, pnl_pct)
    suggestions = _portfolio_suggestions(weights, pnl_pct)
    return PortfolioAnalysis(
        total_value=total_value,
        total_cost=total_cost,
        pnl=pnl,
        pnl_pct=pnl_pct,
        positions=analyzed,
        weights=weights,
        risks=risks,
        suggestions=suggestions,
        disclaimer=DISCLAIMER,
        quote_status=quote_status or [],
        data_warnings=data_warnings or [],
    )


def _is_sample_fallback(quote: QuoteSnapshot) -> bool:
    return quote.source.strip().lower() == "sample fallback"


def _error_detail(exc: Exception) -> str:
    return str(exc) or exc.__class__.__name__


def _portfolio_risks(weights: list[PortfolioWeight], pnl_pct: float) -> list[PortfolioRisk]:
    risks: list[PortfolioRisk] = []
    if weights and weights[0].weight >= 0.45:
        risks.append(
            PortfolioRisk(
                level="high",
                title="单一持仓集中度偏高",
                detail=f"{weights[0].name or weights[0].symbol} 占组合 {weights[0].weight:.1%}，需要设置再平衡和止损规则。",
            )
        )
    markets = {item.market for item in weights}
    if len(markets) == 1 and weights:
        risks.append(
            PortfolioRisk(
                level="medium",
                title="市场暴露单一",
                detail=f"当前组合仅暴露于 {next(iter(markets))} 市场，需关注单一市场系统性波动。",
            )
        )
    if pnl_pct <= -0.15:
        risks.append(
            PortfolioRisk(
                level="medium",
                title="组合回撤较深",
                detail="组合浮亏超过 15%，应复盘买入逻辑、仓位纪律和最大亏损阈值。",
            )
        )
    return risks


def _portfolio_suggestions(weights: list[PortfolioWeight], pnl_pct: float) -> list[str]:
    if not weights:
        return ["先添加持仓或导入 CSV/OCR 结果，再生成组合分析。"]
    suggestions = ["对权重最高的持仓设置观察指标和再平衡阈值。"]
    if pnl_pct > 0.2:
        suggestions.append("组合盈利较高时，考虑分批止盈或上移保护线。")
    if pnl_pct < 0:
        suggestions.append("组合浮亏时，优先确认基本面和趋势是否同时恶化。")
    return suggestions
