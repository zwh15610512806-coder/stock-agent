from fastapi import APIRouter, Request

from app.schemas.ai import AiReportRequest, AiReportResponse
from app.services.ai_reports import DeepSeekReportService

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.post("/reports", response_model=AiReportResponse)
async def create_report(request: Request, payload: AiReportRequest) -> AiReportResponse:
    service: DeepSeekReportService = request.app.state.ai_report_service
    return await service.generate(payload)
