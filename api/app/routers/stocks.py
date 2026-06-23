from fastapi import APIRouter, Query, Request

from app.schemas.stocks import StockScreenerResponse
from app.services.stocks import StockScreenerService

router = APIRouter(prefix="/api/stocks", tags=["stocks"])


@router.get("/screener", response_model=StockScreenerResponse)
async def screener(
    request: Request,
    query: str = Query(default=""),
    min_change_pct: float | None = Query(default=None),
    max_change_pct: float | None = Query(default=None),
    min_turnover: float | None = Query(default=None, ge=0),
    min_market_cap: float | None = Query(default=None, ge=0),
    max_pe: float | None = Query(default=None),
    max_pb: float | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> StockScreenerResponse:
    service = _service(request)
    return await service.screen(
        query=query,
        min_change_pct=min_change_pct,
        max_change_pct=max_change_pct,
        min_turnover=min_turnover,
        min_market_cap=min_market_cap,
        max_pe=max_pe,
        max_pb=max_pb,
        limit=limit,
    )


def _service(request: Request) -> StockScreenerService:
    service = getattr(request.app.state, "stock_screener_service", None)
    if isinstance(service, StockScreenerService):
        return service
    return StockScreenerService()
