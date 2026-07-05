from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.schemas.market import DashboardHeatItem, MarketDashboardResponse, MarketNewsItem, QuoteSnapshot
from app.services.market import INDEX_SYMBOLS

CN_TZ = ZoneInfo("Asia/Shanghai")
NY_TZ = ZoneInfo("America/New_York")

REALTIME_GROUP_ORDER = [
    "indices-cn",
    "indices-hk",
    "indices-us",
    "indices-kr",
    "indices-jp",
    "etf-broad",
    "futures-domestic",
    "futures-overseas",
]

REALTIME_GROUP_TITLES = {
    "indices-cn": "A股",
    "indices-hk": "港股",
    "indices-us": "美股",
    "indices-kr": "韩国市场",
    "indices-jp": "日经指数",
    "etf-broad": "ETF",
    "futures-domestic": "国内期货",
    "futures-overseas": "海外期货",
}


def danginvest_market_status(now: datetime | None = None) -> dict[str, Any]:
    current_utc = now.astimezone(UTC) if now else datetime.now(UTC)
    cn_now = current_utc.astimezone(CN_TZ)
    ny_now = current_utc.astimezone(NY_TZ)
    return {
        "ts": current_utc.isoformat(),
        "timestamp": int(current_utc.timestamp() * 1000),
        "weekday": cn_now.weekday() + 1,
        "weekday_name": _weekday_name(cn_now.weekday()),
        "data": [
            _status_item("cn", "A股", cn_now, [(time(9, 30), time(11, 30)), (time(13, 0), time(15, 0))]),
            _status_item("hk", "港股", cn_now, [(time(9, 30), time(12, 0)), (time(13, 0), time(16, 0))]),
            _status_item("us", "美股", ny_now, [(time(9, 30), time(16, 0))]),
            _status_item("futures_cn", "国内期货", cn_now, [(time(9, 0), time(11, 30)), (time(13, 30), time(15, 0))]),
            _status_item("futures_overseas", "海外期货", ny_now, [(time(8, 0), time(17, 0))]),
        ],
    }


def danginvest_overview_snapshot(
    dashboard: MarketDashboardResponse,
    requested_date: str | None = None,
) -> dict[str, Any]:
    source_dt = _dashboard_trade_datetime(dashboard)
    trade_date = requested_date or source_dt.date().isoformat()
    activity = dashboard.a_share_activity
    breadth = activity or _cn_market_breadth(dashboard)
    up_count = int(getattr(breadth, "advances", 0) or 0) if breadth else 0
    down_count = int(getattr(breadth, "declines", 0) or 0) if breadth else 0
    flat_count = int(getattr(breadth, "unchanged", 0) or 0) if breadth else 0
    total_turnover = _a_share_turnover_yuan(dashboard)
    fund_flow = dashboard.fund_flow_summary.net_amount if dashboard.fund_flow_summary else None
    return {
        "ts": dashboard.as_of.isoformat(),
        "stale": dashboard.cache_status != "live",
        "meta": {
            "style": "danginvest-market-overview",
            "source": _source_summary(dashboard),
            "cache_status": dashboard.cache_status,
            "requestedDate": requested_date,
            "effectiveTradeDate": trade_date,
            "redirected": False,
            "timezone": "Asia/Shanghai",
        },
        "tradeDate": trade_date,
        "rowCount": up_count + down_count + flat_count,
        "snapshotTsMs": int(source_dt.timestamp() * 1000),
        "maxSnapshotMs": int(source_dt.timestamp() * 1000),
        "asOf": source_dt.isoformat(),
        "data": {
            "tradeDate": trade_date,
            "totalTurnoverYuan": total_turnover,
            "totalCount": up_count + down_count + flat_count,
            "upCount": up_count,
            "downCount": down_count,
            "flatCount": flat_count,
            "limitUpCount": int(getattr(breadth, "limit_up", 0) or 0) if breadth else 0,
            "limitDownCount": int(getattr(breadth, "limit_down", 0) or 0) if breadth else 0,
            "breakBoardCount": 0,
            "breakBoardRatePct": 0,
            "avgChangePct": _average_index_change(dashboard),
            "marketTemperature": float(getattr(activity, "sentiment", 0) or _cn_market_sentiment(dashboard)),
            "sentimentLabel": _sentiment_label(float(getattr(activity, "sentiment", 0) or _cn_market_sentiment(dashboard))),
            "northInflowYuan": None,
            "mainInflowYuan": fund_flow,
            "totalMarketCapYuan": None,
        },
    }


def danginvest_realtime_dashboard(dashboard: MarketDashboardResponse) -> dict[str, Any]:
    return {
        "ts": dashboard.as_of.isoformat(),
        "stale": dashboard.cache_status != "live",
        "cache_status": dashboard.cache_status,
        "source_status": [_jsonable(item) for item in dashboard.source_status],
        "overview": danginvest_overview_snapshot(dashboard),
        "groups": [_realtime_group_payload(group, dashboard) for group in REALTIME_GROUP_ORDER],
        "data": _jsonable(dashboard),
    }


def danginvest_intraday_dashboard(dashboard: MarketDashboardResponse, groups: list[str]) -> dict[str, Any]:
    requested = [group for group in groups if group in REALTIME_GROUP_TITLES] or ["indices-cn"]
    payload_groups = {group: _intraday_group_payload(group, dashboard) for group in requested}
    has_points = any(item["points"] for group in payload_groups.values() for item in group["items"])
    return {
        "ts": dashboard.as_of.isoformat(),
        "status": "live" if has_points else "unavailable",
        "stale": True,
        "source": "market-candles-daily-close",
        "detail": "free intraday source unavailable; using real daily close sparkline, not simulated ticks",
        "groups": payload_groups,
    }


def danginvest_news_response(
    news: list[MarketNewsItem],
    limit: int,
    offset: int,
    ts: datetime | None = None,
) -> dict[str, Any]:
    sorted_news = sorted(news, key=lambda item: item.published_at or datetime.min.replace(tzinfo=UTC), reverse=True)
    page = sorted_news[offset : offset + limit]
    current_ts = ts or datetime.now(UTC)
    return {
        "ts": current_ts.isoformat(),
        "count": len(sorted_news),
        "limit": limit,
        "offset": offset,
        "has_more": offset + limit < len(sorted_news),
        "data": [_news_payload(item, offset + index) for index, item in enumerate(page)],
        "next_after": _jsonable(page[-1].published_at) if offset + limit < len(sorted_news) and page else None,
    }


def danginvest_top_turnover_response(
    items: list[dict[str, Any]],
    market: str,
    limit: int,
    requested_date: str | None,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    sorted_items = sorted(items, key=lambda item: float(item.get("turnoverYuan") or 0), reverse=True)[:limit]
    current = as_of or datetime.now(UTC)
    trade_date = requested_date or current.astimezone(CN_TZ).date().isoformat()
    return {
        "mode": "top-turnover",
        "limit": limit,
        "stale": False,
        "tradeDate": trade_date,
        "snapshotTsMs": int(current.timestamp() * 1000),
        "maxSnapshotMs": int(current.timestamp() * 1000),
        "meta": {
            "timezone": "Asia/Shanghai",
            "requestedDate": requested_date,
            "effectiveTradeDate": trade_date,
            "redirected": False,
            "market": market,
        },
        "data": {
            "count": len(sorted_items),
            "items": sorted_items,
        },
        "asOf": current.isoformat(),
    }


def danginvest_market_snapshot(
    dashboard: MarketDashboardResponse,
    top_turnover: dict[str, Any],
    requested_date: str | None,
    news_limit: int = 120,
) -> dict[str, Any]:
    overview = danginvest_overview_snapshot(dashboard, requested_date)
    return {
        "ts": dashboard.as_of.isoformat(),
        "tradeDate": overview["tradeDate"],
        "stale": dashboard.cache_status != "live",
        "meta": overview["meta"],
        "status": danginvest_market_status(dashboard.as_of),
        "overview": overview,
        "realtime": danginvest_realtime_dashboard(dashboard),
        "news": danginvest_news_response(dashboard.market_news, news_limit, 0, dashboard.as_of),
        "topTurnover": top_turnover,
        "heatmap": {
            "etf": [_jsonable(item) for item in dashboard.etf_heatmap],
            "industry": [_jsonable(item) for item in dashboard.industry_heatmap],
            "sector": [_jsonable(item) for item in dashboard.sector_heatmap],
            "region": [_jsonable(item) for item in dashboard.region_heatmap],
            "concept": [_jsonable(item) for item in dashboard.concept_heatmap],
        },
        "commodities": [_jsonable(item) for item in dashboard.commodity_quotes],
        "dragonTiger": [_jsonable(item) for item in dashboard.dragon_tiger],
        "source_status": [_jsonable(item) for item in dashboard.source_status],
    }


def quote_to_turnover_item(quote: QuoteSnapshot) -> dict[str, Any]:
    code = quote.symbol.split(".")[0]
    return {
        "code": code,
        "symbol": quote.symbol,
        "name": quote.name,
        "price": quote.price,
        "changePct": quote.change_pct,
        "change_pct": quote.change_pct,
        "turnoverYuan": quote.turnover,
        "turnover": quote.turnover,
        "source": quote.source,
    }


def _status_item(market: str, name: str, local_now: datetime, sessions: list[tuple[time, time]]) -> dict[str, Any]:
    trade_day = _latest_trade_day(local_now.date())
    is_trade_day = local_now.weekday() < 5
    is_trading = is_trade_day and any(start <= local_now.time() <= end for start, end in sessions)
    status = "trading" if is_trading else "closed"
    return {
        "market": market,
        "name": name,
        "is_trading": is_trading,
        "status": status,
        "status_text": "交易中" if is_trading else "休市",
        "calendar_ok": True,
        "calendar_market": market,
        "is_trade_day": is_trade_day,
        "trade_date": trade_day.isoformat(),
        "prev_trade_date": _latest_trade_day(trade_day - timedelta(days=1)).isoformat(),
    }


def _latest_trade_day(value: date) -> date:
    current = value
    while current.weekday() >= 5:
        current -= timedelta(days=1)
    return current


def _weekday_name(weekday: int) -> str:
    return ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][weekday]


def _dashboard_trade_datetime(dashboard: MarketDashboardResponse) -> datetime:
    for candidate in (
        dashboard.a_share_activity.as_of if dashboard.a_share_activity else None,
        dashboard.a_share_turnover.as_of if dashboard.a_share_turnover else None,
        dashboard.primary_quote.as_of if dashboard.primary_quote else None,
        dashboard.as_of,
    ):
        if candidate is not None:
            return candidate if candidate.tzinfo else candidate.replace(tzinfo=UTC)
    return datetime.now(UTC)


def _cn_market_breadth(dashboard: MarketDashboardResponse) -> Any | None:
    for market in dashboard.markets:
        if market.market == "CN":
            return market.breadth
    return None


def _cn_market_sentiment(dashboard: MarketDashboardResponse) -> float:
    for market in dashboard.markets:
        if market.market == "CN":
            return float(market.sentiment)
    return 0


def _a_share_turnover_yuan(dashboard: MarketDashboardResponse) -> float | None:
    if dashboard.a_share_turnover and dashboard.a_share_turnover.value > 0:
        return dashboard.a_share_turnover.value
    for market in dashboard.markets:
        if market.market == "CN" and market.turnover > 0:
            return market.turnover * 100000000
    return None


def _average_index_change(dashboard: MarketDashboardResponse) -> float:
    quotes = [quote for market in dashboard.markets for quote in market.indices if quote.market == "CN"]
    if not quotes:
        return 0
    return round(sum(quote.change_pct for quote in quotes) / len(quotes), 4)


def _sentiment_label(value: float) -> str:
    if value >= 65:
        return "偏热"
    if value <= 35:
        return "偏冷"
    return "中性"


def _source_summary(dashboard: MarketDashboardResponse) -> str:
    sources = sorted({item.source for item in dashboard.source_status if item.source})
    if sources:
        return " / ".join(sources)
    quote_sources = sorted({quote.source for market in dashboard.markets for quote in market.indices if quote.source})
    return " / ".join(quote_sources) if quote_sources else "unavailable"


def _realtime_group_payload(group: str, dashboard: MarketDashboardResponse) -> dict[str, Any]:
    if group.startswith("indices"):
        items = [_quote_payload(quote, dashboard.index_sparklines.get(quote.symbol, [])) for quote in _quotes_for_group(group, dashboard)]
    elif group == "etf-broad":
        items = [_heat_item_card(item) for item in dashboard.etf_heatmap[:6]]
    elif group == "futures-domestic":
        items = [_commodity_card(item) for item in dashboard.commodity_quotes if "CNY" in item.unit or item.source.startswith("sge")]
    else:
        items = [_commodity_card(item) for item in dashboard.commodity_quotes if "CNY" not in item.unit and not item.source.startswith("sge")]
    return {
        "id": group,
        "title": REALTIME_GROUP_TITLES[group],
        "status": "live" if items else "unavailable",
        "items": items,
    }


def _intraday_group_payload(group: str, dashboard: MarketDashboardResponse) -> dict[str, Any]:
    items = []
    for quote in _quotes_for_group(group, dashboard):
        values = dashboard.index_sparklines.get(quote.symbol, [])
        first = values[0] if values else quote.price
        points = [
            {
                "time": f"D-{len(values) - index - 1}" if len(values) - index - 1 else "latest",
                "price": value,
                "change_pct": round((value - first) / first * 100, 4) if first else 0,
                "volume": None,
            }
            for index, value in enumerate(values)
        ]
        items.append({"symbol": quote.symbol, "name": quote.name, "points": points, "source": "market-candles-daily-close"})
    return {
        "id": group,
        "title": REALTIME_GROUP_TITLES.get(group, group),
        "date": _dashboard_trade_datetime(dashboard).date().isoformat(),
        "intervalSec": 86400,
        "updatedAt": dashboard.as_of.isoformat(),
        "items": items,
    }


def _quotes_for_group(group: str, dashboard: MarketDashboardResponse) -> list[QuoteSnapshot]:
    market_key = {"indices-cn": "CN", "indices-hk": "HK", "indices-us": "US", "indices-kr": "KR", "indices-jp": "JP"}.get(group)
    if not market_key:
        return []
    expected = [symbol for symbol, _ in INDEX_SYMBOLS[market_key]]
    quotes_by_symbol = {quote.symbol: quote for market in dashboard.markets for quote in market.indices}
    return [quotes_by_symbol[symbol] for symbol in expected if symbol in quotes_by_symbol]


def _quote_payload(quote: QuoteSnapshot, sparkline: list[float]) -> dict[str, Any]:
    payload = _jsonable(quote)
    payload["changePct"] = quote.change_pct
    payload["sparkline"] = sparkline
    payload["status"] = "live"
    return payload


def _heat_item_card(item: DashboardHeatItem) -> dict[str, Any]:
    return {
        "symbol": item.name,
        "name": item.name,
        "price": None,
        "changePct": item.change_pct,
        "change_pct": item.change_pct,
        "turnover": item.turnover,
        "source": item.source,
        "status": "live",
    }


def _commodity_card(item: Any) -> dict[str, Any]:
    return {
        "symbol": item.symbol,
        "name": item.name,
        "price": item.price,
        "change": item.change,
        "changePct": item.change_pct,
        "change_pct": item.change_pct,
        "unit": item.unit,
        "source": item.source,
        "sparkline": item.sparkline,
        "status": "live",
    }


def _news_payload(item: MarketNewsItem, index: int) -> dict[str, Any]:
    published = item.published_at.isoformat() if item.published_at else None
    return {
        "id": f"{published or 'unknown'}-{index}-{abs(hash(item.title))}",
        "source": item.source,
        "published_at": published,
        "title": item.title,
        "content": item.content,
        "url": item.url,
    }


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    return value
