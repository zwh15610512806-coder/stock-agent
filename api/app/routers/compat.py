import asyncio
from datetime import UTC, date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from app.schemas.market import CandleSnapshot, MarketCode, QuoteSnapshot, SymbolSearchResult
from app.services.etfs import ETFService
from app.services.macro import MacroDataService
from app.services.market import INDEX_SYMBOLS, MarketDataService
from app.services.stocks import StockScreenerService
from app.services.symbols import STATIC_SYMBOLS, _a_share_pool, normalize_symbol, resolve_symbol_query, search_static_symbols

router = APIRouter(prefix="/api", tags=["compat"])

INDEX_GROUPS: dict[str, list[str]] = {
    "indices-cn": [symbol for symbol, _ in INDEX_SYMBOLS["CN"]],
    "indices-hk": [symbol for symbol, _ in INDEX_SYMBOLS["HK"]],
    "indices-us": [symbol for symbol, _ in INDEX_SYMBOLS["US"]],
    "indices-all": [symbol for market in ("CN", "HK", "US") for symbol, _ in INDEX_SYMBOLS[market]],  # type: ignore[index]
}


@router.get("/quotes")
async def quotes_compat(
    request: Request,
    type: str = Query(default="realtime"),
    group: str = Query(default="indices-all"),
    symbols: str = Query(default=""),
    limit: int = Query(default=120, ge=1, le=500),
) -> dict[str, Any]:
    service = _market_service(request)
    requested = _requested_symbols(symbols, group)
    if type == "intraday":
        return _unavailable_series_response(
            type,
            group,
            requested,
            "intraday free source is not connected; use type=daily for historical daily series",
        )
    if type == "daily":
        return await _quote_series_response(service, requested, type, group, limit)
    return await _quote_response(service, requested, type, group)


@router.get("/pricing/historical")
async def historical_pricing(
    request: Request,
    market: str = Query(default="CN"),
    date: str = Query(..., min_length=10, max_length=10),
    symbols: str = Query(default=""),
) -> dict[str, Any]:
    service = _market_service(request)
    requested_date = _parse_date(date)
    requested_symbols = _requested_symbols(symbols, f"indices-{market.lower()}")
    items: list[dict[str, Any]] = []
    errors: list[str] = []
    for symbol in requested_symbols:
        try:
            candles = await _real_candles(service, symbol, "daily", 260)
            selected = _select_candle_for_date(candles, requested_date)
            if selected is None:
                errors.append(f"{symbol}: no candle on or before {requested_date.isoformat()}")
                continue
            items.append(selected.model_dump(mode="json"))
        except Exception as exc:
            errors.append(f"{symbol}: {_error_detail(exc)}")
    return {
        "market": market.upper(),
        "date": requested_date.isoformat(),
        "status": _status_from_counts(len(items), len(requested_symbols)),
        "source": _source_summary(items),
        "items": items,
        "detail": "; ".join(errors),
        "as_of": datetime.now(UTC),
    }


@router.get("/time-machine/resolve")
async def time_machine_resolve(date: str = Query(..., min_length=10, max_length=10)) -> dict[str, Any]:
    requested = _parse_date(date)
    resolved = requested
    if requested.weekday() == 5:
        resolved = requested - timedelta(days=1)
    elif requested.weekday() == 6:
        resolved = requested - timedelta(days=2)
    return {
        "requested_date": requested.isoformat(),
        "resolved_date": resolved.isoformat(),
        "status": "live",
        "source": "calendar-weekend-adjustment",
        "detail": "" if requested == resolved else "weekend adjusted to prior Friday",
    }


@router.get("/market/status")
async def market_status() -> dict[str, Any]:
    return {
        "status": "ok",
        "as_of": datetime.now(UTC),
        "free_sources": [
            "tencent-free-delayed",
            "sina-free-delayed",
            "Yahoo Finance/free delayed fallback",
            "akshare-eastmoney-free",
            "akshare-macro-free",
        ],
        "detail": "Backend is reachable; third-party sources are checked only by data endpoints.",
    }


@router.get("/market/dashboard/realtime")
async def market_dashboard_realtime(request: Request) -> Any:
    return await _market_service(request).dashboard(["CN", "HK", "US"], "daily")


@router.get("/market/dashboard/intraday")
async def market_dashboard_intraday(
    request: Request,
    group: str = Query(default="indices-cn"),
) -> dict[str, Any]:
    requested = _requested_symbols("", group)
    return _unavailable_series_response(
        "intraday",
        group,
        requested,
        "intraday free source is not connected; use /api/quotes?type=daily for historical daily series",
    )


@router.get("/market/macro-timeseries")
async def macro_timeseries(request: Request) -> dict[str, Any]:
    dashboard = await _macro_service(request).dashboard()
    groups = {
        "rates": dashboard.rates,
        "indicators": dashboard.indicators,
        "bond_yields": dashboard.bond_yields,
        "fx_rates": dashboard.fx_rates,
    }
    return {
        "status": dashboard.cache_status,
        "as_of": dashboard.as_of,
        "source_status": [item.model_dump(mode="json") for item in dashboard.source_status],
        "series": [
            {
                "id": key,
                "label": key.replace("_", " ").title(),
                "points": [point.model_dump(mode="json") for point in points],
            }
            for key, points in groups.items()
        ],
        "disclaimer": dashboard.disclaimer,
    }


@router.get("/market/macro-xray")
async def macro_xray(request: Request) -> dict[str, Any]:
    dashboard = await _macro_service(request).dashboard()
    groups = {
        "rates": dashboard.rates,
        "indicators": dashboard.indicators,
        "bond_yields": dashboard.bond_yields,
        "fx_rates": dashboard.fx_rates,
    }
    live_count = sum(1 for points in groups.values() for point in points if point.status == "live" and point.value is not None)
    total_count = sum(len(points) for points in groups.values())
    return {
        "status": dashboard.cache_status,
        "as_of": dashboard.as_of,
        "live_count": live_count,
        "total_count": total_count,
        "groups": [
            {"id": key, "available": sum(1 for point in points if point.value is not None), "total": len(points)}
            for key, points in groups.items()
        ],
        "source_status": [item.model_dump(mode="json") for item in dashboard.source_status],
    }


@router.get("/market/macro-xray/targets")
async def macro_xray_targets() -> dict[str, Any]:
    return {
        "status": "live",
        "items": [
            {"id": "rates", "label": "Rates", "source": "akshare.macro_china_lpr"},
            {"id": "indicators", "label": "Inflation/GDP/PMI/Credit", "source": "akshare macro"},
            {"id": "bond_yields", "label": "China/US 10Y Yields", "source": "akshare.bond_zh_us_rate"},
            {"id": "fx_rates", "label": "FX Rates", "source": "akshare.currency_boc_sina"},
        ],
    }


@router.get("/stocks/v2/catalog")
async def stock_catalog(
    market: str = Query(default="CN"),
    limit: int = Query(default=100, ge=1, le=1000),
) -> dict[str, Any]:
    items = _catalog_items({market.upper()} if market else {"CN"}, limit)
    return {
        "status": "live" if items else "unavailable",
        "source": "static-core+akshare-stock-info-a-code-name",
        "items": [item.model_dump(mode="json") for item in items],
        "as_of": datetime.now(UTC),
    }


@router.get("/stocks/v2/catalog-lookup")
async def stock_catalog_lookup(
    codes: str = Query(..., min_length=1),
) -> dict[str, Any]:
    requested = [normalize_symbol(code.strip(), None) for code in codes.split(",") if code.strip()]
    catalog = {item.symbol: item for item in _catalog_items({"CN", "HK", "US"}, 2000)}
    items = [catalog[symbol].model_dump(mode="json") for symbol in requested if symbol in catalog]
    missing = [symbol for symbol in requested if symbol not in catalog]
    return {
        "status": _status_from_counts(len(items), len(requested)),
        "source": "static-core+akshare-stock-info-a-code-name",
        "items": items,
        "missing": missing,
    }


@router.get("/stocks/v2/search")
async def stock_search(
    q: str = Query(default=""),
    markets: str = Query(default="CN,HK,US"),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    requested_markets = _parse_markets(markets)
    if q.strip():
        items = _static_symbol_matches(q, requested_markets, limit)
        if not items:
            items = search_static_symbols(q, requested_markets)[:limit]
    else:
        items = _catalog_items(requested_markets, limit)
    return {
        "status": "live" if items else "unavailable",
        "source": "static-core+akshare-stock-info-a-code-name",
        "items": [item.model_dump(mode="json") for item in items],
        "as_of": datetime.now(UTC),
    }


@router.get("/stocks/v2/screener/bootstrap")
async def screener_bootstrap() -> dict[str, Any]:
    return {
        "status": "live",
        "source": "local-screener-config",
        "presets": [
            {"id": "liquidity", "label": "High liquidity", "params": {"min_turnover": 1000000000}},
            {"id": "reasonable_value", "label": "Reasonable PE/PB", "params": {"max_pe": 30, "max_pb": 5}},
        ],
        "ranges": {
            "change_pct": {"min": -20, "max": 20},
            "turnover": {"min": 0},
            "market_cap": {"min": 0},
            "pe": {"min": 0},
            "pb": {"min": 0},
        },
    }


@router.get("/stocks/v2/screener/facets")
async def screener_facets() -> dict[str, Any]:
    return {
        "status": "live",
        "source": "local-screener-config",
        "items": [
            {"id": "exchange", "values": ["SH", "SZ", "BJ"]},
            {"id": "metrics", "values": ["change_pct", "turnover", "market_cap", "pe", "pb"]},
        ],
    }


@router.get("/stocks/v2/screener/query")
async def screener_query(
    request: Request,
    query: str = Query(default=""),
    min_change_pct: float | None = Query(default=None),
    max_change_pct: float | None = Query(default=None),
    min_turnover: float | None = Query(default=None, ge=0),
    min_market_cap: float | None = Query(default=None, ge=0),
    max_pe: float | None = Query(default=None),
    max_pb: float | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> Any:
    return await _stock_service(request).screen(
        query=query,
        min_change_pct=min_change_pct,
        max_change_pct=max_change_pct,
        min_turnover=min_turnover,
        min_market_cap=min_market_cap,
        max_pe=max_pe,
        max_pb=max_pb,
        limit=limit,
    )


@router.get("/stocks/v2/compare/query")
async def compare_query(
    request: Request,
    symbols: str = Query(..., min_length=1),
) -> dict[str, Any]:
    return await _quote_response(_market_service(request), _requested_symbols(symbols, ""), "compare", "stocks")


@router.get("/quotes/v2/overlay")
async def quote_overlay(
    request: Request,
    symbols: str = Query(..., min_length=1),
) -> dict[str, Any]:
    return await _quote_response(_market_service(request), _requested_symbols(symbols, ""), "overlay", "stocks")


@router.get("/quotes/v2/stock-latest/snapshot")
async def stock_latest_snapshot(
    request: Request,
    symbols: str = Query(..., min_length=1),
) -> dict[str, Any]:
    return await _quote_response(_market_service(request), _requested_symbols(symbols, ""), "snapshot", "stocks")


@router.get("/quotes/v2/stock-latest/stats")
async def stock_latest_stats(
    request: Request,
    symbols: str = Query(default="000001.SH,399001.SZ,399006.SZ"),
) -> dict[str, Any]:
    response = await _quote_response(_market_service(request), _requested_symbols(symbols, ""), "stats", "stocks")
    quotes = [QuoteSnapshot.model_validate(item) for item in response["items"]]
    avg_change = sum(item.change_pct for item in quotes) / len(quotes) if quotes else 0
    return {
        **response,
        "stats": {
            "count": len(quotes),
            "advances": sum(1 for item in quotes if item.change_pct > 0),
            "declines": sum(1 for item in quotes if item.change_pct < 0),
            "avg_change_pct": round(avg_change, 4),
        },
    }


@router.get("/quotes/v2/stock-latest/ranking")
async def stock_latest_ranking(
    request: Request,
    symbols: str = Query(default="000001.SH,399001.SZ,399006.SZ"),
    by: str = Query(default="change_pct"),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    response = await _quote_response(_market_service(request), _requested_symbols(symbols, ""), "ranking", "stocks")
    key = "turnover" if by == "turnover" else "change_pct"
    items = sorted(response["items"], key=lambda item: item.get(key) or 0, reverse=True)[:limit]
    return {**response, "items": items, "rank_by": key}


@router.get("/etfs/v1/catalog")
async def etf_catalog(
    request: Request,
    q: str = Query(default=""),
    limit: int = Query(default=30, ge=1, le=200),
) -> Any:
    return await _etf_service(request).search(q=q, limit=limit)


async def _quote_response(service: Any, symbols: list[str], type_name: str, group: str) -> dict[str, Any]:
    results = await asyncio.gather(*(_real_quote(service, symbol) for symbol in symbols), return_exceptions=True)
    quotes: list[QuoteSnapshot] = []
    errors: list[str] = []
    for symbol, result in zip(symbols, results, strict=True):
        if isinstance(result, Exception):
            errors.append(f"{symbol}: {_error_detail(result)}")
        elif _is_sample_quote(result):
            errors.append(f"{symbol}: sample fallback rejected")
        else:
            quotes.append(result)
    items = [quote.model_dump(mode="json") for quote in quotes]
    return {
        "type": type_name,
        "group": group,
        "status": _status_from_counts(len(items), len(symbols)),
        "source": _source_summary(items),
        "as_of": datetime.now(UTC),
        "items": items,
        "detail": "; ".join(errors),
    }


async def _quote_series_response(service: Any, symbols: list[str], type_name: str, group: str, limit: int = 120) -> dict[str, Any]:
    series: list[dict[str, Any]] = []
    errors: list[str] = []
    for symbol in symbols:
        try:
            candles = await _real_candles(service, symbol, "daily", limit)
            series.append(
                {
                    "symbol": symbol,
                    "items": [candle.model_dump(mode="json") for candle in candles],
                    "source": candles[-1].source if candles else "market-candles",
                }
            )
        except Exception as exc:
            errors.append(f"{symbol}: {_error_detail(exc)}")
    return {
        "type": type_name,
        "group": group,
        "status": _status_from_counts(len(series), len(symbols)),
        "source": _source_summary(series),
        "as_of": datetime.now(UTC),
        "series": series,
        "detail": "; ".join(errors),
    }


def _unavailable_series_response(type_name: str, group: str, symbols: list[str], detail: str) -> dict[str, Any]:
    return {
        "type": type_name,
        "group": group,
        "status": "unavailable",
        "source": "unavailable",
        "as_of": datetime.now(UTC),
        "series": [{"symbol": symbol, "items": [], "source": "unavailable"} for symbol in symbols],
        "detail": detail,
    }


async def _real_quote(service: Any, symbol: str) -> QuoteSnapshot:
    normalized = normalize_symbol(symbol, None)
    if hasattr(service, "_fetch_quote_without_sample"):
        quote = await service._fetch_quote_without_sample(normalized)
    else:
        quotes = await service.quotes([normalized])
        if not quotes:
            raise RuntimeError("quote service returned no rows")
        quote = quotes[0]
    if _is_sample_quote(quote):
        raise RuntimeError("sample fallback quote rejected")
    return quote


async def _real_candles(service: Any, symbol: str, period: str, limit: int) -> list[CandleSnapshot]:
    normalized = normalize_symbol(symbol, None)
    if hasattr(service, "_fetch_primary_candles"):
        candles = await service._fetch_primary_candles(normalized, period, limit)
    else:
        candles = await service.candles(normalized, period, limit)
    real = [candle for candle in candles if str(candle.source).strip().lower() != "sample fallback"]
    if not real:
        raise RuntimeError("no real candles returned")
    return real


def _catalog_items(markets: set[str], limit: int) -> list[SymbolSearchResult]:
    allowed = {market for market in markets if market in {"CN", "HK", "US"}}
    items: list[SymbolSearchResult] = []
    seen: set[str] = set()
    for item in STATIC_SYMBOLS:
        if allowed and item.market not in allowed:
            continue
        items.append(item)
        seen.add(item.symbol)
        if len(items) >= limit:
            return items
    if not allowed or "CN" in allowed:
        for item in _a_share_pool():
            if item.symbol in seen:
                continue
            items.append(item)
            seen.add(item.symbol)
            if len(items) >= limit:
                break
    return items


def _static_symbol_matches(query: str, markets: set[MarketCode], limit: int) -> list[SymbolSearchResult]:
    raw_term = query.strip()
    term = raw_term.upper()
    if not raw_term:
        return []
    items: list[SymbolSearchResult] = []
    for item in STATIC_SYMBOLS:
        if markets and item.market not in markets:
            continue
        code = item.symbol.removesuffix(".SH").removesuffix(".SZ").removesuffix(".BJ").removesuffix(".HK")
        if term in item.symbol.upper() or term in code.upper() or raw_term in item.name:
            items.append(item)
            if len(items) >= limit:
                break
    return items


def _requested_symbols(symbols: str, group: str) -> list[str]:
    if symbols.strip():
        return [resolve_symbol_query(item, None) for item in symbols.split(",") if item.strip()]
    return INDEX_GROUPS.get(group, INDEX_GROUPS["indices-all"])


def _parse_markets(value: str) -> set[MarketCode]:
    allowed: set[MarketCode] = {"CN", "HK", "US"}
    parsed = {item.strip().upper() for item in value.split(",")}
    return {item for item in parsed if item in allowed} or allowed  # type: ignore[return-value]


def _select_candle_for_date(candles: list[CandleSnapshot], requested_date: date) -> CandleSnapshot | None:
    candidates: list[CandleSnapshot] = []
    for candle in candles:
        try:
            candle_date = date.fromisoformat(candle.date[:10])
        except ValueError:
            continue
        if candle_date <= requested_date:
            candidates.append(candle)
    return max(candidates, key=lambda item: item.date) if candidates else None


def _status_from_counts(success_count: int, total_count: int) -> str:
    if total_count <= 0 or success_count <= 0:
        return "unavailable"
    return "live" if success_count == total_count else "partial"


def _source_summary(items: list[dict[str, Any]]) -> str:
    sources = sorted({str(item.get("source")) for item in items if item.get("source")})
    return " / ".join(sources) if sources else "unavailable"


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="date must be YYYY-MM-DD") from exc


def _is_sample_quote(quote: QuoteSnapshot) -> bool:
    return str(quote.source).strip().lower() == "sample fallback"


def _error_detail(exc: BaseException) -> str:
    return str(exc) or exc.__class__.__name__


def _market_service(request: Request) -> MarketDataService:
    service = getattr(request.app.state, "market_service", None)
    if service is None:
        service = MarketDataService()
        request.app.state.market_service = service
    return service


def _stock_service(request: Request) -> Any:
    service = getattr(request.app.state, "stock_screener_service", None)
    if service is None:
        service = StockScreenerService()
        request.app.state.stock_screener_service = service
    return service


def _etf_service(request: Request) -> ETFService:
    service = getattr(request.app.state, "etf_service", None)
    if service is None:
        service = ETFService()
        request.app.state.etf_service = service
    return service


def _macro_service(request: Request) -> MacroDataService:
    service = getattr(request.app.state, "macro_service", None)
    if service is None:
        service = MacroDataService()
        request.app.state.macro_service = service
    return service
