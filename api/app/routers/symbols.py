from fastapi import APIRouter, Query, Request

from app.schemas.market import MarketCode, SymbolSearchResult
from app.services.market import MarketDataService

router = APIRouter(prefix="/api/symbols", tags=["symbols"])


@router.get("/search", response_model=list[SymbolSearchResult])
async def search_symbols(
    request: Request,
    q: str = Query(..., min_length=1),
    markets: str = Query(default="CN,HK,US"),
) -> list[SymbolSearchResult]:
    service: MarketDataService = request.app.state.market_service
    requested: set[MarketCode] = set()
    for item in markets.split(","):
        market = item.strip().upper()
        if market in {"CN", "HK", "US"}:
            requested.add(market)  # type: ignore[arg-type]
    return await service.search(q, requested or None)
