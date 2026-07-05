from typing import Any

from pydantic import BaseModel, Field

from app.schemas.portfolio import PortfolioPosition


class OcrPortfolioSummary(BaseModel):
    total_assets: float | None = None
    total_pnl: float | None = None
    day_pnl: float | None = None
    day_pnl_pct: float | None = None
    market_value: float | None = None
    available_cash: float | None = None
    withdrawable_cash: float | None = None
    position_ratio: float | None = None
    currency: str = "CNY"


class OcrUnmatchedRow(BaseModel):
    name: str
    reason: str
    raw_fields: dict[str, Any] = Field(default_factory=dict)


class OcrPositionsResponse(BaseModel):
    status: str
    positions: list[PortfolioPosition]
    raw_lines: list[str]
    message: str = ""
    portfolio_summary: OcrPortfolioSummary | None = None
    unmatched_rows: list[OcrUnmatchedRow] = Field(default_factory=list)
