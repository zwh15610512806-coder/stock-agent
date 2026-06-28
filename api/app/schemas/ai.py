from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.market import CandleSnapshot, MarketCode, QuoteSnapshot
from app.schemas.portfolio import PortfolioPosition

AiReportAnalysisSkill = Literal["standard", "serenity"]


class AiReportRequest(BaseModel):
    symbol: str
    market: MarketCode
    analysis_skill: AiReportAnalysisSkill = "standard"
    horizon: str = "中短线波段"
    risk_profile: str = "稳健"
    quote: QuoteSnapshot | None = None
    candles: list[CandleSnapshot] = Field(default_factory=list)
    portfolio_positions: list[PortfolioPosition] = Field(default_factory=list)


class AiReportSection(BaseModel):
    title: str
    body: str


class AiReportResponse(BaseModel):
    status: Literal["completed", "unavailable", "failed"]
    symbol: str
    market: MarketCode
    summary: str
    sections: list[AiReportSection]
    watch_metrics: list[str]
    risks: list[str]
    model: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    disclaimer: str


class StockInsightRequest(BaseModel):
    position: PortfolioPosition
    horizon_days: int = Field(default=30, ge=5, le=90)


class StockInsightCitation(BaseModel):
    title: str
    url: str
    source: str = ""
    published_at: datetime | None = None


class StockInsightResponse(BaseModel):
    status: Literal["completed", "partial", "unavailable", "failed"]
    symbol: str
    market: MarketCode
    as_of: datetime
    quote: QuoteSnapshot | None = None
    candles: list[CandleSnapshot] = Field(default_factory=list)
    summary: str
    trend: list[str] = Field(default_factory=list)
    financials: list[str] = Field(default_factory=list)
    events: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    citations: list[StockInsightCitation] = Field(default_factory=list)
    data_warnings: list[str] = Field(default_factory=list)
    model: str
    disclaimer: str
