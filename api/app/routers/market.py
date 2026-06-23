from fastapi import APIRouter, Query, Request

from app.schemas.market import CandleSnapshot, MarketCode, MarketDashboardResponse, MarketOverviewResponse, QuoteSnapshot
from app.services.market import MarketDataService
from app.services.portfolio import DISCLAIMER
from app.services.symbols import normalize_symbol

router = APIRouter(prefix="/api/market", tags=["market"])


@router.get("/overview", response_model=MarketOverviewResponse)
async def overview(
    request: Request,
    markets: str = Query(default="CN,HK,US"),
) -> MarketOverviewResponse:
    service: MarketDataService = request.app.state.market_service
    requested = _parse_markets(markets)
    return MarketOverviewResponse(markets=await service.overview(requested), disclaimer=DISCLAIMER)


@router.get("/dashboard", response_model=MarketDashboardResponse)
async def dashboard(
    request: Request,
    markets: str = Query(default="CN,HK,US"),
    period: str = Query(default="daily", pattern="^(daily|weekly|monthly)$"),
) -> MarketDashboardResponse:
    service: MarketDataService = request.app.state.market_service
    requested = _parse_markets(markets)
    return await service.dashboard(requested, period)


@router.get("/quotes", response_model=list[QuoteSnapshot])
async def quotes(
    request: Request,
    symbols: str = Query(..., min_length=1),
) -> list[QuoteSnapshot]:
    service: MarketDataService = request.app.state.market_service
    requested = [normalize_symbol(item, None) for item in symbols.split(",") if item.strip()]
    return await service.quotes(requested)


@router.get("/candles", response_model=list[CandleSnapshot])
async def candles(
    request: Request,
    symbol: str = Query(..., min_length=1),
    period: str = Query(default="daily", pattern="^(daily|weekly|monthly)$"),
    limit: int = Query(default=120, ge=20, le=240),
) -> list[CandleSnapshot]:
    service: MarketDataService = request.app.state.market_service
    return await service.candles(normalize_symbol(symbol, None), period, limit)


def _parse_markets(value: str) -> list[MarketCode]:
    allowed: set[MarketCode] = {"CN", "HK", "US"}
    output: list[MarketCode] = []
    for item in value.split(","):
        market = item.strip().upper()
        if market in allowed and market not in output:
            output.append(market)  # type: ignore[arg-type]
    return output or ["CN", "HK", "US"]
