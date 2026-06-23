from datetime import datetime
from typing import Literal

from pydantic import BaseModel

ETFSourceStatus = Literal["live", "unavailable"]


class ETFQuoteItem(BaseModel):
    symbol: str
    name: str
    price: float | None = None
    change_pct: float | None = None
    turnover: float | None = None
    volume: float | None = None
    source: str


class ETFCandleItem(BaseModel):
    symbol: str
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None
    turnover: float | None = None
    source: str


class ETFSearchResponse(BaseModel):
    items: list[ETFQuoteItem]
    source: str
    as_of: datetime | None = None
    status: ETFSourceStatus
    detail: str = ""


class ETFCandlesResponse(BaseModel):
    items: list[ETFCandleItem]
    source: str
    as_of: datetime | None = None
    status: ETFSourceStatus
    detail: str = ""
