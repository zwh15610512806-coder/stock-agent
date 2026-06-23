from fastapi import APIRouter, Request

from app.schemas.macro import MacroDashboardResponse
from app.services.macro import MacroDataService

router = APIRouter(prefix="/api/macro", tags=["macro"])


@router.get("/dashboard", response_model=MacroDashboardResponse)
async def dashboard(request: Request) -> MacroDashboardResponse:
    service = getattr(request.app.state, "macro_service", None)
    if service is None:
        service = MacroDataService()
        request.app.state.macro_service = service
    return await service.dashboard()
