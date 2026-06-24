import asyncio
import importlib
import math
import os
from collections.abc import Iterable, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime

from app.schemas.etfs import ETFCandleItem, ETFCandlesResponse, ETFQuoteItem, ETFSearchResponse

ETF_SPOT_SOURCE = "akshare-eastmoney-etf-spot"
ETF_HISTORY_SOURCE = "akshare-eastmoney-etf-history"
ETF_HISTORY_SINA_SOURCE = "akshare-sina-etf-history"


class ETFService:
    def __init__(self, akshare_module: object | None = None) -> None:
        self.akshare_module = akshare_module

    async def search(self, q: str = "", limit: int = 50) -> ETFSearchResponse:
        return await asyncio.to_thread(self._search_sync, q, limit)

    async def candles(self, symbol: str, period: str = "daily", limit: int = 120) -> ETFCandlesResponse:
        return await asyncio.to_thread(self._candles_sync, symbol, period, limit)

    def _search_sync(self, q: str, limit: int) -> ETFSearchResponse:
        try:
            akshare = self._akshare()
            with _without_proxy_env():
                rows = _records(akshare.fund_etf_spot_em())
        except Exception as exc:
            return ETFSearchResponse(
                items=[],
                source=ETF_SPOT_SOURCE,
                as_of=None,
                status="unavailable",
                detail=str(exc),
            )

        query = q.strip()
        upper_query = query.upper()
        items: list[ETFQuoteItem] = []
        for row in rows:
            item = _etf_quote_from_row(row)
            if item is None:
                continue
            if query and query not in item.name and upper_query not in item.symbol.upper():
                continue
            items.append(item)
            if len(items) >= max(1, min(limit, 200)):
                break
        return ETFSearchResponse(
            items=items,
            source=ETF_SPOT_SOURCE,
            as_of=datetime.now(UTC),
            status="live",
        )

    def _candles_sync(self, symbol: str, period: str, limit: int) -> ETFCandlesResponse:
        normalized_symbol = _normalize_etf_symbol(symbol)
        normalized_period = period if period in {"daily", "weekly", "monthly"} else "daily"
        normalized_limit = max(1, min(limit, 500))
        history_source = ETF_HISTORY_SOURCE
        try:
            akshare = self._akshare()
            with _without_proxy_env():
                rows = _records(_fund_etf_hist(akshare, normalized_symbol, normalized_period))
        except Exception as exc:
            if normalized_period != "daily":
                return ETFCandlesResponse(
                    items=[],
                    source=ETF_HISTORY_SOURCE,
                    as_of=None,
                    status="unavailable",
                    detail=str(exc),
                )
            try:
                with _without_proxy_env():
                    rows = _records(_fund_etf_hist_sina(akshare, normalized_symbol))
                history_source = ETF_HISTORY_SINA_SOURCE
            except Exception as fallback_exc:
                return ETFCandlesResponse(
                    items=[],
                    source=ETF_HISTORY_SOURCE,
                    as_of=None,
                    status="unavailable",
                    detail=f"{exc}; sina fallback failed: {fallback_exc}",
                )

        candles = [_etf_candle_from_row(row, normalized_symbol, history_source) for row in rows]
        parsed = sorted([item for item in candles if item is not None], key=lambda item: item.date)
        return ETFCandlesResponse(
            items=parsed[-normalized_limit:],
            source=history_source,
            as_of=datetime.now(UTC),
            status="live",
        )

    def _akshare(self) -> object:
        if self.akshare_module is not None:
            return self.akshare_module
        return importlib.import_module("akshare")


def _fund_etf_hist(akshare: object, symbol: str, period: str) -> object:
    try:
        return akshare.fund_etf_hist_em(symbol=symbol, period=period, adjust="")
    except TypeError:
        return akshare.fund_etf_hist_em(symbol=symbol, period=period)


def _fund_etf_hist_sina(akshare: object, symbol: str) -> object:
    return akshare.fund_etf_hist_sina(symbol=_sina_etf_symbol(symbol))


def _etf_quote_from_row(row: Mapping[str, object]) -> ETFQuoteItem | None:
    symbol = _normalize_etf_symbol(_clean_text(_row_value(row, ("代码", "基金代码", "symbol", "code"))))
    name = _clean_text(_row_value(row, ("名称", "基金简称", "name")))
    if not symbol or not name:
        return None
    return ETFQuoteItem(
        symbol=symbol,
        name=name,
        price=_parse_float(_row_value(row, ("最新价", "price", "latest_price", "last_price"))),
        change_pct=_parse_float(_row_value(row, ("涨跌幅", "change_pct", "pct_chg", "changePercent"))),
        turnover=_parse_money(_row_value(row, ("成交额", "turnover", "amount"))),
        volume=_parse_float(_row_value(row, ("成交量", "volume"))),
        source=ETF_SPOT_SOURCE,
    )


def _etf_candle_from_row(row: Mapping[str, object], symbol: str, source: str) -> ETFCandleItem | None:
    date_value = _clean_text(_row_value(row, ("日期", "date", "时间")))
    open_value = _parse_float(_row_value(row, ("开盘", "open")))
    high_value = _parse_float(_row_value(row, ("最高", "high")))
    low_value = _parse_float(_row_value(row, ("最低", "low")))
    close_value = _parse_float(_row_value(row, ("收盘", "close", "最新价")))
    if not date_value or open_value is None or high_value is None or low_value is None or close_value is None:
        return None
    return ETFCandleItem(
        symbol=symbol,
        date=date_value[:10],
        open=open_value,
        high=high_value,
        low=low_value,
        close=close_value,
        volume=_parse_float(_row_value(row, ("成交量", "volume"))),
        turnover=_parse_money(_row_value(row, ("成交额", "turnover", "amount"))),
        source=source,
    )


def _normalize_etf_symbol(symbol: str) -> str:
    raw = symbol.strip().upper()
    if raw.endswith((".SH", ".SZ")):
        raw = raw[:-3]
    for prefix in ("SH", "SZ"):
        if raw.startswith(prefix) and raw[len(prefix):].isdigit():
            raw = raw[len(prefix):]
            break
    return raw


def _sina_etf_symbol(symbol: str) -> str:
    normalized = _normalize_etf_symbol(symbol)
    prefix = "sh" if normalized.startswith("5") else "sz"
    return f"{prefix}{normalized}"


def _parse_money(value: object) -> float | None:
    parsed = _parse_float(value)
    if parsed is not None and not _has_unit(value):
        return parsed
    text = str(value or "").strip().replace(",", "")
    if not text or text in {"--", "-", "None", "nan", "NaN"}:
        return None
    multiplier = 1.0
    if text.endswith("亿元"):
        multiplier = 100_000_000.0
        text = text[:-2]
    elif text.endswith("亿"):
        multiplier = 100_000_000.0
        text = text[:-1]
    elif text.endswith("万元"):
        multiplier = 10_000.0
        text = text[:-2]
    elif text.endswith("万"):
        multiplier = 10_000.0
        text = text[:-1]
    if text.endswith("%"):
        text = text[:-1]
    try:
        number = float(text)
    except ValueError:
        return None
    return round(number * multiplier, 4)


def _parse_float(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text or text in {"--", "-", "None", "nan", "NaN"}:
        return None
    if text.endswith("%"):
        text = text[:-1]
    try:
        number = float(text)
    except ValueError:
        return None
    if math.isnan(number):
        return None
    return round(number, 4)


def _has_unit(value: object) -> bool:
    text = str(value or "")
    return any(unit in text for unit in ("亿", "万"))


def _records(table: object) -> list[Mapping[str, object]]:
    if hasattr(table, "to_dict"):
        raw_records = table.to_dict("records")
    else:
        raw_records = table
    if not isinstance(raw_records, Iterable):
        return []
    return [row for row in raw_records if isinstance(row, Mapping)]


def _row_value(row: Mapping[str, object], names: tuple[str, ...]) -> object:
    for name in names:
        if name in row:
            return row[name]
    lower_names = {name.lower() for name in names}
    for key, value in row.items():
        if str(key).lower() in lower_names:
            return value
    return None


def _clean_text(value: object) -> str:
    return str(value or "").strip()


@contextmanager
def _without_proxy_env():
    proxy_keys = (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "no_proxy",
    )
    previous = {key: os.environ.get(key) for key in proxy_keys}
    try:
        for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
            os.environ.pop(key, None)
        os.environ["NO_PROXY"] = "*"
        os.environ["no_proxy"] = "*"
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
