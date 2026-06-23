from datetime import datetime
from typing import Literal

from pydantic import BaseModel

StockSourceStatus = Literal["live", "unavailable"]


class StockScreenerItem(BaseModel):
    symbol: str
    code: str
    name: str
    market: Literal["CN"] = "CN"
    currency: Literal["CNY"] = "CNY"
    exchange: str | None = None
    price: float | None = None
    change_pct: float | None = None
    turnover: float | None = None
    volume: float | None = None
    market_cap: float | None = None
    pe: float | None = None
    pb: float | None = None
    turnover_rate: float | None = None
    source: str


class StockScreenerResponse(BaseModel):
    items: list[StockScreenerItem]
    source: str
    as_of: datetime | None = None
    status: StockSourceStatus
    detail: str = ""
