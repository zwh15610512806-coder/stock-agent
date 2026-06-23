from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

MarketCode = Literal["CN", "HK", "US"]
DashboardCacheStatus = Literal["live", "stale", "partial", "unavailable"]
DashboardSourceState = Literal["live", "stale", "unavailable"]


class QuoteSnapshot(BaseModel):
    symbol: str
    name: str
    market: MarketCode
    price: float
    change: float = 0
    change_pct: float = 0
    volume: float = 0
    turnover: float = 0
    currency: str
    source: str
    as_of: datetime
    delay_label: str


class CandleSnapshot(BaseModel):
    symbol: str
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float = 0
    source: str
    delay_label: str


class SymbolSearchResult(BaseModel):
    symbol: str
    name: str
    market: MarketCode
    currency: str


class MarketHeatItem(BaseModel):
    name: str
    change_pct: float
    turnover: float = 0
    direction: Literal["up", "down", "flat"]


class MarketBreadth(BaseModel):
    advances: int = 0
    declines: int = 0
    unchanged: int = 0
    limit_up: int = 0
    limit_down: int = 0


class MarketOverviewItem(BaseModel):
    market: MarketCode
    label: str
    indices: list[QuoteSnapshot]
    turnover: float = 0
    sentiment: float = Field(ge=0, le=100)
    breadth: MarketBreadth
    heatmap: list[MarketHeatItem]
    source: str
    delay_label: str
    as_of: datetime


class MarketOverviewResponse(BaseModel):
    markets: list[MarketOverviewItem]
    disclaimer: str


class DashboardSourceStatus(BaseModel):
    name: str
    status: DashboardSourceState
    source: str
    detail: str = ""
    as_of: datetime | None = None


class AShareActivity(BaseModel):
    advances: int = 0
    declines: int = 0
    unchanged: int = 0
    limit_up: int = 0
    limit_down: int = 0
    suspended: int = 0
    sentiment: float = Field(default=0, ge=0, le=100)
    source: str
    as_of: datetime | None = None


class DashboardHeatItem(BaseModel):
    name: str
    change_pct: float = 0
    turnover: float = 0
    net_amount: float = 0
    direction: Literal["up", "down", "flat"]
    source: str


class FundFlowItem(BaseModel):
    symbol: str = ""
    name: str
    change_pct: float = 0
    net_amount: float = 0
    turnover: float = 0
    source: str


class FundFlowSummary(BaseModel):
    top_inflows: list[FundFlowItem]
    top_outflows: list[FundFlowItem]
    net_amount: float = 0
    source: str
    as_of: datetime | None = None


class MarketDashboardResponse(BaseModel):
    as_of: datetime
    cache_status: DashboardCacheStatus
    source_status: list[DashboardSourceStatus]
    primary_quote: QuoteSnapshot | None = None
    primary_candles: list[CandleSnapshot] = []
    markets: list[MarketOverviewItem]
    a_share_activity: AShareActivity | None = None
    fund_flow_summary: FundFlowSummary | None = None
    industry_heatmap: list[DashboardHeatItem] = []
    concept_heatmap: list[DashboardHeatItem] = []
    region_heatmap: list[DashboardHeatItem] = []
    disclaimer: str
