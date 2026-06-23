from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.market import MarketCode


class PortfolioPosition(BaseModel):
    symbol: str
    name: str = ""
    market: MarketCode
    quantity: float = Field(ge=0)
    cost_price: float = Field(ge=0)
    current_price: float = Field(ge=0)
    currency: str


class PortfolioPositionAnalysis(PortfolioPosition):
    market_value: float
    cost_value: float
    pnl: float
    pnl_pct: float


class PortfolioWeight(BaseModel):
    symbol: str
    name: str
    market: MarketCode
    value: float
    weight: float


class PortfolioRisk(BaseModel):
    level: Literal["low", "medium", "high"]
    title: str
    detail: str


class PortfolioQuoteStatus(BaseModel):
    symbol: str
    status: Literal["live", "stale", "unavailable"]
    source: str
    detail: str = ""
    as_of: datetime | None = None


class PortfolioAnalysisRequest(BaseModel):
    positions: list[PortfolioPosition]
    refresh_prices: bool = True


class PortfolioAnalysis(BaseModel):
    total_value: float
    total_cost: float
    pnl: float
    pnl_pct: float
    positions: list[PortfolioPositionAnalysis]
    weights: list[PortfolioWeight]
    risks: list[PortfolioRisk]
    suggestions: list[str]
    disclaimer: str
    quote_status: list[PortfolioQuoteStatus] = Field(default_factory=list)
    data_warnings: list[str] = Field(default_factory=list)
