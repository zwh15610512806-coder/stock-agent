from datetime import datetime
from typing import Literal

from pydantic import BaseModel

MacroCacheStatus = Literal["live", "stale", "partial", "unavailable"]
MacroSourceState = Literal["live", "stale", "unavailable"]


class MacroSourceStatus(BaseModel):
    name: str
    status: MacroSourceState
    source: str
    detail: str = ""
    as_of: datetime | None = None


class MacroDataPoint(BaseModel):
    name: str
    value: float | None = None
    unit: str
    as_of: datetime | None = None
    source: str
    status: MacroSourceState


class MacroDashboardResponse(BaseModel):
    as_of: datetime
    cache_status: MacroCacheStatus
    source_status: list[MacroSourceStatus]
    rates: list[MacroDataPoint]
    indicators: list[MacroDataPoint]
    bond_yields: list[MacroDataPoint]
    fx_rates: list[MacroDataPoint]
    disclaimer: str
