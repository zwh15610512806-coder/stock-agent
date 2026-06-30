from fastapi import APIRouter, Query, Request

from app.schemas.macro import MacroDashboardResponse, MacroTimeseriesResponse
from app.services.macro import MacroDataService

router = APIRouter(prefix="/api/macro", tags=["macro"])


@router.get("/dashboard", response_model=MacroDashboardResponse)
async def dashboard(request: Request) -> MacroDashboardResponse:
    service = getattr(request.app.state, "macro_service", None)
    if service is None:
        service = MacroDataService()
        request.app.state.macro_service = service
    return await service.dashboard()


@router.get("/timeseries", response_model=MacroTimeseriesResponse)
async def timeseries(
    request: Request,
    series_ids: str = Query(default=""),
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    max_points: int = Query(default=600, ge=1, le=5000),
) -> MacroTimeseriesResponse:
    service = getattr(request.app.state, "macro_service", None)
    if service is None:
        service = MacroDataService()
        request.app.state.macro_service = service
    parsed_ids = [item.strip() for item in series_ids.split(",") if item.strip()] if series_ids else None
    return await service.timeseries(series_ids=parsed_ids, start=start, end=end, max_points=max_points)
