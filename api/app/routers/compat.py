import asyncio
import html
import json
import re
from datetime import UTC, date, datetime, timedelta, timezone
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query, Request, Response

from app.config import get_settings
from app.routers.cache_headers import set_shared_cache_header
from app.routers.market_payloads import (
    danginvest_intraday_dashboard,
    danginvest_market_snapshot,
    danginvest_market_status,
    danginvest_news_response,
    danginvest_realtime_dashboard,
    danginvest_top_turnover_response,
    quote_to_turnover_item,
)
from app.schemas.market import CandleSnapshot, MarketCode, MarketNewsItem, QuoteSnapshot, SymbolSearchResult
from app.services.etfs import ETFService
from app.services.macro import MacroDataService
from app.services.macro_provider import macro_provider_for_settings
from app.services.macro_xray import MacroXrayService
from app.services.market import INDEX_SYMBOLS, MarketDataService, _records, _row_value, parse_cn_money, parse_pct
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
    return danginvest_market_status()


@router.get("/market/dashboard/realtime")
async def market_dashboard_realtime(request: Request, response: Response) -> Any:
    set_shared_cache_header(response, s_maxage=30, stale_while_revalidate=300)
    try:
        dashboard = await _market_service(request).dashboard(["CN", "HK", "US"], "daily")
        return danginvest_realtime_dashboard(dashboard)
    except Exception as exc:
        fallback = await _danginvest_public_json(request, "/api/market/dashboard/realtime", {}, "danginvest:dashboard:realtime")
        if fallback is not None:
            return _mark_danginvest_fallback(fallback, "market_dashboard_realtime")
        raise HTTPException(status_code=503, detail=f"market realtime dashboard unavailable: {exc}") from exc


@router.get("/market/dashboard/intraday")
async def market_dashboard_intraday(
    request: Request,
    groups: str = Query(default="indices-cn"),
    group: str | None = Query(default=None),
) -> dict[str, Any]:
    requested_groups = _parse_group_list(group or groups)
    dashboard = await _market_service(request).dashboard(["CN", "HK", "US"], "daily")
    payload = danginvest_intraday_dashboard(dashboard, requested_groups)
    if payload["status"] == "live":
        return payload
    fallback = await _danginvest_public_json(
        request,
        "/api/market/dashboard/intraday",
        {"groups": ",".join(requested_groups)},
        f"danginvest:dashboard:intraday:{','.join(requested_groups)}",
    )
    if fallback is not None:
        return _mark_danginvest_fallback(fallback, "market_dashboard_intraday")
    return payload


@router.get("/market/news")
async def market_news(
    request: Request,
    response: Response,
    limit: int = Query(default=120, ge=1, le=120),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    set_shared_cache_header(response, s_maxage=30, stale_while_revalidate=300)
    dashboard = await _market_service(request).dashboard(["CN", "HK", "US"], "daily")
    local = danginvest_news_response(dashboard.market_news, limit, offset, dashboard.as_of)
    if local["count"] >= offset + limit or local["data"]:
        return local
    sina_fallback = await _sina_public_news_response(request, limit, offset)
    if sina_fallback is not None:
        return sina_fallback
    fallback = await _danginvest_public_json(
        request,
        "/api/market/news",
        {"limit": str(limit), "offset": str(offset)},
        f"danginvest:market:news:{limit}:{offset}",
        ttl_seconds=60,
    )
    if fallback is not None:
        return _mark_danginvest_fallback(fallback, "market_news")
    return local


@router.get("/market/stocks/top-turnover")
async def market_top_turnover(
    request: Request,
    response: Response,
    market: str = Query(default="cn"),
    limit: int = Query(default=10, ge=1, le=100),
    date: str | None = Query(default=None, min_length=10, max_length=10),
) -> dict[str, Any]:
    set_shared_cache_header(response, s_maxage=30, stale_while_revalidate=300)
    items = await _top_turnover_items(_market_service(request), market, limit)
    if not items:
        fallback = await _danginvest_public_json(
            request,
            "/api/market/stocks/top-turnover",
            {"market": market.lower(), "limit": str(limit), **({"date": date} if date else {})},
            f"danginvest:top-turnover:{market.lower()}:{date or 'latest'}:{limit}",
            ttl_seconds=60,
        )
        if fallback is not None:
            return _mark_danginvest_fallback(fallback, "top_turnover")
    return danginvest_top_turnover_response(items, market.lower(), limit, date)


@router.get("/market")
async def market_date_snapshot(
    request: Request,
    response: Response,
    date: str | None = Query(default=None, min_length=10, max_length=10),
) -> dict[str, Any]:
    set_shared_cache_header(response, s_maxage=30, stale_while_revalidate=300)
    service = _market_service(request)
    try:
        dashboard = await service.dashboard(["CN", "HK", "US"], "daily")
    except Exception as exc:
        fallback = await _danginvest_public_json(
            request,
            "/api/market",
            {"date": date} if date else {},
            f"danginvest:market:snapshot:{date or 'latest'}",
            ttl_seconds=60,
        )
        if fallback is not None:
            return _mark_danginvest_fallback(fallback, "market_snapshot")
        raise HTTPException(status_code=503, detail=f"market snapshot unavailable: {exc}") from exc
    top_turnover = danginvest_top_turnover_response(
        await _top_turnover_items(service, "cn", 10),
        "cn",
        10,
        date,
        dashboard.as_of,
    )
    return danginvest_market_snapshot(dashboard, top_turnover, date)


@router.get("/market/macro-timeseries")
async def macro_timeseries(
    request: Request,
    response: Response,
    series_ids: str = Query(default=""),
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    max_points: int = Query(default=600, ge=1, le=5000),
) -> Any:
    set_shared_cache_header(response, s_maxage=3600, stale_while_revalidate=86400)
    if series_ids.strip():
        parsed_ids = [item.strip() for item in series_ids.split(",") if item.strip()]
        return await _macro_provider(request).timeseries(
            series_ids=parsed_ids,
            start=start,
            end=end,
            max_points=max_points,
        )
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
async def macro_xray(
    request: Request,
    response: Response,
    universe_type: str = Query(default="index"),
    universe_code: str = Query(default="000300.SH"),
    scope: str = Query(default="non_financial"),
    period: str = Query(default="latest"),
    quarters: int = Query(default=40, ge=1, le=80),
    lookback: int = Query(default=6, ge=1, le=24),
) -> Any:
    set_shared_cache_header(response, s_maxage=3600, stale_while_revalidate=86400)
    return await _macro_provider(request).xray(
        universe_type=universe_type,
        universe_code=universe_code,
        scope=scope,
        period=period,
        quarters=quarters,
        lookback=lookback,
    )


@router.get("/market/macro-xray/targets")
async def macro_xray_targets(
    request: Request,
    response: Response,
    universe_type: str = Query(default="index"),
    lookback: int = Query(default=6, ge=1, le=24),
    target_source: str = Query(default="stock_basic_full_v1"),
) -> Any:
    set_shared_cache_header(response, s_maxage=3600, stale_while_revalidate=86400)
    return await _macro_provider(request).targets(
        universe_type=universe_type,
        lookback=lookback,
        target_source=target_source,
    )


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


def _parse_group_list(value: str) -> list[str]:
    groups = [item.strip() for item in value.split(",") if item.strip()]
    return groups or ["indices-cn"]


async def _sina_public_news_response(request: Request, limit: int, offset: int) -> dict[str, Any] | None:
    service = _market_service(request)
    cache = getattr(service, "snapshot_cache", None)
    cache_key = f"sina:market:news:{limit}:{offset}"
    cached = cache.get(cache_key) if cache is not None else None
    if cached is not None and not cached.is_stale and isinstance(cached.payload, dict):
        return cached.payload

    fetcher = getattr(request.app.state, "market_news_fallback_fetcher", None)
    try:
        if fetcher is not None:
            payload = await _maybe_await(fetcher(limit, offset))
        else:
            payload = await _fetch_sina_market_news_json(limit, offset)
        items = _sina_news_items_from_payload(payload)
    except Exception:
        if cached is not None and isinstance(cached.payload, dict):
            stale_payload = dict(cached.payload)
            stale_payload["stale"] = True
            return stale_payload
        return None

    if not items:
        return None
    response = danginvest_news_response(items, limit, 0, datetime.now(UTC))
    response["offset"] = offset
    response["count"] = offset + len(items) + (limit if len(items) >= limit else 0)
    response["has_more"] = len(items) >= limit
    response["source_status"] = [
        {
            "name": "market_news",
            "status": "live",
            "source": "sina-7x24",
            "detail": "served from Sina 7x24 public JSON feed",
            "as_of": datetime.now(UTC).isoformat(),
        }
    ]
    if cache is not None:
        cache.save(cache_key, response, "sina-7x24", 60)
    return response


async def _fetch_sina_market_news_json(limit: int, offset: int) -> dict[str, Any]:
    page_size = max(1, min(limit, 120))
    page = max(1, offset // page_size + 1)
    async with httpx.AsyncClient(timeout=8.0, trust_env=False, follow_redirects=True) as client:
        response = await client.get(
            "https://zhibo.sina.com.cn/api/zhibo/feed",
            params={"page": page, "page_size": page_size, "zhibo_id": 152},
            headers={"user-agent": "Mozilla/5.0"},
        )
        response.raise_for_status()
        payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("sina 7x24 returned invalid payload")
    return payload


def _sina_news_items_from_payload(payload: dict[str, Any]) -> list[MarketNewsItem]:
    feed = (((payload.get("result") or {}).get("data") or {}).get("feed") or {}).get("list") or []
    if not isinstance(feed, list):
        return []
    items: list[MarketNewsItem] = []
    for row in feed:
        if not isinstance(row, dict):
            continue
        text = _clean_sina_rich_text(row.get("rich_text"))
        if not text:
            continue
        title, content = _split_sina_news_text(text)
        items.append(
            MarketNewsItem(
                title=title,
                content=content,
                published_at=_parse_sina_news_time(row.get("create_time")),
                source="sina-7x24",
                url=_sina_news_url(row),
            )
        )
    return items


def _clean_sina_rich_text(value: object) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _split_sina_news_text(text: str) -> tuple[str, str]:
    match = re.match(r"^【(.+?)】\s*(.*)$", text)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    title = text[:72].strip()
    return title, text


def _parse_sina_news_time(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text).replace(tzinfo=timezone(timedelta(hours=8)))
    except ValueError:
        return None


def _sina_news_url(row: dict[str, Any]) -> str:
    raw_ext = row.get("ext")
    if isinstance(raw_ext, str) and raw_ext.strip():
        try:
            parsed = json.loads(raw_ext)
            docurl = parsed.get("docurl")
            if isinstance(docurl, str):
                return docurl.replace("\\/", "/")
        except json.JSONDecodeError:
            pass
    return ""


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


async def _danginvest_public_json(
    request: Request,
    path: str,
    params: dict[str, str],
    cache_key: str,
    ttl_seconds: int = 30,
) -> dict[str, Any] | None:
    service = _market_service(request)
    cache = getattr(service, "snapshot_cache", None)
    cached = cache.get(cache_key) if cache is not None else None
    if cached is not None and not cached.is_stale and isinstance(cached.payload, dict):
        return _mark_danginvest_fallback(dict(cached.payload), "danginvest_public_cache", stale=False)

    settings = getattr(request.app.state, "settings", None) or get_settings()
    base_url = str(getattr(settings, "danginvest_base_url", "https://dang-invest.com")).rstrip("/")
    timeout_seconds = float(getattr(settings, "danginvest_timeout_seconds", 8.0))
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds, trust_env=False) as client:
            response = await client.get(f"{base_url}{path}", params=params)
            response.raise_for_status()
            payload = response.json()
    except Exception:
        if cached is not None and isinstance(cached.payload, dict):
            return _mark_danginvest_fallback(dict(cached.payload), "danginvest_public_cache", stale=True)
        return None

    if not isinstance(payload, dict):
        return None
    if cache is not None:
        cache.save(cache_key, payload, "danginvest-public-fallback", ttl_seconds)
    return _mark_danginvest_fallback(payload, "danginvest_public_fallback", stale=False)


def _mark_danginvest_fallback(payload: dict[str, Any], name: str, stale: bool | None = None) -> dict[str, Any]:
    marked = dict(payload)
    if stale is not None:
        marked["stale"] = stale
    source_status = list(marked.get("source_status") or [])
    source_status.append(
        {
            "name": name,
            "status": "stale" if stale else "live",
            "source": "danginvest-public-fallback",
            "detail": "served from SQLite cache" if stale else "served from DangInvest public API fallback",
            "as_of": datetime.now(UTC).isoformat(),
        }
    )
    marked["source_status"] = source_status
    meta = marked.get("meta")
    if isinstance(meta, dict):
        meta = dict(meta)
        meta["fallbackSource"] = "danginvest-public-fallback"
        marked["meta"] = meta
    return marked


async def _top_turnover_items(service: Any, market: str, limit: int) -> list[dict[str, Any]]:
    market_key = market.lower()
    spot_items = await asyncio.to_thread(_spot_turnover_items_sync, service, market_key, limit)
    if spot_items:
        return spot_items
    return await _quote_turnover_items(service, market_key, limit)


def _spot_turnover_items_sync(service: Any, market: str, limit: int) -> list[dict[str, Any]]:
    if market not in {"cn", "a", "ashare"} or not hasattr(service, "_akshare"):
        return []
    try:
        rows = _records(service._akshare().stock_zh_a_spot_em())
    except Exception:
        return []
    items: list[dict[str, Any]] = []
    for row in rows:
        code = str(_row_value(row, ("代码", "股票代码", "code", "symbol")) or "").strip()
        if not code:
            continue
        turnover = parse_cn_money(_row_value(row, ("成交额", "turnover", "amount")))
        if turnover <= 0:
            continue
        items.append(
            {
                "code": code,
                "symbol": _a_share_symbol_from_code(code),
                "name": str(_row_value(row, ("名称", "股票简称", "name")) or code),
                "price": parse_cn_money(_row_value(row, ("最新价", "收盘", "现价", "price"))),
                "changePct": parse_pct(_row_value(row, ("涨跌幅", "change_pct", "涨幅"))),
                "change_pct": parse_pct(_row_value(row, ("涨跌幅", "change_pct", "涨幅"))),
                "turnoverYuan": turnover,
                "turnover": turnover,
                "source": "akshare-eastmoney-a-spot",
            }
        )
    return sorted(items, key=lambda item: item["turnoverYuan"], reverse=True)[:limit]


async def _quote_turnover_items(service: Any, market: str, limit: int) -> list[dict[str, Any]]:
    symbols = _turnover_candidate_symbols(market, limit)
    results = await asyncio.gather(*(_real_quote(service, symbol) for symbol in symbols), return_exceptions=True)
    quotes = [result for result in results if isinstance(result, QuoteSnapshot)]
    return [quote_to_turnover_item(quote) for quote in sorted(quotes, key=lambda item: item.turnover, reverse=True)[:limit]]


def _turnover_candidate_symbols(market: str, limit: int) -> list[str]:
    if market in {"hk", "h"}:
        return [symbol for symbol, _ in INDEX_SYMBOLS["HK"]][:limit]
    if market in {"us", "usa"}:
        return [symbol for symbol, _ in INDEX_SYMBOLS["US"]][:limit]
    core = ["600519.SH", "300750.SZ", "601318.SH", "000858.SZ", "002594.SZ", "600036.SH"]
    return core[: max(limit, 1)]


def _a_share_symbol_from_code(code: str) -> str:
    value = code.strip()
    if value.upper().endswith((".SH", ".SZ", ".BJ")):
        return value.upper()
    if value.startswith(("6", "9")):
        return f"{value}.SH"
    if value.startswith(("8", "4")):
        return f"{value}.BJ"
    return f"{value}.SZ"


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


def _macro_xray_service(request: Request) -> Any:
    service = getattr(request.app.state, "macro_xray_service", None)
    if service is None:
        service = MacroXrayService(macro_service=_macro_service(request))
        request.app.state.macro_xray_service = service
    return service


def _macro_provider(request: Request) -> Any:
    provider = getattr(request.app.state, "macro_provider", None)
    if provider is None:
        provider = macro_provider_for_settings(
            macro_service=_macro_service(request),
            xray_service=_macro_xray_service(request),
        )
        request.app.state.macro_provider = provider
    return provider
