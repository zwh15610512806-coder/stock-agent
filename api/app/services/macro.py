import asyncio
import importlib
import time
from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypeVar

from app.schemas.macro import MacroCacheStatus, MacroDashboardResponse, MacroDataPoint, MacroSourceState, MacroSourceStatus
from app.services.market_cache import CachedSnapshot, MarketSnapshotCache

MACRO_SOURCE = "akshare-macro-free"
MACRO_SNAPSHOT_TTL_SECONDS = 6 * 60 * 60
MACRO_SOURCE_TIMEOUT_SECONDS = 8.0
MACRO_FAILURE_COOLDOWN_SECONDS = 3 * 60
T = TypeVar("T")


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
