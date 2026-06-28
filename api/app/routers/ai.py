from fastapi import APIRouter, Request

from app.schemas.ai import AiReportRequest, AiReportResponse, StockInsightRequest, StockInsightResponse
from app.services.ai_reports import DeepSeekReportService
from app.services.stock_insights import StockInsightService

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.post("/reports", response_model=AiReportResponse)
async def create_report(request: Request, payload: AiReportRequest) -> AiReportResponse:
    service: DeepSeekReportService = request.app.state.ai_report_service
    return await service.generate(payload)


@router.post("/stock-insights", response_model=StockInsightResponse)
async def create_stock_insight(request: Request, payload: StockInsightRequest) -> StockInsightResponse:
    service: StockInsightService = request.app.state.stock_insight_service
    return await service.generate(payload)
