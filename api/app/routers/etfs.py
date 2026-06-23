from fastapi import APIRouter, Query, Request

from app.schemas.etfs import ETFCandlesResponse, ETFSearchResponse
from app.services.etfs import ETFService

router = APIRouter(prefix="/api/etfs", tags=["etfs"])


@router.get("/search", response_model=ETFSearchResponse)
async def search(
    request: Request,
    q: str = Query(default=""),
    limit: int = Query(default=50, ge=1, le=200),
) -> ETFSearchResponse:
    service = _service(request)
    return await service.search(q=q, limit=limit)


@router.get("/candles", response_model=ETFCandlesResponse)
async def candles(
    request: Request,
    symbol: str = Query(..., min_length=1),
    period: str = Query(default="daily", pattern="^(daily|weekly|monthly)$"),
    limit: int = Query(default=120, ge=1, le=500),
) -> ETFCandlesResponse:
    service = _service(request)
    return await service.candles(symbol=symbol, period=period, limit=limit)


def _service(request: Request) -> ETFService:
    service = getattr(request.app.state, "etf_service", None)
    if isinstance(service, ETFService):
        return service
    return ETFService()
