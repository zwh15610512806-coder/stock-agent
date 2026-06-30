from datetime import datetime

from pydantic import BaseModel

from app.schemas.macro import MacroSourceState, MacroSourceStatus


class MacroXrayUniverse(BaseModel):
    type: str
    code: str
    name: str
    scope: str = "non_financial"


class MacroXrayPeriod(BaseModel):
    latest: str | None = None
    quarters: int
    lookback: int


class MacroXraySample(BaseModel):
    count: int
    coverage: float
    source: str


class MacroXrayPoint(BaseModel):
    period: str
    date: str
    revenueYoy: float | None = None
    profitYoy: float | None = None
    profitRevenueGap: float | None = None
    receivableYoy: float | None = None
    inventoryYoy: float | None = None
    ocfYoy: float | None = None
    capexYoy: float | None = None
    cashYoy: float | None = None
    interestDebtYoy: float | None = None
    cashConversionRatio: float | None = None
    grossMarginProxy: float | None = None
    expenseToRevenue: float | None = None
    rdYoy: float | None = None
    lossCompanyRatio: float | None = None


class MacroXrayInsight(BaseModel):
    level: str
    title: str
    detail: str


class MacroXrayResponse(BaseModel):
    ts: datetime
    status: MacroSourceState
    index: str
    universe: MacroXrayUniverse
    period: MacroXrayPeriod
    sample: MacroXraySample
    latest: MacroXrayPoint | None = None
    points: list[MacroXrayPoint]
    nominalGdp: list[MacroXrayPoint] = []
    crossIndex: list[MacroXrayPoint] = []
    insights: list[MacroXrayInsight] = []
    diagnostics: list[str] = []
    source_status: list[MacroSourceStatus] = []
    methodology: str


class MacroXrayTarget(BaseModel):
    id: str
    type: str
    code: str
    name: str
    source: str
    status: MacroSourceState


class MacroXrayTargetsResponse(BaseModel):
    ts: datetime
    status: MacroSourceState
    items: list[MacroXrayTarget]
    source_status: list[MacroSourceStatus] = []
    methodology: str
