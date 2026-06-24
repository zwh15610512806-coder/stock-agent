import asyncio
import importlib
import math
import os
from collections.abc import Iterable, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime

from app.schemas.stocks import StockScreenerItem, StockScreenerResponse
from app.services.market import MarketDataService
from app.services.symbols import normalize_symbol, search_static_symbols

STOCK_SCREENER_SOURCE = "akshare-eastmoney-a-share-spot"
STOCK_SCREENER_FALLBACK_SOURCE = "symbol-pool+tencent-free-delayed"
STOCK_SCREENER_TIMEOUT_SECONDS = 8.0


class StockScreenerService:
    def __init__(self, akshare_module: object | None = None, market_service: object | None = None) -> None:
        self.akshare_module = akshare_module
        self.market_service = market_service or MarketDataService()

    async def screen(
        self,
        query: str = "",
        min_change_pct: float | None = None,
        max_change_pct: float | None = None,
        min_turnover: float | None = None,
        min_market_cap: float | None = None,
        max_pe: float | None = None,
        max_pb: float | None = None,
        limit: int = 50,
    ) -> StockScreenerResponse:
        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    self._screen_sync,
                    query,
                    min_change_pct,
                    max_change_pct,
                    min_turnover,
                    min_market_cap,
                    max_pe,
                    max_pb,
                    limit,
                ),
                timeout=STOCK_SCREENER_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            response = StockScreenerResponse(
                items=[],
                source=STOCK_SCREENER_SOURCE,
                as_of=None,
                status="unavailable",
                detail=f"primary screener timed out after {STOCK_SCREENER_TIMEOUT_SECONDS:g}s",
            )
        if response.status == "unavailable":
            fallback = await self._fallback_keyword_screen(
                query=query,
                min_change_pct=min_change_pct,
                max_change_pct=max_change_pct,
                min_turnover=min_turnover,
                min_market_cap=min_market_cap,
                max_pe=max_pe,
                max_pb=max_pb,
                limit=limit,
                failure_detail=response.detail,
            )
            if fallback.items:
                return fallback
        return response

    def _screen_sync(
        self,
        query: str,
        min_change_pct: float | None,
        max_change_pct: float | None,
        min_turnover: float | None,
        min_market_cap: float | None,
        max_pe: float | None,
        max_pb: float | None,
        limit: int,
    ) -> StockScreenerResponse:
        try:
            akshare = self._akshare()
            with _without_proxy_env():
                rows = _records(akshare.stock_zh_a_spot_em())
        except Exception as exc:
            return StockScreenerResponse(
                items=[],
                source=STOCK_SCREENER_SOURCE,
                as_of=None,
                status="unavailable",
                detail=str(exc),
            )

        normalized_query = query.strip()
        upper_query = normalized_query.upper()
        filtered: list[StockScreenerItem] = []
        for row in rows:
            item = _stock_item_from_row(row)
            if item is None:
                continue
            if normalized_query and not _matches_query(item, normalized_query, upper_query):
                continue
            if not _passes_min(item.change_pct, min_change_pct):
                continue
            if not _passes_max(item.change_pct, max_change_pct):
                continue
            if not _passes_min(item.turnover, min_turnover):
                continue
            if not _passes_min(item.market_cap, min_market_cap):
                continue
            if not _passes_max(item.pe, max_pe):
                continue
            if not _passes_max(item.pb, max_pb):
                continue
            filtered.append(item)
            if len(filtered) >= max(1, min(limit, 200)):
                break

        return StockScreenerResponse(
            items=filtered,
            source=STOCK_SCREENER_SOURCE,
            as_of=datetime.now(UTC),
            status="live",
        )

    def _akshare(self) -> object:
        if self.akshare_module is not None:
            return self.akshare_module
        return importlib.import_module("akshare")

    async def _fallback_keyword_screen(
        self,
        query: str,
        min_change_pct: float | None,
        max_change_pct: float | None,
        min_turnover: float | None,
        min_market_cap: float | None,
        max_pe: float | None,
        max_pb: float | None,
        limit: int,
        failure_detail: str,
    ) -> StockScreenerResponse:
        if not query.strip():
            return StockScreenerResponse(
                items=[],
                source=STOCK_SCREENER_FALLBACK_SOURCE,
                as_of=None,
                status="unavailable",
                detail=failure_detail,
            )
        candidates = search_static_symbols(query, {"CN"}, akshare_module=self.akshare_module)[: max(1, min(limit, 30))]
        items: list[StockScreenerItem] = []
        as_of: datetime | None = None
        for candidate in candidates:
            try:
                quote = await self.market_service.quote(candidate.symbol)
            except Exception:
                continue
            if str(getattr(quote, "source", "")).strip().lower() == "sample fallback":
                continue
            item = StockScreenerItem(
                symbol=candidate.symbol,
                code=_plain_code(candidate.symbol),
                name=candidate.name,
                exchange=candidate.exchange or _exchange_for_symbol(candidate.symbol),
                price=getattr(quote, "price", None),
                change_pct=getattr(quote, "change_pct", None),
                turnover=getattr(quote, "turnover", None),
                volume=getattr(quote, "volume", None),
                market_cap=None,
                pe=None,
                pb=None,
                source=str(getattr(quote, "source", STOCK_SCREENER_FALLBACK_SOURCE)) or STOCK_SCREENER_FALLBACK_SOURCE,
            )
            if not _passes_min(item.change_pct, min_change_pct):
                continue
            if not _passes_max(item.change_pct, max_change_pct):
                continue
            if not _passes_min(item.turnover, min_turnover):
                continue
            if not _passes_min(item.market_cap, min_market_cap):
                continue
            if not _passes_max(item.pe, max_pe):
                continue
            if not _passes_max(item.pb, max_pb):
                continue
            quote_as_of = getattr(quote, "as_of", None)
            if isinstance(quote_as_of, datetime):
                as_of = quote_as_of
            items.append(item)
        return StockScreenerResponse(
            items=items,
            source=STOCK_SCREENER_FALLBACK_SOURCE,
            as_of=as_of or datetime.now(UTC),
            status="live" if items else "unavailable",
            detail=f"Primary screener source unavailable: {failure_detail}",
        )


def _stock_item_from_row(row: Mapping[str, object]) -> StockScreenerItem | None:
    code = _clean_text(_row_value(row, ("代码", "股票代码", "证券代码", "code", "symbol")))
    name = _clean_text(_row_value(row, ("名称", "股票简称", "证券简称", "name")))
    symbol = _normalize_stock_code(code)
    if not symbol or not name:
        return None
    return StockScreenerItem(
        symbol=symbol,
        code=_plain_code(symbol),
        name=name,
        exchange=_exchange_for_symbol(symbol),
        price=_parse_float(_row_value(row, ("最新价", "最新", "price", "latest_price", "last_price"))),
        change_pct=_parse_float(_row_value(row, ("涨跌幅", "change_pct", "pct_chg", "changePercent"))),
        turnover=_parse_money(_row_value(row, ("成交额", "turnover", "amount"))),
        volume=_parse_float(_row_value(row, ("成交量", "volume"))),
        market_cap=_parse_money(_row_value(row, ("总市值", "market_cap", "total_market_cap", "total_mv"))),
        pe=_parse_float(_row_value(row, ("市盈率-动态", "市盈率", "pe", "pe_ttm", "dynamic_pe"))),
        pb=_parse_float(_row_value(row, ("市净率", "pb", "price_to_book"))),
        turnover_rate=_parse_float(_row_value(row, ("换手率", "turnover_rate"))),
        source=STOCK_SCREENER_SOURCE,
    )


def _matches_query(item: StockScreenerItem, query: str, upper_query: str) -> bool:
    return query in item.name or upper_query in item.symbol.upper() or upper_query in item.code.upper()


def _passes_min(value: float | None, threshold: float | None) -> bool:
    return threshold is None or (value is not None and value >= threshold)


def _passes_max(value: float | None, threshold: float | None) -> bool:
    return threshold is None or (value is not None and value <= threshold)


def _normalize_stock_code(code: str) -> str:
    raw = code.strip().upper()
    if not raw:
        return ""
    for prefix in ("SH", "SZ", "BJ"):
        if raw.startswith(prefix) and raw[len(prefix):].isdigit():
            raw = raw[len(prefix):]
            break
    if raw.endswith((".SH", ".SZ", ".BJ")):
        return normalize_symbol(raw, "CN")
    if raw.isdigit():
        return normalize_symbol(raw.zfill(6), "CN")
    return ""


def _plain_code(symbol: str) -> str:
    return symbol.removesuffix(".SH").removesuffix(".SZ").removesuffix(".BJ")


def _exchange_for_symbol(symbol: str) -> str | None:
    if symbol.endswith(".SH"):
        return "SH"
    if symbol.endswith(".SZ"):
        return "SZ"
    if symbol.endswith(".BJ"):
        return "BJ"
    return None


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
