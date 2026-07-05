from typing import Any

from fastapi import APIRouter, Query, Request, Response

from app.routers.cache_headers import set_shared_cache_header
from app.routers.market_payloads import danginvest_overview_snapshot
from app.schemas.market import CandleSnapshot, MarketCode, MarketDashboardResponse, MarketOverviewResponse, QuoteSnapshot
from app.services.market import MarketDataService
from app.services.portfolio import DISCLAIMER
from app.services.symbols import normalize_symbol

router = APIRouter(prefix="/api/market", tags=["market"])
DEFAULT_DASHBOARD_MARKETS: tuple[MarketCode, ...] = ("CN", "HK", "US", "KR", "JP")


@router.get("/overview")
async def overview(
    request: Request,
    markets: str | None = Query(default=None),
    date: str | None = Query(default=None, min_length=10, max_length=10),
) -> Any:
    service: MarketDataService = request.app.state.market_service
    if markets is None or date is not None:
        dashboard_response = await service.dashboard(list(DEFAULT_DASHBOARD_MARKETS), "daily")
        return danginvest_overview_snapshot(dashboard_response, date)
    requested = _parse_markets(markets)
    return MarketOverviewResponse(markets=await service.overview(requested), disclaimer=DISCLAIMER)


@router.get("/dashboard", response_model=MarketDashboardResponse)
async def dashboard(
    request: Request,
    response: Response,
    markets: str = Query(default="CN,HK,US,KR,JP"),
    period: str = Query(default="daily", pattern="^(daily|weekly|monthly)$"),
) -> MarketDashboardResponse:
    service: MarketDataService = request.app.state.market_service
    requested = _parse_markets(markets)
    set_shared_cache_header(response, s_maxage=30, stale_while_revalidate=300)
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
    allowed: set[MarketCode] = {"CN", "HK", "US", "KR", "JP"}
    output: list[MarketCode] = []
    for item in value.split(","):
        market = item.strip().upper()
        if market in allowed and market not in output:
            output.append(market)  # type: ignore[arg-type]
    return output or list(DEFAULT_DASHBOARD_MARKETS)
