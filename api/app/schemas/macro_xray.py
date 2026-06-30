from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.schemas.macro import MacroSourceState, MacroSourceStatus


class MacroXrayUniverse(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: str
    code: str
    name: str
    scope: str = "non_financial"


class MacroXrayPeriod(BaseModel):
    model_config = ConfigDict(extra="allow")

    latest: str | None = None
    quarters: int = 0
    lookback: int = 0


class MacroXraySample(BaseModel):
    model_config = ConfigDict(extra="allow")

    count: int
    coverage: float
    source: str


class MacroXrayPoint(BaseModel):
    model_config = ConfigDict(extra="allow")

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
    equipmentRenewalRatio: float | None = None
    distributionCashYoy: float | None = None
    expenseYoy: float | None = None
    fixedAssetsYoy: float | None = None
    depreciationYoy: float | None = None
    employeeCashYoy: float | None = None
    orderBacklogYoy: float | None = None
    payableYoy: float | None = None
    netCashCompanyRatio: float | None = None


class MacroXrayInsight(BaseModel):
    level: str
    title: str
    detail: str


class MacroXrayResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    ts: datetime
    status: MacroSourceState
    index: str | dict[str, Any]
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
    model_config = ConfigDict(extra="allow")

    id: str
    type: str
    code: str
    name: str
    source: str
    status: MacroSourceState


class MacroXrayTargetsResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    ts: datetime
    status: MacroSourceState
    items: list[MacroXrayTarget]
    targets: list[MacroXrayTarget] = []
    source_status: list[MacroSourceStatus] = []
    methodology: str
