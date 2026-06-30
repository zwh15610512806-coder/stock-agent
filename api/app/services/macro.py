import asyncio
import importlib
import time
from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, TypeVar

from app.schemas.macro import (
    MacroCacheStatus,
    MacroDashboardResponse,
    MacroDataPoint,
    MacroSourceState,
    MacroSourceStatus,
    MacroTimeseriesPoint,
    MacroTimeseriesResponse,
    MacroTimeseriesSeries,
)
from app.services.market_cache import CachedSnapshot, MarketSnapshotCache

MACRO_SOURCE = "akshare-macro-free"
MACRO_SNAPSHOT_TTL_SECONDS = 6 * 60 * 60
MACRO_SOURCE_TIMEOUT_SECONDS = 8.0
MACRO_FAILURE_COOLDOWN_SECONDS = 3 * 60
T = TypeVar("T")

DEFAULT_MACRO_SERIES_IDS = [
    "cn.rate.cn10y",
    "us.rate.us10y",
    "fx.usdcnh",
    "fx.dxy",
    "cn.money.m1_yoy",
    "cn.money.m2_yoy",
    "cn.money.m1_minus_m2_yoy",
    "cn.ppi.yoy",
    "cn.cpi.yoy",
    "cn.pmi.manu",
    "cn.activity.industrial_production_yoy",
    "cn.credit.social_financing_yoy",
    "cn.credit.new_rmb_loans",
    "cn.rates.repo.dr007",
    "cn.market.financing_ratio",
    "cn.market.dividend_yield_all_a",
    "cn.market.turnover_rate_all_a",
    "cn.real_estate.loan_yoy",
    "cn.special_bond.progress",
]

MACRO_SERIES_SPECS: dict[str, dict[str, Any]] = {
    "cn.money.m1_yoy": {
        "name": "M1 YoY",
        "category": "money",
        "frequency": "monthly",
        "unit": "%",
        "source_key": "macro:series:money_supply",
        "source_name": "macro_china_money_supply",
        "source": "akshare.macro_china_money_supply",
        "fetcher": "_fetch_money_supply_series_sync",
        "methodology": "M1 year-over-year growth from AkShare China money supply table.",
    },
    "cn.money.m2_yoy": {
        "name": "M2 YoY",
        "category": "money",
        "frequency": "monthly",
        "unit": "%",
        "source_key": "macro:series:money_supply",
        "source_name": "macro_china_money_supply",
        "source": "akshare.macro_china_money_supply",
        "fetcher": "_fetch_money_supply_series_sync",
        "methodology": "M2 year-over-year growth from AkShare China money supply table.",
    },
    "cn.money.m1_minus_m2_yoy": {
        "name": "M1-M2 YoY Spread",
        "category": "money",
        "frequency": "monthly",
        "unit": "ppt",
        "source": "derived:akshare.macro_china_money_supply",
        "is_derived": True,
        "dependencies": ("cn.money.m1_yoy", "cn.money.m2_yoy"),
        "methodology": "Derived as M1 YoY minus M2 YoY using matched monthly observations.",
    },
    "cn.rate.cn10y": {
        "name": "China 10Y Government Bond Yield",
        "category": "rates",
        "frequency": "daily",
        "unit": "%",
        "source_key": "macro:series:bond_zh_us_rate",
        "source_name": "bond_zh_us_rate",
        "source": "akshare.bond_zh_us_rate",
        "fetcher": "_fetch_bond_rate_series_sync",
        "methodology": "China 10Y government bond yield from AkShare China/US bond yield table.",
    },
    "us.rate.us10y": {
        "name": "US 10Y Treasury Yield",
        "category": "rates",
        "frequency": "daily",
        "unit": "%",
        "source_key": "macro:series:bond_zh_us_rate",
        "source_name": "bond_zh_us_rate",
        "source": "akshare.bond_zh_us_rate",
        "fetcher": "_fetch_bond_rate_series_sync",
        "methodology": "US 10Y treasury yield from AkShare China/US bond yield table.",
    },
    "cn.rate.cn_us_10y_spread": {
        "name": "CN-US 10Y Yield Spread",
        "category": "rates",
        "frequency": "daily",
        "unit": "ppt",
        "source": "derived:akshare.bond_zh_us_rate",
        "is_derived": True,
        "dependencies": ("cn.rate.cn10y", "us.rate.us10y"),
        "methodology": "Derived as China 10Y yield minus US 10Y yield on matched dates.",
    },
    "cn.ppi.yoy": {
        "name": "PPI YoY",
        "category": "inflation",
        "frequency": "monthly",
        "unit": "%",
        "source_key": "macro:series:ppi",
        "source_name": "macro_china_ppi",
        "source": "akshare.macro_china_ppi",
        "fetcher": "_fetch_ppi_series_sync",
        "methodology": "China producer price index year-over-year growth from AkShare.",
    },
    "cn.cpi.yoy": {
        "name": "CPI YoY",
        "category": "inflation",
        "frequency": "monthly",
        "unit": "%",
        "source_key": "macro:series:cpi",
        "source_name": "macro_china_cpi",
        "source": "akshare.macro_china_cpi",
        "fetcher": "_fetch_cpi_series_sync",
        "methodology": "China consumer price index year-over-year growth from AkShare.",
    },
    "cn.pmi.manu": {
        "name": "Manufacturing PMI",
        "category": "activity",
        "frequency": "monthly",
        "unit": "index",
        "source_key": "macro:series:pmi",
        "source_name": "macro_china_pmi",
        "source": "akshare.macro_china_pmi",
        "fetcher": "_fetch_pmi_series_sync",
        "methodology": "Manufacturing PMI from AkShare macro China PMI table.",
    },
    "cn.activity.industrial_production_yoy": {
        "name": "Industrial Production YoY",
        "category": "activity",
        "frequency": "monthly",
        "unit": "%",
        "source_key": "macro:series:industrial_production",
        "source_name": "macro_china_industrial_production_yoy",
        "source": "akshare.macro_china_industrial_production_yoy",
        "fetcher": "_fetch_industrial_production_series_sync",
        "methodology": "Industrial value-added or industrial production YoY from AkShare public macro tables.",
    },
    "cn.credit.social_financing_yoy": {
        "name": "Social Financing YoY",
        "category": "credit",
        "frequency": "monthly",
        "unit": "%",
        "source_key": "macro:series:social_financing",
        "source_name": "macro_china_shrzgm",
        "source": "akshare.macro_china_shrzgm",
        "fetcher": "_fetch_social_financing_series_sync",
        "methodology": "Social financing stock YoY from AkShare public macro table when available.",
    },
    "cn.credit.new_rmb_loans": {
        "name": "New RMB Loans",
        "category": "credit",
        "frequency": "monthly",
        "unit": "CNY",
        "source_key": "macro:series:new_financial_credit",
        "source_name": "macro_china_new_financial_credit",
        "source": "akshare.macro_china_new_financial_credit",
        "fetcher": "_fetch_new_credit_series_sync",
        "methodology": "New RMB loan flow from AkShare China new financial credit table.",
    },
    "fx.usdcnh": {
        "name": "USD/CNH",
        "category": "fx",
        "frequency": "daily",
        "unit": "CNH",
        "source_key": "macro:series:fx_usdcnh",
        "source_name": "forex_hist_em_usdcnh",
        "source": "akshare.forex_hist_em",
        "fetcher": "_fetch_usdcnh_series_sync",
        "methodology": "USD/CNH historical quotes from Eastmoney through AkShare when the function is available.",
    },
    "fx.dxy": {
        "name": "DXY",
        "category": "fx",
        "frequency": "daily",
        "unit": "index",
        "source_key": "macro:series:dxy",
        "source_name": "index_global_hist_em_dxy",
        "source": "akshare.index_global_hist_em",
        "fetcher": "_fetch_dxy_series_sync",
        "methodology": "Dollar index proxy from AkShare global index history when the function is available.",
    },
    "cn.rates.repo.dr007": {
        "name": "DR007 Proxy",
        "category": "rates",
        "frequency": "daily",
        "unit": "%",
        "source_key": "macro:series:repo_dr007",
        "source_name": "repo_rate_hist",
        "source": "akshare.repo_rate_hist",
        "fetcher": "_fetch_repo_dr007_series_sync",
        "methodology": "Public repo-rate proxy for DR007; exact official DR007 feed is not bundled.",
    },
}

UNAVAILABLE_SERIES_SPECS: dict[str, dict[str, str]] = {
    "cn.market.financing_ratio": {
        "name": "All A Margin Financing Ratio",
        "category": "market",
        "frequency": "daily",
        "unit": "%",
        "source": "unavailable",
        "methodology": "Requires margin balance divided by total A-share market cap. Public proxy is not wired yet.",
    },
    "cn.market.dividend_yield_all_a": {
        "name": "All A Dividend Yield",
        "category": "market",
        "frequency": "daily",
        "unit": "%",
        "source": "unavailable",
        "methodology": "Requires all-A dividend yield constituent aggregation or licensed index feed. Public proxy is not wired yet.",
    },
    "cn.market.turnover_rate_all_a": {
        "name": "All A Turnover Rate",
        "category": "market",
        "frequency": "daily",
        "unit": "%",
        "source": "unavailable",
        "methodology": "Requires full-market turnover divided by free-float or market-cap denominator. Public proxy is not wired yet.",
    },
    "cn.real_estate.loan_yoy": {
        "name": "Real Estate Loan YoY",
        "category": "property",
        "frequency": "quarterly",
        "unit": "%",
        "source": "unavailable",
        "methodology": "Official real-estate loan balance feed is not connected; return unavailable instead of sample data.",
    },
    "cn.special_bond.progress": {
        "name": "Special Bond Issuance Progress",
        "category": "fiscal",
        "frequency": "monthly",
        "unit": "%",
        "source": "unavailable",
        "methodology": "Requires official quota and issuance schedule; return unavailable until connected.",
    },
}


class MacroDataService:
    def __init__(
        self,
        akshare_module: object | None = None,
        snapshot_cache: MarketSnapshotCache | None = None,
    ) -> None:
        self.akshare_module = akshare_module
        self.snapshot_cache = snapshot_cache or MarketSnapshotCache(_default_macro_cache_path())
        self._source_failure_cache: dict[str, tuple[float, str]] = {}

    async def dashboard(self) -> MacroDashboardResponse:
        (
            (rates, lpr_status),
            (cpi_items, cpi_status),
            (gdp_items, gdp_status),
            (pmi_items, pmi_status),
            (credit_items, credit_status),
            (bond_yields, bond_status),
            (fx_rates, fx_status),
        ) = await asyncio.gather(
            self._cached_macro_source(
                key="macro:china_lpr",
                name="macro_china_lpr",
                source="akshare.macro_china_lpr",
                fetcher=self._fetch_lpr_sync,
                empty_value=_unavailable_points(
                    [
                        ("LPR 1Y", "%", "akshare.macro_china_lpr"),
                        ("LPR 5Y", "%", "akshare.macro_china_lpr"),
                    ]
                ),
            ),
            self._cached_macro_source(
                key="macro:china_cpi",
                name="macro_china_cpi",
                source="akshare.macro_china_cpi",
                fetcher=self._fetch_cpi_sync,
                empty_value=_unavailable_points([("China CPI YoY", "%", "akshare.macro_china_cpi")]),
            ),
            self._cached_macro_source(
                key="macro:china_gdp",
                name="macro_china_gdp",
                source="akshare.macro_china_gdp",
                fetcher=self._fetch_gdp_sync,
                empty_value=_unavailable_points([("China GDP YoY", "%", "akshare.macro_china_gdp")]),
            ),
            self._cached_macro_source(
                key="macro:china_pmi",
                name="macro_china_pmi",
                source="akshare.macro_china_pmi",
                fetcher=self._fetch_pmi_sync,
                empty_value=_unavailable_points([("China Manufacturing PMI", "index", "akshare.macro_china_pmi")]),
            ),
            self._cached_macro_source(
                key="macro:china_new_financial_credit",
                name="macro_china_new_financial_credit",
                source="akshare.macro_china_new_financial_credit",
                fetcher=self._fetch_credit_sync,
                empty_value=_unavailable_points(
                    [("China New RMB Loans", "CNY", "akshare.macro_china_new_financial_credit")]
                ),
            ),
            self._cached_macro_source(
                key="macro:bond_zh_us_rate",
                name="bond_zh_us_rate",
                source="akshare.bond_zh_us_rate",
                fetcher=self._fetch_bond_yields_sync,
                empty_value=_unavailable_points(
                    [
                        ("China 10Y Government Bond Yield", "%", "akshare.bond_zh_us_rate"),
                        ("US 10Y Treasury Yield", "%", "akshare.bond_zh_us_rate"),
                    ]
                ),
            ),
            self._cached_macro_source(
                key="macro:currency_boc_sina",
                name="currency_boc_sina",
                source="akshare.currency_boc_sina",
                fetcher=self._fetch_fx_rates_sync,
                empty_value=_unavailable_points(
                    [
                        ("USD/CNY", "CNY", "akshare.currency_boc_sina"),
                        ("EUR/CNY", "CNY", "akshare.currency_boc_sina"),
                    ]
                ),
            ),
        )
        source_status = [lpr_status, cpi_status, gdp_status, pmi_status, credit_status, bond_status, fx_status]
        return MacroDashboardResponse(
            as_of=datetime.now(UTC),
            cache_status=_macro_cache_status(source_status),
            source_status=source_status,
            rates=rates,
            indicators=[*cpi_items, *gdp_items, *pmi_items, *credit_items],
            bond_yields=bond_yields,
            fx_rates=fx_rates,
            disclaimer="Free public macro sources may be delayed, missing, or cached; unavailable fields are returned as null.",
        )

    async def timeseries(
        self,
        series_ids: list[str] | None = None,
        start: str | None = None,
        end: str | None = None,
        max_points: int = 600,
    ) -> MacroTimeseriesResponse:
        requested_ids = [item.strip() for item in (series_ids or DEFAULT_MACRO_SERIES_IDS) if item.strip()]
        if not requested_ids:
            requested_ids = DEFAULT_MACRO_SERIES_IDS
        end_date = _parse_date_boundary(end) or datetime.now(UTC).date()
        start_date = _parse_date_boundary(start) or (end_date - timedelta(days=365 * 10))
        if start_date > end_date:
            start_date, end_date = end_date, start_date
        max_points = max(1, min(max_points, 5000))

        needed_ids = list(requested_ids)
        for series_id in requested_ids:
            dependencies = MACRO_SERIES_SPECS.get(series_id, {}).get("dependencies", ())
            for dependency in dependencies:
                if dependency not in needed_ids:
                    needed_ids.append(dependency)

        data_by_id: dict[str, list[MacroTimeseriesPoint]] = {}
        status_by_name: dict[str, MacroSourceStatus] = {}
        direct_specs: dict[str, dict[str, Any]] = {}
        for series_id in needed_ids:
            spec = MACRO_SERIES_SPECS.get(series_id)
            if spec is not None and "source_key" in spec:
                direct_specs.setdefault(str(spec["source_key"]), spec)

        for source_key, spec in direct_specs.items():
            fetcher = getattr(self, str(spec["fetcher"]))
            source_payload, status = await self._cached_series_source(
                key=source_key,
                name=str(spec["source_name"]),
                source=str(spec["source"]),
                fetcher=fetcher,
                timeout_seconds=MACRO_SOURCE_TIMEOUT_SECONDS,
            )
            status_by_name[status.name] = status
            data_by_id.update(source_payload)

        for series_id in needed_ids:
            spec = MACRO_SERIES_SPECS.get(series_id)
            if spec is None or not spec.get("is_derived"):
                continue
            dependencies = spec.get("dependencies", ())
            if len(dependencies) == 2:
                data_by_id[series_id] = _derive_difference_points(
                    data_by_id.get(str(dependencies[0]), []),
                    data_by_id.get(str(dependencies[1]), []),
                )

        response_series: list[MacroTimeseriesSeries] = []
        for series_id in requested_ids:
            spec = MACRO_SERIES_SPECS.get(series_id) or UNAVAILABLE_SERIES_SPECS.get(series_id)
            if spec is None:
                spec = {
                    "name": series_id,
                    "category": "unknown",
                    "frequency": "unknown",
                    "unit": "",
                    "source": "unavailable",
                    "methodology": "No public source mapping is configured for this series id.",
                }
            filtered_points = _filter_timeseries_points(data_by_id.get(series_id, []), start_date, end_date, max_points)
            source = str(spec.get("source", "unavailable"))
            status: MacroSourceState = "live" if filtered_points else "unavailable"
            if source == "unavailable":
                status = "unavailable"
            source_name = str(spec.get("source_name") or series_id)
            if source == "unavailable" or spec is UNAVAILABLE_SERIES_SPECS.get(series_id):
                status_by_name.setdefault(
                    source_name,
                    MacroSourceStatus(
                        name=source_name,
                        status="unavailable",
                        source=source,
                        detail=str(spec.get("methodology", "source unavailable")),
                    ),
                )
            response_series.append(
                MacroTimeseriesSeries(
                    series_id=series_id,
                    name=str(spec.get("name", series_id)),
                    category=str(spec.get("category", "unknown")),
                    frequency=str(spec.get("frequency", "unknown")),
                    unit=str(spec.get("unit", "")),
                    source=source,
                    status=status,
                    methodology=str(spec.get("methodology", "")),
                    is_derived=bool(spec.get("is_derived", False)),
                    description=str(spec.get("description", "")),
                    points=filtered_points,
                )
            )

        return MacroTimeseriesResponse(
            ts=datetime.now(UTC),
            start=start_date.isoformat(),
            end=end_date.isoformat(),
            series=response_series,
            source_status=list(status_by_name.values()),
            disclaimer=(
                "Free public macro sources may be delayed, cached, unavailable, or proxy-based; "
                "unavailable fields are returned without sample data."
            ),
        )

    async def _cached_macro_source(
        self,
        key: str,
        name: str,
        source: str,
        fetcher: Callable[[], list[MacroDataPoint]],
        empty_value: list[MacroDataPoint],
        timeout_seconds: float = MACRO_SOURCE_TIMEOUT_SECONDS,
    ) -> tuple[list[MacroDataPoint], MacroSourceStatus]:
        cached = self.snapshot_cache.get(key)
        if cached is not None and not cached.is_stale:
            return _points_from_payload(cached.payload), MacroSourceStatus(
                name=name,
                status="live",
                source=cached.source,
                detail="served from fresh SQLite cache",
                as_of=cached.fetched_at,
            )
        failed = self._source_failure_cache.get(key)
        if failed is not None and time.time() - failed[0] < MACRO_FAILURE_COOLDOWN_SECONDS:
            detail = f"recent source failure: {failed[1]}"
            if cached is not None:
                return _mark_points_stale(_points_from_payload(cached.payload)), _cached_status(name, cached, detail)
            return _mark_points(empty_value, "unavailable"), MacroSourceStatus(
                name=name,
                status="unavailable",
                source=source,
                detail=detail,
            )

        try:
            result = await asyncio.wait_for(asyncio.to_thread(fetcher), timeout=timeout_seconds)
            if not any(item.status != "unavailable" and item.value is not None for item in result):
                raise RuntimeError("source returned no recognized values")
            self.snapshot_cache.save(
                key,
                {"items": [item.model_dump(mode="json") for item in result]},
                source,
                MACRO_SNAPSHOT_TTL_SECONDS,
            )
            self._source_failure_cache.pop(key, None)
            return result, MacroSourceStatus(name=name, status="live", source=source, as_of=datetime.now(UTC))
        except Exception as exc:
            detail = f"source timed out after {timeout_seconds:g}s" if isinstance(exc, TimeoutError) else str(exc)
            self._source_failure_cache[key] = (time.time(), detail)
            cached = self.snapshot_cache.get(key)
            if cached is not None:
                return _mark_points_stale(_points_from_payload(cached.payload)), _cached_status(name, cached, detail)
            return _mark_points(empty_value, "unavailable"), MacroSourceStatus(
                name=name,
                status="unavailable",
                source=source,
                detail=detail,
            )

    async def _cached_series_source(
        self,
        key: str,
        name: str,
        source: str,
        fetcher: Callable[[], dict[str, list[MacroTimeseriesPoint]]],
        timeout_seconds: float = MACRO_SOURCE_TIMEOUT_SECONDS,
    ) -> tuple[dict[str, list[MacroTimeseriesPoint]], MacroSourceStatus]:
        cached = self.snapshot_cache.get(key)
        if cached is not None and not cached.is_stale:
            return _series_points_from_payload(cached.payload), MacroSourceStatus(
                name=name,
                status="live",
                source=cached.source,
                detail="served from fresh SQLite cache",
                as_of=cached.fetched_at,
            )
        failed = self._source_failure_cache.get(key)
        if failed is not None and time.time() - failed[0] < MACRO_FAILURE_COOLDOWN_SECONDS:
            detail = f"recent source failure: {failed[1]}"
            if cached is not None:
                return _series_points_from_payload(cached.payload), _cached_status(name, cached, detail)
            return {}, MacroSourceStatus(name=name, status="unavailable", source=source, detail=detail)

        try:
            result = await asyncio.wait_for(asyncio.to_thread(fetcher), timeout=timeout_seconds)
            if not any(points for points in result.values()):
                raise RuntimeError("source returned no recognized series values")
            self.snapshot_cache.save(
                key,
                {"series": {series_id: [point.model_dump(mode="json") for point in points] for series_id, points in result.items()}},
                source,
                MACRO_SNAPSHOT_TTL_SECONDS,
            )
            self._source_failure_cache.pop(key, None)
            return result, MacroSourceStatus(name=name, status="live", source=source, as_of=datetime.now(UTC))
        except Exception as exc:
            detail = f"source timed out after {timeout_seconds:g}s" if isinstance(exc, TimeoutError) else str(exc)
            self._source_failure_cache[key] = (time.time(), detail)
            cached = self.snapshot_cache.get(key)
            if cached is not None:
                return _series_points_from_payload(cached.payload), _cached_status(name, cached, detail)
            return {}, MacroSourceStatus(name=name, status="unavailable", source=source, detail=detail)

    def _fetch_lpr_sync(self) -> list[MacroDataPoint]:
        rows = _records(self._akshare().macro_china_lpr())
        row = _latest_row(rows, ("date", "日期", "公布日期"))
        as_of = _row_as_of(row, ("date", "日期", "公布日期"))
        source = "akshare.macro_china_lpr"
        return [
            _point("LPR 1Y", _row_value(row, ("lpr_1y", "1年", "1年LPR", "1Y")), "%", as_of, source),
            _point("LPR 5Y", _row_value(row, ("lpr_5y", "5年", "5年LPR", "5Y")), "%", as_of, source),
        ]

    def _fetch_cpi_sync(self) -> list[MacroDataPoint]:
        rows = _records(self._akshare().macro_china_cpi())
        row = _latest_row(rows, ("month", "date", "月份", "日期"))
        as_of = _row_as_of(row, ("month", "date", "月份", "日期"))
        value = _row_value(row, ("cpi_yoy", "同比", "全国同比", "全国-同比增长", "CPI同比"))
        return [_point("China CPI YoY", value, "%", as_of, "akshare.macro_china_cpi")]

    def _fetch_gdp_sync(self) -> list[MacroDataPoint]:
        rows = _records(self._akshare().macro_china_gdp())
        row = _latest_row(rows, ("quarter", "date", "季度", "日期"))
        as_of = _row_as_of(row, ("quarter", "date", "季度", "日期"))
        value = _row_value(row, ("gdp_yoy", "同比", "国内生产总值-同比增长", "GDP同比"))
        return [_point("China GDP YoY", value, "%", as_of, "akshare.macro_china_gdp")]

    def _fetch_pmi_sync(self) -> list[MacroDataPoint]:
        rows = _records(self._akshare().macro_china_pmi())
        row = _latest_row(rows, ("month", "date", "月份", "日期"))
        as_of = _row_as_of(row, ("month", "date", "月份", "日期"))
        value = _row_value(row, ("manufacturing_pmi", "制造业PMI", "制造业采购经理指数", "PMI"))
        return [_point("China Manufacturing PMI", value, "index", as_of, "akshare.macro_china_pmi")]

    def _fetch_credit_sync(self) -> list[MacroDataPoint]:
        rows = _records(self._akshare().macro_china_new_financial_credit())
        row = _latest_row(rows, ("month", "date", "月份", "日期"))
        as_of = _row_as_of(row, ("month", "date", "月份", "日期"))
        value = _money_value(
            _row_value(row, ("new_rmb_loans", "新增人民币贷款", "人民币贷款增加", "新增贷款")),
            row,
        )
        return [_point("China New RMB Loans", value, "CNY", as_of, "akshare.macro_china_new_financial_credit")]

    def _fetch_bond_yields_sync(self) -> list[MacroDataPoint]:
        rows = _records(self._akshare().bond_zh_us_rate())
        row = _latest_row(rows, ("date", "日期"))
        as_of = _row_as_of(row, ("date", "日期"))
        source = "akshare.bond_zh_us_rate"
        return [
            _point(
                "China 10Y Government Bond Yield",
                _row_value(row, ("china_10y", "中国10年期国债收益率", "中国国债收益率10年", "中国10年")),
                "%",
                as_of,
                source,
            ),
            _point(
                "US 10Y Treasury Yield",
                _row_value(row, ("us_10y", "美国10年期国债收益率", "美国国债收益率10年", "美国10年")),
                "%",
                as_of,
                source,
            ),
        ]

    def _fetch_fx_rates_sync(self) -> list[MacroDataPoint]:
        rows = _records(self._akshare().currency_boc_sina())
        source = "akshare.currency_boc_sina"
        items: list[MacroDataPoint] = []
        for code in ("USD", "EUR"):
            row = _latest_currency_row(rows, code)
            as_of = _row_as_of(row, ("date", "日期", "发布日期", "发布时间"))
            value = _fx_value(_row_value(row, ("boc_mid", "中行折算价", "央行中间价", "汇率")))
            items.append(_point(f"{code}/CNY", value, "CNY", as_of, source))
        return items

    def _fetch_money_supply_series_sync(self) -> dict[str, list[MacroTimeseriesPoint]]:
        rows = _records(self._akshare().macro_china_money_supply())
        date_fields = ("month", "date", "\u6708\u4efd", "\u65e5\u671f", "\u7edf\u8ba1\u65f6\u95f4")
        return {
            "cn.money.m1_yoy": _series_points(rows, date_fields, ("m1_yoy", "M1同比", "M1同比增长", "\u8d27\u5e01\u4f9b\u5e94\u91cf-M1\u540c\u6bd4")),
            "cn.money.m2_yoy": _series_points(rows, date_fields, ("m2_yoy", "M2同比", "M2同比增长", "\u8d27\u5e01\u4f9b\u5e94\u91cf-M2\u540c\u6bd4")),
        }

    def _fetch_bond_rate_series_sync(self) -> dict[str, list[MacroTimeseriesPoint]]:
        rows = _records(self._akshare().bond_zh_us_rate())
        date_fields = ("date", "\u65e5\u671f", "trade_date", "TRADE_DATE")
        return {
            "cn.rate.cn10y": _series_points(
                rows,
                date_fields,
                ("china_10y", "\u4e2d\u56fd10\u5e74\u671f\u56fd\u503a\u6536\u76ca\u7387", "\u4e2d\u56fd\u56fd\u503a\u6536\u76ca\u738710\u5e74", "\u4e2d\u56fd10\u5e74"),
            ),
            "us.rate.us10y": _series_points(
                rows,
                date_fields,
                ("us_10y", "\u7f8e\u56fd10\u5e74\u671f\u56fd\u503a\u6536\u76ca\u7387", "\u7f8e\u56fd\u56fd\u503a\u6536\u76ca\u738710\u5e74", "\u7f8e\u56fd10\u5e74"),
            ),
        }

    def _fetch_ppi_series_sync(self) -> dict[str, list[MacroTimeseriesPoint]]:
        rows = _records(self._akshare().macro_china_ppi())
        return {
            "cn.ppi.yoy": _series_points(
                rows,
                ("month", "date", "\u6708\u4efd", "\u65e5\u671f"),
                ("ppi_yoy", "PPI同比", "\u5168\u56fd\u5de5\u4e1a\u751f\u4ea7\u8005\u51fa\u5382\u4ef7\u683c\u540c\u6bd4", "\u540c\u6bd4"),
            )
        }

    def _fetch_cpi_series_sync(self) -> dict[str, list[MacroTimeseriesPoint]]:
        rows = _records(self._akshare().macro_china_cpi())
        return {
            "cn.cpi.yoy": _series_points(
                rows,
                ("month", "date", "\u6708\u4efd", "\u65e5\u671f"),
                ("cpi_yoy", "CPI同比", "\u5168\u56fd\u540c\u6bd4", "\u540c\u6bd4"),
            )
        }

    def _fetch_pmi_series_sync(self) -> dict[str, list[MacroTimeseriesPoint]]:
        rows = _records(self._akshare().macro_china_pmi())
        return {
            "cn.pmi.manu": _series_points(
                rows,
                ("month", "date", "\u6708\u4efd", "\u65e5\u671f"),
                ("manufacturing_pmi", "PMI", "\u5236\u9020\u4e1aPMI", "\u5236\u9020\u4e1a-\u6307\u6570", "\u5236\u9020\u4e1a\u91c7\u8d2d\u7ecf\u7406\u6307\u6570"),
            )
        }

    def _fetch_industrial_production_series_sync(self) -> dict[str, list[MacroTimeseriesPoint]]:
        akshare = self._akshare()
        if hasattr(akshare, "macro_china_industrial_production_yoy"):
            rows = _records(akshare.macro_china_industrial_production_yoy())
        else:
            rows = _records(akshare.macro_china_gyzjz())
        return {
            "cn.activity.industrial_production_yoy": _series_points(
                rows,
                ("month", "date", "\u6708\u4efd", "\u65e5\u671f"),
                ("industrial_production_yoy", "\u5de5\u4e1a\u589e\u52a0\u503c\u540c\u6bd4", "\u540c\u6bd4\u589e\u957f", "\u5f53\u6708\u540c\u6bd4", "\u540c\u6bd4"),
            )
        }

    def _fetch_social_financing_series_sync(self) -> dict[str, list[MacroTimeseriesPoint]]:
        rows = _records(self._akshare().macro_china_shrzgm())
        return {
            "cn.credit.social_financing_yoy": _series_points(
                rows,
                ("month", "date", "\u6708\u4efd", "\u65e5\u671f"),
                ("social_financing_yoy", "\u793e\u4f1a\u878d\u8d44\u89c4\u6a21\u5b58\u91cf\u540c\u6bd4", "\u589e\u901f", "\u540c\u6bd4"),
            )
        }

    def _fetch_new_credit_series_sync(self) -> dict[str, list[MacroTimeseriesPoint]]:
        rows = _records(self._akshare().macro_china_new_financial_credit())
        points: list[MacroTimeseriesPoint] = []
        for row in rows:
            point_date = _row_as_of(row, ("month", "date", "\u6708\u4efd", "\u65e5\u671f"))
            if point_date is None:
                continue
            value = _money_value(
                _row_value(row, ("new_rmb_loans", "\u65b0\u589e\u4eba\u6c11\u5e01\u8d37\u6b3e", "\u4eba\u6c11\u5e01\u8d37\u6b3e\u589e\u52a0", "\u5f53\u6708")),
                row,
            )
            if value is None:
                continue
            points.append(_timeseries_point(point_date, value))
        return {"cn.credit.new_rmb_loans": _sort_points(points)}

    def _fetch_usdcnh_series_sync(self) -> dict[str, list[MacroTimeseriesPoint]]:
        akshare = self._akshare()
        if not hasattr(akshare, "forex_hist_em"):
            return {"fx.usdcnh": []}
        try:
            rows = _records(akshare.forex_hist_em(symbol="USDCNH"))
        except TypeError:
            rows = _records(akshare.forex_hist_em("USDCNH"))
        return {
            "fx.usdcnh": _series_points(
                rows,
                ("date", "\u65e5\u671f", "trade_date", "\u65f6\u95f4"),
                ("close", "\u6536\u76d8", "\u6700\u65b0\u4ef7", "\u4e2d\u95f4\u4ef7"),
            )
        }

    def _fetch_dxy_series_sync(self) -> dict[str, list[MacroTimeseriesPoint]]:
        akshare = self._akshare()
        if not hasattr(akshare, "index_global_hist_em"):
            return {"fx.dxy": []}
        try:
            rows = _records(akshare.index_global_hist_em(symbol="\u7f8e\u5143\u6307\u6570"))
        except TypeError:
            rows = _records(akshare.index_global_hist_em("\u7f8e\u5143\u6307\u6570"))
        return {
            "fx.dxy": _series_points(
                rows,
                ("date", "\u65e5\u671f", "trade_date", "\u65f6\u95f4"),
                ("close", "\u6536\u76d8", "\u6700\u65b0\u4ef7"),
            )
        }

    def _fetch_repo_dr007_series_sync(self) -> dict[str, list[MacroTimeseriesPoint]]:
        akshare = self._akshare()
        if not hasattr(akshare, "repo_rate_hist"):
            return {"cn.rates.repo.dr007": []}
        rows = _records(akshare.repo_rate_hist())
        return {
            "cn.rates.repo.dr007": _series_points(
                rows,
                ("date", "\u65e5\u671f", "trade_date"),
                ("DR007", "dr007", "FDR007", "FR007", "\u5229\u7387", "\u52a0\u6743\u5229\u7387"),
            )
        }

    def _akshare(self) -> object:
        if self.akshare_module is None:
            self.akshare_module = importlib.import_module("akshare")
        return self.akshare_module


def _records(table: object) -> list[Mapping[str, object]]:
    if hasattr(table, "to_dict"):
        raw_records = table.to_dict("records")
    else:
        raw_records = table
    if not isinstance(raw_records, Iterable):
        return []
    return [row for row in raw_records if isinstance(row, Mapping)]


def _latest_row(rows: list[Mapping[str, object]], date_fields: tuple[str, ...]) -> Mapping[str, object]:
    if not rows:
        return {}
    dated_rows: list[tuple[datetime, Mapping[str, object]]] = []
    for row in rows:
        parsed = _row_as_of(row, date_fields)
        if parsed is not None:
            dated_rows.append((parsed, row))
    if dated_rows:
        return max(dated_rows, key=lambda item: item[0])[1]
    return rows[-1]


def _latest_currency_row(rows: list[Mapping[str, object]], code: str) -> Mapping[str, object]:
    matching = [row for row in rows if _currency_code(_row_value(row, ("currency", "货币", "币种", "货币名称"))) == code]
    return _latest_row(matching, ("date", "日期", "发布日期", "发布时间")) if matching else {}


def _row_value(row: Mapping[str, object], names: tuple[str, ...]) -> object:
    if not row:
        return None
    for name in names:
        if name in row:
            return row[name]
    normalized = {_normalize_key(name) for name in names}
    for key, value in row.items():
        if _normalize_key(str(key)) in normalized:
            return value
    for key, value in row.items():
        key_text = str(key).lower()
        if any(name.lower() in key_text or key_text in name.lower() for name in names):
            return value
    return None


def _normalize_key(value: str) -> str:
    return value.lower().replace(" ", "").replace("_", "").replace("-", "")


def _row_as_of(row: Mapping[str, object], fields: tuple[str, ...]) -> datetime | None:
    return _parse_datetime(_row_value(row, fields))


def _parse_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    text = str(value).strip()
    if not text:
        return None
    if "Q" in text.upper():
        try:
            year, quarter = text.upper().split("Q", 1)
            month = int(quarter) * 3
            return datetime(int(year), month, 1, tzinfo=UTC)
        except (TypeError, ValueError):
            return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d", "%Y-%m", "%Y/%m"):
        try:
            return datetime.strptime(text[: len(datetime.now().strftime(fmt))], fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def _point(name: str, value: object, unit: str, as_of: datetime | None, source: str) -> MacroDataPoint:
    numeric = _number(value)
    return MacroDataPoint(
        name=name,
        value=numeric,
        unit=unit,
        as_of=as_of if numeric is not None else None,
        source=source,
        status="live" if numeric is not None else "unavailable",
    )


def _number(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, int | float):
        if value != value:
            return None
        return round(float(value), 6)
    text = str(value).strip().replace(",", "")
    if not text or text in {"--", "-", "None", "nan"}:
        return None
    multiplier = 1.0
    if text.endswith("亿元"):
        multiplier = 100000000.0
        text = text[:-2]
    elif text.endswith("万元"):
        multiplier = 10000.0
        text = text[:-2]
    elif text.endswith("亿"):
        multiplier = 100000000.0
        text = text[:-1]
    elif text.endswith("万"):
        multiplier = 10000.0
        text = text[:-1]
    if text.endswith("%"):
        text = text[:-1]
    try:
        return round(float(text) * multiplier, 6)
    except ValueError:
        return None


def _money_value(value: object, row: Mapping[str, object]) -> float | None:
    numeric = _number(value)
    if numeric is None:
        return None
    value_text = str(value or "")
    if any(token in value_text for token in ("亿", "万", "元")):
        return numeric
    unit_text = str(_row_value(row, ("unit", "单位")) or "")
    if "亿" in unit_text:
        return numeric * 100000000
    if "万" in unit_text:
        return numeric * 10000
    return numeric


def _fx_value(value: object) -> float | None:
    numeric = _number(value)
    if numeric is None:
        return None
    if numeric > 20:
        numeric /= 100
    return round(numeric, 6)


def _currency_code(value: object) -> str:
    text = str(value or "").upper()
    if "USD" in text or "美元" in text:
        return "USD"
    if "EUR" in text or "欧元" in text:
        return "EUR"
    if "GBP" in text or "英镑" in text:
        return "GBP"
    if "JPY" in text or "日元" in text:
        return "JPY"
    if "HKD" in text or "港币" in text:
        return "HKD"
    return text


def _parse_date_boundary(value: str | None) -> date | None:
    if not value:
        return None
    parsed = _parse_datetime(value)
    return parsed.date() if parsed is not None else None


def _series_points(
    rows: list[Mapping[str, object]],
    date_fields: tuple[str, ...],
    value_fields: tuple[str, ...],
) -> list[MacroTimeseriesPoint]:
    points: list[MacroTimeseriesPoint] = []
    for row in rows:
        point_date = _row_as_of(row, date_fields)
        if point_date is None:
            continue
        numeric = _number(_row_value(row, value_fields))
        if numeric is None:
            continue
        points.append(_timeseries_point(point_date, numeric, _row_as_of(row, ("release_date", "\u53d1\u5e03\u65e5\u671f"))))
    return _sort_points(points)


def _timeseries_point(point_date: datetime, value: float, release_date: datetime | None = None) -> MacroTimeseriesPoint:
    day = point_date.date().isoformat()
    return MacroTimeseriesPoint(
        date=day,
        point_date=day,
        release_date=release_date.date().isoformat() if release_date is not None else None,
        value=round(value, 6),
    )


def _sort_points(points: list[MacroTimeseriesPoint]) -> list[MacroTimeseriesPoint]:
    return sorted(points, key=lambda point: point.date)


def _filter_timeseries_points(
    points: list[MacroTimeseriesPoint],
    start_date: date,
    end_date: date,
    max_points: int,
) -> list[MacroTimeseriesPoint]:
    filtered = []
    for point in points:
        try:
            point_day = date.fromisoformat(point.date[:10])
        except ValueError:
            continue
        if start_date <= point_day <= end_date:
            filtered.append(point)
    return filtered[-max_points:]


def _derive_difference_points(
    left: list[MacroTimeseriesPoint],
    right: list[MacroTimeseriesPoint],
) -> list[MacroTimeseriesPoint]:
    right_by_date = {point.date: point for point in right if point.value is not None}
    points: list[MacroTimeseriesPoint] = []
    for left_point in left:
        right_point = right_by_date.get(left_point.date)
        if left_point.value is None or right_point is None or right_point.value is None:
            continue
        points.append(
            MacroTimeseriesPoint(
                date=left_point.date,
                point_date=left_point.point_date or left_point.date,
                release_date=left_point.release_date or right_point.release_date,
                value=round(left_point.value - right_point.value, 6),
            )
        )
    return points


def _series_points_from_payload(payload: dict[str, Any]) -> dict[str, list[MacroTimeseriesPoint]]:
    raw_series = payload.get("series", {})
    if not isinstance(raw_series, Mapping):
        return {}
    result: dict[str, list[MacroTimeseriesPoint]] = {}
    for series_id, points in raw_series.items():
        if isinstance(points, list):
            result[str(series_id)] = [MacroTimeseriesPoint.model_validate(point) for point in points]
    return result


def _points_from_payload(payload: dict[str, Any]) -> list[MacroDataPoint]:
    return [MacroDataPoint.model_validate(item) for item in payload.get("items", [])]


def _unavailable_points(items: list[tuple[str, str, str]]) -> list[MacroDataPoint]:
    return [MacroDataPoint(name=name, value=None, unit=unit, as_of=None, source=source, status="unavailable") for name, unit, source in items]


def _mark_points(items: list[MacroDataPoint], status: MacroSourceState) -> list[MacroDataPoint]:
    return [item.model_copy(update={"status": status, "value": item.value if status != "unavailable" else None}) for item in items]


def _mark_points_stale(items: list[MacroDataPoint]) -> list[MacroDataPoint]:
    return [item.model_copy(update={"status": "stale" if item.status == "live" else item.status}) for item in items]


def _cached_status(name: str, cached: CachedSnapshot, detail: str) -> MacroSourceStatus:
    return MacroSourceStatus(name=name, status="stale", source=cached.source, detail=detail, as_of=cached.fetched_at)


def _macro_cache_status(statuses: list[MacroSourceStatus]) -> MacroCacheStatus:
    if not statuses:
        return "unavailable"
    if all(item.status == "live" for item in statuses):
        return "live"
    if any(item.status == "stale" for item in statuses):
        return "stale"
    if any(item.status == "live" for item in statuses):
        return "partial"
    return "unavailable"


def _default_macro_cache_path() -> Path:
    return Path(__file__).resolve().parents[3] / ".runtime" / "macro_cache.sqlite3"
