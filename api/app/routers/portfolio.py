from fastapi import APIRouter, Request

from app.schemas.portfolio import PortfolioAnalysis, PortfolioAnalysisRequest
from app.services.portfolio import analyze_portfolio, refresh_portfolio_prices

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


@router.post("/analyze", response_model=PortfolioAnalysis)
async def analyze(request: Request, payload: PortfolioAnalysisRequest) -> PortfolioAnalysis:
    positions = payload.positions
    quote_status = []
    data_warnings = []
    if payload.refresh_prices:
        refresh_result = await refresh_portfolio_prices(positions, request.app.state.market_service)
        positions = refresh_result.positions
        quote_status = refresh_result.quote_status
        data_warnings = refresh_result.data_warnings
    return analyze_portfolio(positions, quote_status=quote_status, data_warnings=data_warnings)
