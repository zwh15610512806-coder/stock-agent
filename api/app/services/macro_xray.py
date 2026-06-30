import importlib
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from app.schemas.macro import MacroSourceStatus
from app.schemas.macro_xray import (
    MacroXrayInsight,
    MacroXrayPeriod,
    MacroXrayPoint,
    MacroXrayResponse,
    MacroXraySample,
    MacroXrayTarget,
    MacroXrayTargetsResponse,
    MacroXrayUniverse,
)
from app.services.macro import MacroDataService, _records, _row_value

INDEX_TARGETS = {
    "000300.SH": "沪深300",
    "000905.SH": "中证500",
    "000510.SH": "中证A500",
    "000852.SH": "中证1000",
}

XRAY_SERIES_IDS = [
    "cn.activity.industrial_production_yoy",
    "cn.ppi.yoy",
    "cn.money.m1_yoy",
    "cn.money.m2_yoy",
    "cn.money.m1_minus_m2_yoy",
    "cn.credit.social_financing_yoy",
]


class MacroXrayService:
    def __init__(
        self,
        macro_service: MacroDataService | None = None,
        akshare_module: object | None = None,
    ) -> None:
        self.macro_service = macro_service or MacroDataService(akshare_module=akshare_module)
        self.akshare_module = akshare_module

    async def xray(
        self,
        universe_type: str = "index",
        universe_code: str = "000300.SH",
        scope: str = "non_financial",
        period: str = "latest",
        quarters: int = 40,
        lookback: int = 6,
    ) -> MacroXrayResponse:
        del period
        quarters = max(1, min(quarters, 80))
        lookback = max(1, min(lookback, 24))
        series_response = await self.macro_service.timeseries(
            series_ids=XRAY_SERIES_IDS,
            start=None,
            end=None,
            max_points=max(quarters * 4, 160),
        )
        series_map = {series.series_id: series.points for series in series_response.series}
        rows = _quarter_rows(series_map)
        points = [_xray_point_from_row(row) for row in rows[-quarters:]]
        points = [point for point in points if _point_has_signal(point)]
        status = "live" if points else "unavailable"
        diagnostics = [] if points else ["公开宏观源未返回可用于 X-Ray 代理计算的历史序列。"]
        latest = points[-1] if points else None
        universe_name = _target_name(universe_type, universe_code)
        source_status = series_response.source_status
        insights = _insights(latest)
        methodology = (
            "公开宏观源近似版：以工业增加值同比代理收入增速，以工业增加值与 PPI 组合代理利润弹性，"
            "以 M1-M2、社融增速代理现金周转、库存和扩产压力。该口径不是 DangInvest 原始成分股财报聚合算法。"
        )
        return MacroXrayResponse(
            ts=datetime.now(UTC),
            status=status,
            index=universe_code,
            universe=MacroXrayUniverse(type=universe_type, code=universe_code, name=universe_name, scope=scope),
            period=MacroXrayPeriod(latest=latest.period if latest else None, quarters=quarters, lookback=lookback),
            sample=MacroXraySample(count=1 if points else 0, coverage=0.0, source="public-macro-proxy"),
            latest=latest,
            points=points,
            nominalGdp=[],
            crossIndex=[],
            insights=insights,
            diagnostics=diagnostics,
            source_status=source_status,
            methodology=methodology,
        )

    async def targets(
        self,
        universe_type: str = "index",
        lookback: int = 6,
        target_source: str = "stock_basic_full_v1",
    ) -> MacroXrayTargetsResponse:
        del lookback, target_source
        items: list[MacroXrayTarget] = []
        source_status: list[MacroSourceStatus] = []
        if universe_type in {"index", "all"}:
            items.extend(
                MacroXrayTarget(
                    id=f"index:{code}",
                    type="index",
                    code=code,
                    name=name,
                    source="static-index-targets",
                    status="live",
                )
                for code, name in INDEX_TARGETS.items()
            )
        if universe_type in {"industry", "all"}:
            industry_items, status = self._industry_targets()
            items.extend(industry_items)
            source_status.append(status)
        if not items and universe_type not in {"index", "industry", "all"}:
            source_status.append(
                MacroSourceStatus(
                    name="macro_xray_targets",
                    status="unavailable",
                    source="unavailable",
                    detail=f"unsupported universe_type: {universe_type}",
                )
            )
        return MacroXrayTargetsResponse(
            ts=datetime.now(UTC),
            status="live" if items else "unavailable",
            items=items,
            source_status=source_status,
            methodology="Targets come from static index presets and AkShare Eastmoney industry board names when available.",
        )

    def _industry_targets(self) -> tuple[list[MacroXrayTarget], MacroSourceStatus]:
        source = "akshare.stock_board_industry_name_em"
        try:
            rows = _records(self._akshare().stock_board_industry_name_em())
            items: list[MacroXrayTarget] = []
            for row in rows:
                code = str(_row_value(row, ("板块代码", "code", "industry_code")) or "").strip()
                name = str(_row_value(row, ("板块名称", "name", "industry_name")) or "").strip()
                if not code or not name:
                    continue
                items.append(
                    MacroXrayTarget(
                        id=f"industry:{code}",
                        type="industry",
                        code=code,
                        name=name,
                        source=source,
                        status="live",
                    )
                )
            if not items:
                raise RuntimeError("industry board source returned no recognized rows")
            return items, MacroSourceStatus(name="stock_board_industry_name_em", status="live", source=source, as_of=datetime.now(UTC))
        except Exception as exc:
            return [], MacroSourceStatus(
                name="stock_board_industry_name_em",
                status="unavailable",
                source=source,
                detail=str(exc),
            )

    def _akshare(self) -> object:
        if self.akshare_module is None:
            self.akshare_module = importlib.import_module("akshare")
        return self.akshare_module


def _quarter_rows(series_map: dict[str, list[Any]]) -> list[dict[str, float | str]]:
    quarters: dict[str, dict[str, float | str]] = {}
    for series_id, points in series_map.items():
        for point in points:
            if point.value is None:
                continue
            period = _quarter_label(point.date)
            row = quarters.setdefault(period, {"period": period, "date": point.date})
            if str(point.date) > str(row.get("date", "")):
                row["date"] = point.date
            row[series_id] = point.value
    return [quarters[key] for key in sorted(quarters)]


def _quarter_label(value: str) -> str:
    year = int(value[:4])
    month = int(value[5:7])
    quarter = (month - 1) // 3 + 1
    return f"{year}Q{quarter}"


def _xray_point_from_row(row: Mapping[str, float | str]) -> MacroXrayPoint:
    industrial = _decimal(row.get("cn.activity.industrial_production_yoy"))
    ppi = _decimal(row.get("cn.ppi.yoy"))
    m1 = _decimal(row.get("cn.money.m1_yoy"))
    m2 = _decimal(row.get("cn.money.m2_yoy"))
    m1_minus_m2 = _decimal(row.get("cn.money.m1_minus_m2_yoy"))
    social = _decimal(row.get("cn.credit.social_financing_yoy"))

    revenue = industrial
    profit = _combine(industrial, ppi, weights=(0.7, 0.9))
    inventory = _combine(m2, _neg(m1_minus_m2), weights=(0.35, 0.5))
    receivable = social
    cash_conversion = _cash_conversion(m1_minus_m2, ppi)
    capex = _combine(social, industrial, weights=(0.5, 0.35))
    cash = _combine(m1, ppi, weights=(0.7, 0.2))
    debt = social
    gross_margin = _gross_margin(ppi)
    expense = _expense_ratio(ppi)
    rd = _combine(industrial, m1, weights=(0.45, 0.25))
    loss_ratio = _loss_ratio(profit)
    return MacroXrayPoint(
        period=str(row["period"]),
        date=str(row["date"]),
        revenueYoy=revenue,
        profitYoy=profit,
        profitRevenueGap=_diff(profit, revenue),
        receivableYoy=receivable,
        inventoryYoy=inventory,
        ocfYoy=cash,
        capexYoy=capex,
        cashYoy=cash,
        interestDebtYoy=debt,
        cashConversionRatio=cash_conversion,
        grossMarginProxy=gross_margin,
        expenseToRevenue=expense,
        rdYoy=rd,
        lossCompanyRatio=loss_ratio,
    )


def _decimal(value: object) -> float | None:
    if isinstance(value, int | float):
        return round(float(value) / 100, 6)
    return None


def _combine(left: float | None, right: float | None, weights: tuple[float, float]) -> float | None:
    values = []
    if left is not None:
        values.append(left * weights[0])
    if right is not None:
        values.append(right * weights[1])
    if not values:
        return None
    return round(sum(values), 6)


def _neg(value: float | None) -> float | None:
    return -value if value is not None else None


def _diff(left: float | None, right: float | None) -> float | None:
    if left is None or right is None:
        return None
    return round(left - right, 6)


def _cash_conversion(m1_minus_m2: float | None, ppi: float | None) -> float | None:
    if m1_minus_m2 is None and ppi is None:
        return None
    value = 0.82
    if m1_minus_m2 is not None:
        value += m1_minus_m2 * 1.2
    if ppi is not None:
        value += ppi * 0.4
    return round(max(0.35, min(1.35, value)), 6)


def _gross_margin(ppi: float | None) -> float | None:
    if ppi is None:
        return None
    return round(max(0.05, min(0.45, 0.22 + ppi * 0.5)), 6)


def _expense_ratio(ppi: float | None) -> float | None:
    if ppi is None:
        return None
    return round(max(0.06, min(0.24, 0.14 - ppi * 0.25)), 6)


def _loss_ratio(profit: float | None) -> float | None:
    if profit is None:
        return None
    return round(max(0.02, min(0.35, 0.12 - profit * 0.6)), 6)


def _point_has_signal(point: MacroXrayPoint) -> bool:
    return any(
        value is not None
        for value in (
            point.revenueYoy,
            point.profitYoy,
            point.inventoryYoy,
            point.cashConversionRatio,
        )
    )


def _insights(latest: MacroXrayPoint | None) -> list[MacroXrayInsight]:
    if latest is None:
        return []
    insights: list[MacroXrayInsight] = []
    if latest.profitRevenueGap is not None:
        level = "positive" if latest.profitRevenueGap >= 0 else "warning"
        title = "利润弹性领先收入" if latest.profitRevenueGap >= 0 else "利润弹性弱于收入"
        insights.append(MacroXrayInsight(level=level, title=title, detail=f"利润-收入代理差为 {latest.profitRevenueGap:.2%}。"))
    if latest.cashConversionRatio is not None:
        level = "positive" if latest.cashConversionRatio >= 0.8 else "warning"
        insights.append(MacroXrayInsight(level=level, title="现金转化代理", detail=f"现金转化代理值 {latest.cashConversionRatio:.2f}。"))
    return insights


def _target_name(universe_type: str, universe_code: str) -> str:
    if universe_type == "index":
        return INDEX_TARGETS.get(universe_code, universe_code)
    if universe_type == "industry":
        return universe_code
    if universe_type == "etf":
        return universe_code
    return universe_code
