from typing import Protocol

from app.schemas.market import QuoteSnapshot
from app.schemas.portfolio import (
    PortfolioAnalysis,
    PortfolioPosition,
    PortfolioPositionAnalysis,
    PortfolioRisk,
    PortfolioWeight,
)
from app.services.symbols import normalize_symbol

DISCLAIMER = "仅供研究参考，不构成任何证券买卖建议。"


class QuoteProvider(Protocol):
    async def quotes(self, symbols: list[str]) -> list[QuoteSnapshot]:
        pass


async def refresh_positions_with_quotes(
    positions: list[PortfolioPosition],
    quote_provider: QuoteProvider,
) -> list[PortfolioPosition]:
    if not positions:
        return positions
    try:
        quotes = await quote_provider.quotes([position.symbol for position in positions])
    except Exception:
        return positions
    quote_by_symbol = {quote.symbol: quote for quote in quotes}
    refreshed: list[PortfolioPosition] = []
    for position in positions:
        quote = quote_by_symbol.get(normalize_symbol(position.symbol, position.market))
        if quote is None or quote.price <= 0:
            refreshed.append(position)
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
    return refreshed


def analyze_portfolio(positions: list[PortfolioPosition]) -> PortfolioAnalysis:
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
    )


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
