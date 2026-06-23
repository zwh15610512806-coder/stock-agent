from fastapi import APIRouter, Request

from app.schemas.portfolio import PortfolioAnalysis, PortfolioAnalysisRequest
from app.services.portfolio import analyze_portfolio, refresh_positions_with_quotes

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


@router.post("/analyze", response_model=PortfolioAnalysis)
async def analyze(request: Request, payload: PortfolioAnalysisRequest) -> PortfolioAnalysis:
    positions = payload.positions
    if payload.refresh_prices:
        positions = await refresh_positions_with_quotes(positions, request.app.state.market_service)
    return analyze_portfolio(positions)
