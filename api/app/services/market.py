import asyncio
import json
import os
import importlib
import math
import subprocess
import sys
import time
from collections.abc import Callable, Iterable, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, TypeVar

import httpx

from app.schemas.market import (
    AShareActivity,
    AShareTurnover,
    CandleSnapshot,
    CommodityQuote,
    DashboardCacheStatus,
    DashboardHeatItem,
    DashboardSourceStatus,
    DragonTigerItem,
    FundFlowItem,
    FundFlowSummary,
    MarketNewsItem,
    MarketBreadth,
    MarketCode,
    MarketDashboardResponse,
    MarketHeatItem,
    MarketOverviewItem,
    QuoteSnapshot,
    SymbolSearchResult,
)
from app.services.etfs import ETFService, ETF_SPOT_SOURCE
from app.services.market_cache import CachedSnapshot, MarketSnapshotCache
from app.services.symbols import (
    currency_for_market,
    display_name_for_symbol,
    infer_market,
    normalize_symbol,
    search_static_symbols,
    yahoo_symbol,
)

AKSHARE_SOURCE = "akshare-eastmoney-free"
TENCENT_SOURCE = "tencent-free-delayed"
YAHOO_SOURCE = "Yahoo Finance/free delayed fallback"
DELAY = "免费公开源，可能延迟、缺失或被缓存"
LEGU_SOURCE = "legulegu-market-activity"
THS_SOURCE = "ths-fund-flow"
EASTMONEY_SOURCE = "eastmoney-sector-fund-flow"
NEWS_SOURCE = "cls-telegraph"
MODEL_NEWS_SOURCE = "model-web-search"
COMBINED_NEWS_SOURCE = "model-web-search/akshare-news"
COMMODITY_SOURCE = "akshare-commodity"
LHB_SOURCE = "eastmoney-lhb"
ASHARE_TURNOVER_SOURCE = "akshare-exchange-summary"
DRAGON_TIGER_SECTOR_FIELDS = ("所属行业", "行业", "板块", "行业板块", "sector", "industry")
SNAPSHOT_TTL_SECONDS = 10 * 60
SLOW_SNAPSHOT_TTL_SECONDS = 30 * 60
DASHBOARD_SOURCE_TIMEOUT_SECONDS = 8.0
DASHBOARD_SLOW_SOURCE_TIMEOUT_SECONDS = 12.0
DASHBOARD_OPTIONAL_SOURCE_TIMEOUT_SECONDS = 6.0
DASHBOARD_FAILURE_COOLDOWN_SECONDS = 3 * 60
DASHBOARD_HEATMAP_LIMIT = 120
DASHBOARD_OPTIONAL_STATUS_NAMES = {
    "etf_heatmap",
    "fund_flow_summary",
    "market_news",
    "commodity_quotes",
    "dragon_tiger",
    "index_sparklines",
}
AKSHARE_WORKER_ENV = "ZTOU_AKSHARE_WORKER"
T = TypeVar("T")

INDEX_SYMBOLS: dict[MarketCode, list[tuple[str, str]]] = {
    "CN": [("000001.SH", "上证指数"), ("399001.SZ", "深证成指"), ("399006.SZ", "创业板指")],
    "HK": [("HSTECH.HK", "恒生科技指数"), ("HSCEI.HK", "恒生国企")],
    "US": [("DJI", "道琼斯"), ("SPX", "标普500"), ("NDX", "纳斯达克100")],
}
INDEX_SYMBOL_SET = {symbol for pairs in INDEX_SYMBOLS.values() for symbol, _ in pairs} | {"HSI.HK"}

HEATMAP: dict[MarketCode, list[MarketHeatItem]] = {
    "CN": [
        MarketHeatItem(name="银行", change_pct=0.72, turnover=420, direction="up"),
        MarketHeatItem(name="半导体", change_pct=-0.46, turnover=388, direction="down"),
        MarketHeatItem(name="食品饮料", change_pct=1.18, turnover=310, direction="up"),
        MarketHeatItem(name="医药生物", change_pct=-0.21, turnover=270, direction="down"),
    ],
    "HK": [
        MarketHeatItem(name="互联网", change_pct=0.88, turnover=290, direction="up"),
        MarketHeatItem(name="地产", change_pct=-0.63, turnover=180, direction="down"),
        MarketHeatItem(name="金融", change_pct=0.34, turnover=210, direction="up"),
        MarketHeatItem(name="消费", change_pct=-0.17, turnover=150, direction="down"),
    ],
    "US": [
        MarketHeatItem(name="大型科技", change_pct=1.08, turnover=520, direction="up"),
        MarketHeatItem(name="半导体", change_pct=0.64, turnover=480, direction="up"),
        MarketHeatItem(name="能源", change_pct=-0.25, turnover=240, direction="down"),
        MarketHeatItem(name="金融", change_pct=0.18, turnover=260, direction="up"),
    ],
}


class MarketDataService:
    def __init__(
        self,
        cache_ttl_seconds: int = 90,
        akshare_module: object | None = None,
        snapshot_cache: MarketSnapshotCache | None = None,
        news_search_api_key: str = "",
        news_search_api_base: str = "https://api.openai.com/v1",
        news_search_model: str = "gpt-4.1-mini",
        news_search_timeout_seconds: float = 8.0,
        dashboard_source_timeout_seconds: float = DASHBOARD_SOURCE_TIMEOUT_SECONDS,
        dashboard_slow_source_timeout_seconds: float = DASHBOARD_SLOW_SOURCE_TIMEOUT_SECONDS,
        dashboard_optional_source_timeout_seconds: float = DASHBOARD_OPTIONAL_SOURCE_TIMEOUT_SECONDS,
    ) -> None:
        self.cache_ttl_seconds = cache_ttl_seconds
        self.akshare_module = akshare_module
        self.snapshot_cache = snapshot_cache or MarketSnapshotCache(_default_snapshot_cache_path())
        self.news_search_api_key = news_search_api_key
        self.news_search_api_base = news_search_api_base.rstrip("/")
        self.news_search_model = news_search_model
        self.news_search_timeout_seconds = news_search_timeout_seconds
        self.dashboard_source_timeout_seconds = max(0.1, dashboard_source_timeout_seconds)
        self.dashboard_slow_source_timeout_seconds = max(0.1, dashboard_slow_source_timeout_seconds)
        self.dashboard_optional_source_timeout_seconds = max(0.1, dashboard_optional_source_timeout_seconds)
        self._quote_cache: dict[str, tuple[float, QuoteSnapshot]] = {}
        self._candle_cache: dict[tuple[str, str, int], tuple[float, list[CandleSnapshot]]] = {}
        self._dashboard_failure_cache: dict[str, tuple[float, str]] = {}

    async def overview(self, markets: list[MarketCode]) -> list[MarketOverviewItem]:
        now = datetime.now(UTC)

        async def build_market_item(market: MarketCode) -> MarketOverviewItem:
            index_quotes = await self.quotes([symbol for symbol, _ in INDEX_SYMBOLS[market]])
            heatmap = HEATMAP[market]
            advances = sum(1 for item in heatmap if item.change_pct > 0)
            declines = sum(1 for item in heatmap if item.change_pct < 0)
            sentiment = _sentiment_from_quotes(index_quotes, advances, declines)
            return MarketOverviewItem(
                market=market,
                label={"CN": "A股", "HK": "港股", "US": "美股"}[market],
                indices=index_quotes,
                turnover=round(sum(item.turnover for item in index_quotes) / 100000000, 2),
                sentiment=sentiment,
                breadth=MarketBreadth(advances=advances, declines=declines, unchanged=max(0, 8 - advances - declines)),
                heatmap=heatmap,
                source=f"{AKSHARE_SOURCE} / {YAHOO_SOURCE}",
                delay_label=DELAY,
                as_of=now,
            )

        return list(await asyncio.gather(*(build_market_item(market) for market in markets)))

    async def quotes(self, symbols: list[str]) -> list[QuoteSnapshot]:
        normalized = [normalize_symbol(symbol, None) for symbol in symbols if symbol.strip()]
        unique_symbols = list(dict.fromkeys(normalized))
        fetched = await asyncio.gather(*(self.quote(symbol) for symbol in unique_symbols))
        quotes_by_symbol = dict(zip(unique_symbols, fetched, strict=True))
        return [quotes_by_symbol[symbol] for symbol in normalized]

    async def quote(self, symbol: str) -> QuoteSnapshot:
        normalized = normalize_symbol(symbol, None)
        cached = self._quote_cache.get(normalized)
        if cached and time.time() - cached[0] < self.cache_ttl_seconds:
            return cached[1]
        try:
            quote = await self._fetch_primary_quote(normalized)
        except Exception:
            quote = self._sample_quote(normalized)
        self._quote_cache[normalized] = (time.time(), quote)
        return quote

    async def candles(self, symbol: str, period: str, limit: int) -> list[CandleSnapshot]:
        normalized = normalize_symbol(symbol, None)
        normalized_period = period if period in {"daily", "weekly", "monthly"} else "daily"
        normalized_limit = max(20, min(limit, 240))
        key = (normalized, normalized_period, normalized_limit)
        cached = self._candle_cache.get(key)
        if cached and time.time() - cached[0] < self.cache_ttl_seconds:
            return cached[1]
        try:
            candles = await self._fetch_primary_candles(normalized, normalized_period, normalized_limit)
        except Exception:
            candles = self._sample_candles(normalized, normalized_period, normalized_limit)
        self._candle_cache[key] = (time.time(), candles)
        return candles

    async def search(self, query: str, markets: set[MarketCode] | None = None) -> list[SymbolSearchResult]:
        return search_static_symbols(query, markets)

    async def dashboard(self, markets: list[MarketCode], period: str) -> MarketDashboardResponse:
        normalized_markets = markets or ["CN", "HK", "US"]
        normalized_period = period if period in {"daily", "weekly", "monthly"} else "daily"
        source_timeout = self.dashboard_source_timeout_seconds
        slow_source_timeout = self.dashboard_slow_source_timeout_seconds
        optional_source_timeout = self.dashboard_optional_source_timeout_seconds
        news_timeout = max(optional_source_timeout, self.news_search_timeout_seconds)
        source_status: list[DashboardSourceStatus] = []

        primary_quote_task = asyncio.create_task(self._fetch_dashboard_quote("000001.SH"))
        primary_candles_task = asyncio.create_task(
            self._fetch_dashboard_candles(
                "000001.SH",
                normalized_period,
                120,
            )
        )
        activity_task = asyncio.create_task(self._cached_dashboard_source(
            key="dashboard:a_share_activity",
            name="a_share_activity",
            source=LEGU_SOURCE,
            ttl_seconds=SNAPSHOT_TTL_SECONDS,
            fetcher=self._fetch_a_share_activity_sync,
            serializer=lambda item: item.model_dump(mode="json"),
            deserializer=lambda payload: AShareActivity.model_validate(payload),
            empty_value=None,
            timeout_seconds=source_timeout,
        ))

        turnover_task = asyncio.create_task(self._cached_dashboard_source(
            key="dashboard:a_share_turnover",
            name="a_share_turnover",
            source=ASHARE_TURNOVER_SOURCE,
            ttl_seconds=SNAPSHOT_TTL_SECONDS,
            fetcher=self._fetch_a_share_turnover_sync,
            serializer=lambda item: item.model_dump(mode="json"),
            deserializer=lambda payload: AShareTurnover.model_validate(payload),
            empty_value=None,
            timeout_seconds=source_timeout,
        ))

        etf_task = asyncio.create_task(self._cached_dashboard_source(
            key="dashboard:etf_heatmap",
            name="etf_heatmap",
            source=ETF_SPOT_SOURCE,
            ttl_seconds=SNAPSHOT_TTL_SECONDS,
            fetcher=self._fetch_etf_heatmap_sync,
            serializer=lambda items: {"items": [item.model_dump(mode="json") for item in items]},
            deserializer=lambda payload: [DashboardHeatItem.model_validate(item) for item in payload.get("items", [])],
            empty_value=[],
            timeout_seconds=source_timeout,
        ))

        industry_task = asyncio.create_task(self._cached_dashboard_source(
            key="dashboard:industry_heatmap",
            name="industry_heatmap",
            source=THS_SOURCE,
            ttl_seconds=SNAPSHOT_TTL_SECONDS,
            fetcher=lambda: self._fetch_fund_flow_heatmap_sync("industry"),
            serializer=lambda items: {"items": [item.model_dump(mode="json") for item in items]},
            deserializer=lambda payload: [DashboardHeatItem.model_validate(item) for item in payload.get("items", [])],
            empty_value=[],
            timeout_seconds=source_timeout,
        ))

        sector_task = asyncio.create_task(self._cached_dashboard_source(
            key="dashboard:sector_heatmap",
            name="sector_heatmap",
            source=EASTMONEY_SOURCE,
            ttl_seconds=SNAPSHOT_TTL_SECONDS,
            fetcher=self._fetch_sector_heatmap_sync,
            serializer=lambda items: {"items": [item.model_dump(mode="json") for item in items]},
            deserializer=lambda payload: [DashboardHeatItem.model_validate(item) for item in payload.get("items", [])],
            empty_value=[],
            timeout_seconds=optional_source_timeout,
        ))

        concept_task = asyncio.create_task(self._cached_dashboard_source(
            key="dashboard:concept_heatmap",
            name="concept_heatmap",
            source=THS_SOURCE,
            ttl_seconds=SNAPSHOT_TTL_SECONDS,
            fetcher=lambda: self._fetch_fund_flow_heatmap_sync("concept"),
            serializer=lambda items: {"items": [item.model_dump(mode="json") for item in items]},
            deserializer=lambda payload: [DashboardHeatItem.model_validate(item) for item in payload.get("items", [])],
            empty_value=[],
            timeout_seconds=source_timeout,
        ))

        region_task = asyncio.create_task(self._cached_dashboard_source(
            key="dashboard:region_heatmap",
            name="region_heatmap",
            source=EASTMONEY_SOURCE,
            ttl_seconds=SNAPSHOT_TTL_SECONDS,
            fetcher=self._fetch_region_heatmap_sync,
            serializer=lambda items: {"items": [item.model_dump(mode="json") for item in items]},
            deserializer=lambda payload: [DashboardHeatItem.model_validate(item) for item in payload.get("items", [])],
            empty_value=[],
            timeout_seconds=optional_source_timeout,
        ))

        fund_task = asyncio.create_task(self._cached_dashboard_source(
            key="dashboard:fund_flow_summary",
            name="fund_flow_summary",
            source=THS_SOURCE,
            ttl_seconds=SLOW_SNAPSHOT_TTL_SECONDS,
            fetcher=self._fetch_fund_flow_summary_sync,
            serializer=lambda item: item.model_dump(mode="json"),
            deserializer=lambda payload: FundFlowSummary.model_validate(payload),
            empty_value=None,
            timeout_seconds=slow_source_timeout,
        ))

        news_task = asyncio.create_task(self._cached_dashboard_source(
            key="dashboard:market_news",
            name="market_news",
            source=COMBINED_NEWS_SOURCE,
            ttl_seconds=SNAPSHOT_TTL_SECONDS,
            fetcher=self._fetch_market_news_sync,
            serializer=lambda items: {"items": [item.model_dump(mode="json") for item in items]},
            deserializer=lambda payload: [MarketNewsItem.model_validate(item) for item in payload.get("items", [])],
            empty_value=[],
            timeout_seconds=news_timeout,
        ))

        commodity_task = asyncio.create_task(self._cached_dashboard_source(
            key="dashboard:commodity_quotes",
            name="commodity_quotes",
            source=COMMODITY_SOURCE,
            ttl_seconds=SNAPSHOT_TTL_SECONDS,
            fetcher=self._fetch_commodity_quotes_sync,
            serializer=lambda items: {"items": [item.model_dump(mode="json") for item in items]},
            deserializer=lambda payload: [CommodityQuote.model_validate(item) for item in payload.get("items", [])],
            empty_value=[],
            timeout_seconds=source_timeout,
        ))

        dragon_tiger_task = asyncio.create_task(self._cached_dashboard_source(
            key="dashboard:dragon_tiger",
            name="dragon_tiger",
            source=LHB_SOURCE,
            ttl_seconds=SLOW_SNAPSHOT_TTL_SECONDS,
            fetcher=self._fetch_dragon_tiger_sync,
            serializer=lambda items: {"items": [item.model_dump(mode="json") for item in items]},
            deserializer=lambda payload: [DragonTigerItem.model_validate(item) for item in payload.get("items", [])],
            empty_value=[],
            timeout_seconds=slow_source_timeout,
        ))

        activity, activity_status = await activity_task
        a_share_turnover, turnover_status = await turnover_task
        if a_share_turnover is not None:
            a_share_turnover.status = turnover_status.status
        market_task = asyncio.create_task(self._dashboard_markets(normalized_markets, activity, a_share_turnover))
        market_items, market_status = await market_task
        sparkline_task = asyncio.create_task(self._dashboard_index_sparklines(market_items))

        (
            (primary_quote, primary_quote_status),
            (primary_candles, primary_candles_status),
            (etf_heatmap, etf_status),
            (industry_heatmap, industry_status),
            (sector_heatmap, sector_status),
            (concept_heatmap, concept_status),
            (region_heatmap, region_status),
            (fund_flow_summary, fund_status),
            (market_news, news_status),
            (commodity_quotes, commodity_status),
            (dragon_tiger, dragon_tiger_status),
            (index_sparklines, sparkline_status),
        ) = await asyncio.gather(
            primary_quote_task,
            primary_candles_task,
            etf_task,
            industry_task,
            sector_task,
            concept_task,
            region_task,
            fund_task,
            news_task,
            commodity_task,
            dragon_tiger_task,
            sparkline_task,
        )
        source_status.extend(
            [
                primary_quote_status,
                primary_candles_status,
                activity_status,
                turnover_status,
                etf_status,
                industry_status,
                sector_status,
                concept_status,
                region_status,
                fund_status,
                news_status,
                commodity_status,
                dragon_tiger_status,
                market_status,
                sparkline_status,
            ]
        )

        return MarketDashboardResponse(
            as_of=datetime.now(UTC),
            cache_status=_dashboard_cache_status(source_status),
            source_status=source_status,
            primary_quote=primary_quote,
            primary_candles=primary_candles,
            markets=market_items,
            a_share_activity=activity,
            a_share_turnover=a_share_turnover,
            fund_flow_summary=fund_flow_summary,
            etf_heatmap=etf_heatmap,
            industry_heatmap=industry_heatmap,
            sector_heatmap=sector_heatmap,
            concept_heatmap=concept_heatmap,
            region_heatmap=region_heatmap,
            market_news=market_news,
            commodity_quotes=commodity_quotes,
            dragon_tiger=dragon_tiger,
            index_sparklines=index_sparklines,
            disclaimer="免费公开源可能延迟、缺失或被缓存；缓存数据会在来源状态中标记。",
        )

    async def _fetch_dashboard_quote(self, symbol: str) -> tuple[QuoteSnapshot | None, DashboardSourceStatus]:
        try:
            quote = await asyncio.wait_for(
                self._fetch_quote_without_sample(symbol),
                timeout=self.dashboard_source_timeout_seconds,
            )
            return quote, DashboardSourceStatus(name="primary_quote", status="live", source=quote.source, as_of=quote.as_of)
        except Exception as exc:
            detail = f"source timed out after {self.dashboard_source_timeout_seconds:g}s" if isinstance(exc, TimeoutError) else str(exc)
            return None, DashboardSourceStatus(
                name="primary_quote",
                status="unavailable",
                source="market-quote",
                detail=detail,
            )

    async def _fetch_dashboard_candles(
        self,
        symbol: str,
        period: str,
        limit: int,
    ) -> tuple[list[CandleSnapshot], DashboardSourceStatus]:
        try:
            candles = await asyncio.wait_for(
                self._fetch_primary_candles(normalize_symbol(symbol, None), period, limit),
                timeout=self.dashboard_source_timeout_seconds,
            )
            source = candles[-1].source if candles else "market-candles"
            if source == "sample fallback":
                raise RuntimeError(f"sample candles rejected for dashboard: {symbol}")
            return candles, DashboardSourceStatus(name="primary_candles", status="live", source=source)
        except Exception as exc:
            detail = f"source timed out after {self.dashboard_source_timeout_seconds:g}s" if isinstance(exc, TimeoutError) else str(exc)
            return [], DashboardSourceStatus(
                name="primary_candles",
                status="unavailable",
                source="market-candles",
                detail=detail,
            )

    async def _dashboard_markets(
        self,
        markets: list[MarketCode],
        activity: AShareActivity | None,
        a_share_turnover: AShareTurnover | None,
    ) -> tuple[list[MarketOverviewItem], DashboardSourceStatus]:
        statuses: list[str] = []

        async def build_market(market: MarketCode) -> MarketOverviewItem:
            async def fetch_index_quote(symbol: str) -> QuoteSnapshot:
                return await asyncio.wait_for(
                    self._fetch_quote_without_sample(symbol),
                    timeout=self.dashboard_source_timeout_seconds,
                )

            quotes = await asyncio.gather(
                *(fetch_index_quote(symbol) for symbol, _ in INDEX_SYMBOLS[market]),
                return_exceptions=True,
            )
            live_quotes = [quote for quote in quotes if isinstance(quote, QuoteSnapshot)]
            statuses.extend("live" if isinstance(quote, QuoteSnapshot) else "unavailable" for quote in quotes)
            advances = activity.advances if market == "CN" and activity else sum(1 for quote in live_quotes if quote.change_pct > 0)
            declines = activity.declines if market == "CN" and activity else sum(1 for quote in live_quotes if quote.change_pct < 0)
            unchanged = activity.unchanged if market == "CN" and activity else max(0, len(live_quotes) - advances - declines)
            sentiment = activity.sentiment if market == "CN" and activity else _sentiment_from_quotes(live_quotes, advances, declines)
            turnover = (
                round(a_share_turnover.value / 100000000, 2)
                if market == "CN" and a_share_turnover is not None and a_share_turnover.value > 0
                else round(sum(item.turnover for item in live_quotes) / 100000000, 2)
                if market != "CN"
                else 0
            )
            return MarketOverviewItem(
                market=market,
                label={"CN": "A股", "HK": "港股", "US": "美股"}[market],
                indices=live_quotes,
                turnover=turnover,
                sentiment=sentiment,
                breadth=MarketBreadth(
                    advances=advances,
                    declines=declines,
                    unchanged=unchanged,
                    limit_up=activity.limit_up if market == "CN" and activity else 0,
                    limit_down=activity.limit_down if market == "CN" and activity else 0,
                ),
                heatmap=[],
                source=" / ".join(sorted({quote.source for quote in live_quotes})) if live_quotes else "unavailable",
                delay_label=DELAY,
                as_of=datetime.now(UTC),
            )

        items = list(await asyncio.gather(*(build_market(market) for market in markets)))
        status = "live" if statuses and all(item == "live" for item in statuses) else "unavailable"
        return items, DashboardSourceStatus(name="index_markets", status=status, source="market-index-quotes")

    async def _fetch_quote_without_sample(self, symbol: str) -> QuoteSnapshot:
        normalized = normalize_symbol(symbol, None)
        cached = self._quote_cache.get(normalized)
        if cached and time.time() - cached[0] < self.cache_ttl_seconds and cached[1].source != "sample fallback":
            return cached[1]
        quote = await self._fetch_primary_quote(normalized)
        if quote.source == "sample fallback":
            raise RuntimeError(f"sample quote rejected for dashboard: {normalized}")
        self._quote_cache[normalized] = (time.time(), quote)
        return quote

    async def _cached_dashboard_source(
        self,
        key: str,
        name: str,
        source: str,
        ttl_seconds: int,
        fetcher: Callable[[], T],
        serializer: Callable[[T], dict[str, Any]],
        deserializer: Callable[[dict[str, Any]], T],
        empty_value: T,
        timeout_seconds: float = DASHBOARD_SOURCE_TIMEOUT_SECONDS,
    ) -> tuple[T, DashboardSourceStatus]:
        cached = self.snapshot_cache.get(key)
        if cached is not None and not cached.is_stale:
            return deserializer(cached.payload), DashboardSourceStatus(
                name=name,
                status="live",
                source=cached.source,
                detail="served from fresh SQLite cache",
                as_of=cached.fetched_at,
            )
        failed = self._dashboard_failure_cache.get(key)
        if failed is not None and time.time() - failed[0] < DASHBOARD_FAILURE_COOLDOWN_SECONDS:
            detail = f"recent source failure: {failed[1]}"
            if cached is not None:
                return deserializer(cached.payload), _cached_status(name, cached, detail)
            return empty_value, DashboardSourceStatus(name=name, status="unavailable", source=source, detail=detail)
        try:
            result = await asyncio.wait_for(asyncio.to_thread(fetcher), timeout=timeout_seconds)
            self.snapshot_cache.save(key, serializer(result), source, ttl_seconds)
            self._dashboard_failure_cache.pop(key, None)
            return result, DashboardSourceStatus(name=name, status="live", source=source, as_of=datetime.now(UTC))
        except Exception as exc:
            detail = f"source timed out after {timeout_seconds:g}s" if isinstance(exc, TimeoutError) else str(exc)
            self._dashboard_failure_cache[key] = (time.time(), detail)
            cached = self.snapshot_cache.get(key)
            if cached is not None:
                return deserializer(cached.payload), _cached_status(name, cached, detail)
            return empty_value, DashboardSourceStatus(name=name, status="unavailable", source=source, detail=detail)

    def _fetch_a_share_activity_sync(self) -> AShareActivity:
        if self._use_akshare_worker():
            payload = self._run_akshare_worker_sync("a_share_activity", timeout_seconds=self.dashboard_source_timeout_seconds)
            return AShareActivity.model_validate(payload)
        with _without_proxy_env():
            rows = _records(self._akshare().stock_market_activity_legu())
        values = {str(_row_value(row, ("item",))): _row_value(row, ("value",)) for row in rows}
        as_of = _parse_optional_datetime(values.get("统计日期"))
        return AShareActivity(
            advances=int(parse_cn_money(values.get("上涨"))),
            declines=int(parse_cn_money(values.get("下跌"))),
            unchanged=int(parse_cn_money(values.get("平盘"))),
            limit_up=int(parse_cn_money(values.get("涨停"))),
            limit_down=int(parse_cn_money(values.get("跌停"))),
            suspended=int(parse_cn_money(values.get("停牌"))),
            sentiment=max(0, min(100, parse_pct(values.get("活跃度")))),
            source=LEGU_SOURCE,
            as_of=as_of,
        )

    def _fetch_a_share_turnover_sync(self) -> AShareTurnover:
        with _without_proxy_env():
            akshare = self._akshare()
            sse_rows = _records(akshare.stock_sse_summary())
            szse_rows = _records(akshare.stock_szse_summary())
        sse_value = _exchange_turnover_from_rows(sse_rows)
        szse_value = _exchange_turnover_from_rows(szse_rows)
        total = sse_value + szse_value
        if total <= 0:
            raise RuntimeError("exchange summaries returned no A-share turnover")
        as_of = _latest_datetime_from_rows([*sse_rows, *szse_rows])
        return AShareTurnover(
            value=round(total, 4),
            unit="CNY",
            sse_value=round(sse_value, 4),
            szse_value=round(szse_value, 4),
            source=ASHARE_TURNOVER_SOURCE,
            status="live",
            as_of=as_of,
        )

    def _fetch_fund_flow_heatmap_sync(self, kind: str) -> list[DashboardHeatItem]:
        if self._use_akshare_worker():
            payload = self._run_akshare_worker_sync(f"{kind}_heatmap", timeout_seconds=self.dashboard_source_timeout_seconds)
            return [DashboardHeatItem.model_validate(item) for item in payload]
        with _without_proxy_env():
            akshare = self._akshare()
            if kind == "industry":
                rows = _records(akshare.stock_fund_flow_industry(symbol="即时"))
            elif kind == "concept":
                rows = _records(akshare.stock_fund_flow_concept(symbol="即时"))
            else:
                raise ValueError(f"Unsupported heatmap kind: {kind}")
        return _heat_items_from_rows(rows, THS_SOURCE, limit=DASHBOARD_HEATMAP_LIMIT)

    def _fetch_region_heatmap_sync(self) -> list[DashboardHeatItem]:
        if self._use_akshare_worker():
            payload = self._run_akshare_worker_sync("region_heatmap", timeout_seconds=self.dashboard_optional_source_timeout_seconds)
            return [DashboardHeatItem.model_validate(item) for item in payload]
        with _without_proxy_env():
            rows = _records(
                self._akshare().stock_sector_fund_flow_rank(
                    indicator="今日",
                    sector_type="地域资金流",
                )
            )
        return _heat_items_from_rows(rows, EASTMONEY_SOURCE, limit=DASHBOARD_HEATMAP_LIMIT)

    def _fetch_sector_heatmap_sync(self) -> list[DashboardHeatItem]:
        if self._use_akshare_worker():
            payload = self._run_akshare_worker_sync("sector_heatmap", timeout_seconds=self.dashboard_optional_source_timeout_seconds)
            return [DashboardHeatItem.model_validate(item) for item in payload]
        with _without_proxy_env():
            rows = _records(
                self._akshare().stock_sector_fund_flow_rank(
                    indicator="今日",
                    sector_type="行业资金流",
                )
            )
        return _heat_items_from_rows(rows, EASTMONEY_SOURCE, limit=DASHBOARD_HEATMAP_LIMIT)

    def _fetch_etf_heatmap_sync(self) -> list[DashboardHeatItem]:
        if self._use_akshare_worker():
            payload = self._run_akshare_worker_sync("etf_heatmap", timeout_seconds=self.dashboard_source_timeout_seconds)
            return [DashboardHeatItem.model_validate(item) for item in payload]
        response = ETFService(akshare_module=self.akshare_module)._search_sync("", DASHBOARD_HEATMAP_LIMIT)
        if response.status != "live":
            raise RuntimeError(response.detail or "ETF spot source unavailable")
        items: list[DashboardHeatItem] = []
        for quote in response.items:
            change_pct = quote.change_pct or 0
            turnover = quote.turnover or 0
            items.append(
                DashboardHeatItem(
                    name=quote.name,
                    change_pct=change_pct,
                    turnover=turnover,
                    net_amount=0,
                    direction=_direction_for_pct(change_pct),
                    source=quote.source,
                )
            )
        return items[:DASHBOARD_HEATMAP_LIMIT]

    def _fetch_fund_flow_summary_sync(self) -> FundFlowSummary:
        if self._use_akshare_worker():
            payload = self._run_akshare_worker_sync("fund_flow_summary", timeout_seconds=self.dashboard_slow_source_timeout_seconds)
            return FundFlowSummary.model_validate(payload)
        with _without_proxy_env():
            rows = _records(self._akshare().stock_fund_flow_individual(symbol="即时"))
        items = [_fund_flow_item_from_row(row) for row in rows]
        items = [item for item in items if item.name]
        inflows = sorted(items, key=lambda item: item.net_amount, reverse=True)[:5]
        outflows = sorted(items, key=lambda item: item.net_amount)[:5]
        return FundFlowSummary(
            top_inflows=inflows,
            top_outflows=outflows,
            net_amount=sum(item.net_amount for item in items),
            source=THS_SOURCE,
            as_of=datetime.now(UTC),
        )

    def _fetch_market_news_sync(self) -> list[MarketNewsItem]:
        items: list[MarketNewsItem] = []
        errors: list[str] = []

        if self.news_search_api_key:
            try:
                items.extend(self._fetch_model_market_news_sync())
            except Exception as exc:
                errors.append(f"{MODEL_NEWS_SOURCE}: {exc}")

        if self._use_akshare_worker():
            try:
                payload = self._run_akshare_worker_sync(
                    "market_news",
                    timeout_seconds=max(self.dashboard_optional_source_timeout_seconds, self.news_search_timeout_seconds),
                )
                items.extend(MarketNewsItem.model_validate(item) for item in payload)
            except Exception as exc:
                errors.append(f"{NEWS_SOURCE}: {exc}")
            if items:
                return _dedupe_news_items(items)[:24]
            raise RuntimeError("; ".join(errors) or "market news returned no rows")

        akshare = self._akshare()
        for source, fetcher in (
            (NEWS_SOURCE, lambda: akshare.stock_info_global_cls(symbol="全部")),
            ("eastmoney-global-news", lambda: akshare.stock_info_global_em()),
            ("ths-global-news", lambda: akshare.stock_info_global_ths()),
        ):
            try:
                with _without_proxy_env():
                    rows = _records(fetcher())
                items.extend(_news_items_from_rows(rows, source))
            except Exception as exc:
                errors.append(f"{source}: {exc}")
        if items:
            return _dedupe_news_items(items)[:24]
        raise RuntimeError("; ".join(errors) or "market news returned no rows")

    def _fetch_model_market_news_sync(self) -> list[MarketNewsItem]:
        prompt = _model_news_prompt()
        payload = {
            "model": self.news_search_model,
            "tools": [{"type": "web_search"}],
            "tool_choice": "required",
            "input": prompt,
        }
        async_base = self.news_search_api_base.rstrip("/")
        async_url = f"{async_base}/responses"
        with httpx.Client(timeout=self.news_search_timeout_seconds, trust_env=False) as client:
            response = client.post(
                async_url,
                headers={"Authorization": f"Bearer {self.news_search_api_key}"},
                json=payload,
            )
            response.raise_for_status()
        body = response.json()
        text = _responses_output_text(body)
        if not text:
            raise RuntimeError("model web search returned no text")
        parsed = _json_object_from_text(text)
        return _model_news_items_from_payload(parsed)

    def _fetch_commodity_quotes_sync(self) -> list[CommodityQuote]:
        if self._use_akshare_worker():
            payload = self._run_akshare_worker_sync("commodity_quotes", timeout_seconds=self.dashboard_source_timeout_seconds)
            return [CommodityQuote.model_validate(item) for item in payload]
        akshare = self._akshare()
        items: list[CommodityQuote] = []
        with _without_proxy_env():
            for symbol, name, unit in (
                ("Au99.99", "黄金连续", "CNY/g"),
                ("Ag(T+D)", "白银延期", "CNY/kg"),
            ):
                try:
                    rows = _records(akshare.spot_quotations_sge(symbol=symbol))
                    quote = _commodity_from_sge_rows(rows, symbol, name, unit)
                    if quote is not None:
                        items.append(quote)
                except Exception:
                    continue
            try:
                rows = _records(akshare.futures_global_spot_em())
                items.extend(_commodities_from_global_futures(rows))
            except Exception:
                pass
        if not items:
            raise RuntimeError("commodity sources returned no rows")
        return items[:6]

    def _fetch_dragon_tiger_sync(self) -> list[DragonTigerItem]:
        if self._use_akshare_worker():
            payload = self._run_akshare_worker_sync("dragon_tiger", timeout_seconds=self.dashboard_slow_source_timeout_seconds)
            return [DragonTigerItem.model_validate(item) for item in payload]
        today = datetime.now(UTC).date()
        start_date = (today - timedelta(days=10)).strftime("%Y%m%d")
        end_date = today.strftime("%Y%m%d")
        with _without_proxy_env():
            rows = _records(self._akshare().stock_lhb_detail_em(start_date=start_date, end_date=end_date))
        items = [_dragon_tiger_item_from_row(row) for row in rows]
        items = [item for item in items if item is not None]
        if not items:
            raise RuntimeError("dragon tiger source returned no rows")
        latest_date = max(item.trade_date for item in items)
        latest_items = [item for item in items if item.trade_date == latest_date]
        latest_items = sorted(latest_items, key=lambda item: item.net_amount, reverse=True)
        sector_by_code = self._dragon_tiger_sector_map_sync(latest_items)
        enriched_items: list[DragonTigerItem] = []
        for item in latest_items:
            code = _dragon_tiger_code_key(item.symbol)
            sector = item.sector or sector_by_code.get(code, "")
            enriched_items.append(
                item.model_copy(
                    update={
                        "sector": sector,
                    }
                )
            )
        return enriched_items

    def _dragon_tiger_sector_map_sync(self, items: list[DragonTigerItem]) -> dict[str, str]:
        missing_codes = {_dragon_tiger_code_key(item.symbol) for item in items if not item.sector}
        missing_codes.discard("")
        if not missing_codes:
            return {}
        try:
            with _without_proxy_env():
                rows = _records(self._akshare().stock_zh_a_spot_em())
        except Exception:
            return {}

        sectors: dict[str, str] = {}
        for row in rows:
            code = _dragon_tiger_code_key(_row_value(row, ("代码", "股票代码", "code", "symbol")))
            if code not in missing_codes or code in sectors:
                continue
            sector = _dragon_tiger_sector_from_row(row)
            if sector:
                sectors[code] = sector
        return sectors

    async def _dashboard_index_sparklines(
        self,
        markets: list[MarketOverviewItem],
    ) -> tuple[dict[str, list[float]], DashboardSourceStatus]:
        symbols = list(dict.fromkeys(quote.symbol for market in markets for quote in market.indices))
        output: dict[str, list[float]] = {}
        errors: list[str] = []

        async def fetch_symbol(symbol: str) -> tuple[str, list[float] | None, str | None]:
            try:
                candles = await asyncio.wait_for(
                    self._fetch_primary_candles(symbol, "daily", 24),
                    timeout=self.dashboard_source_timeout_seconds,
                )
                closes = [round(candle.close, 4) for candle in candles[-18:] if candle.close > 0]
                return symbol, closes or None, None
            except Exception as exc:
                detail = f"timed out after {self.dashboard_source_timeout_seconds:g}s" if isinstance(exc, TimeoutError) else str(exc)
                return symbol, None, detail

        for symbol, closes, error in await asyncio.gather(*(fetch_symbol(symbol) for symbol in symbols)):
            if closes:
                output[symbol] = closes
            elif error:
                errors.append(f"{symbol}: {error}")

        if output:
            return output, DashboardSourceStatus(
                name="index_sparklines",
                status="live",
                source="market-candles",
                detail="; ".join(errors[:3]),
            )
        return output, DashboardSourceStatus(
            name="index_sparklines",
            status="unavailable",
            source="market-candles",
            detail="; ".join(errors[:3]) or "no index sparkline data",
        )

    async def _fetch_primary_quote(self, symbol: str) -> QuoteSnapshot:
        market = infer_market(symbol)
        if market in {"CN", "HK"} and symbol in INDEX_SYMBOL_SET:
            try:
                return await self._fetch_tencent_quote(symbol)
            except Exception:
                pass
        if market in {"CN", "HK"}:
            try:
                return await asyncio.to_thread(self._fetch_akshare_quote_sync, symbol)
            except Exception:
                pass
            try:
                return await self._fetch_tencent_quote(symbol)
            except Exception:
                pass
        return await self._fetch_yahoo_quote(symbol)

    async def _fetch_primary_candles(self, symbol: str, period: str, limit: int) -> list[CandleSnapshot]:
        market = infer_market(symbol)
        if market in {"CN", "HK"} and symbol in INDEX_SYMBOL_SET:
            try:
                return await self._fetch_yahoo_candles(symbol, period, limit)
            except Exception:
                pass
        if market in {"CN", "HK"}:
            try:
                return await asyncio.to_thread(self._fetch_akshare_candles_sync, symbol, period, limit)
            except Exception:
                pass
        return await self._fetch_yahoo_candles(symbol, period, limit)

    def _akshare(self) -> object:
        if self.akshare_module is None:
            self.akshare_module = importlib.import_module("akshare")
        return self.akshare_module

    def _fetch_akshare_quote_sync(self, symbol: str) -> QuoteSnapshot:
        if self._use_akshare_worker():
            payload = self._run_akshare_worker_sync("quote", symbol, timeout_seconds=self.dashboard_source_timeout_seconds)
            return QuoteSnapshot.model_validate(payload)
        with _without_proxy_env():
            akshare = self._akshare()
            market = infer_market(symbol)
            code = _plain_code(symbol)
            rows = self._akshare_quote_rows(akshare, symbol, market)
        row = _find_row_by_code(rows, code)
        if row is None:
            raise RuntimeError(f"AKShare returned no quote for {symbol}")
        price = _safe_float(_row_value(row, ("最新价", "收盘", "现价", "price")))
        change = _safe_float(_row_value(row, ("涨跌额", "change")))
        change_pct = _safe_float(_row_value(row, ("涨跌幅", "change_pct", "涨幅")))
        volume = _safe_float(_row_value(row, ("成交量", "volume")))
        turnover = _safe_float(_row_value(row, ("成交额", "turnover", "amount")))
        name = str(_row_value(row, ("名称", "name")) or display_name_for_symbol(symbol))
        if price <= 0:
            raise RuntimeError(f"AKShare returned invalid price for {symbol}")
        return QuoteSnapshot(
            symbol=symbol,
            name=name,
            market=market,
            price=round(price, 4),
            change=round(change, 4),
            change_pct=round(change_pct, 4),
            volume=volume,
            turnover=turnover,
            currency=currency_for_market(market),
            source=AKSHARE_SOURCE,
            as_of=datetime.now(UTC),
            delay_label=DELAY,
        )

    def _akshare_quote_rows(self, akshare: object, symbol: str, market: MarketCode) -> list[Mapping[str, object]]:
        if market == "HK":
            return _records(akshare.stock_hk_spot_em())
        if symbol in {"000001.SH", "399001.SZ", "399006.SZ"}:
            try:
                return _records(akshare.stock_zh_index_spot_em(symbol="沪深重要指数"))
            except TypeError:
                return _records(akshare.stock_zh_index_spot_em())
        return _records(akshare.stock_zh_a_spot_em())

    def _fetch_akshare_candles_sync(self, symbol: str, period: str, limit: int) -> list[CandleSnapshot]:
        if self._use_akshare_worker():
            payload = self._run_akshare_worker_sync(
                "candles",
                symbol,
                period,
                str(limit),
                timeout_seconds=self.dashboard_source_timeout_seconds,
            )
            return [CandleSnapshot.model_validate(item) for item in payload]
        with _without_proxy_env():
            akshare = self._akshare()
            market = infer_market(symbol)
            source_period = "daily" if period in {"daily", "weekly", "monthly"} else "daily"
            start_date = (datetime.now(UTC) - timedelta(days=_history_days_for_period(period, limit))).strftime("%Y%m%d")
            end_date = datetime.now(UTC).strftime("%Y%m%d")
            table = self._akshare_candle_table(akshare, symbol, market, source_period, start_date, end_date)
        candles = _candles_from_records(_records(table), symbol, AKSHARE_SOURCE, DELAY)
        if period in {"weekly", "monthly"}:
            candles = _aggregate_candles(candles, period)
        if not candles:
            raise RuntimeError(f"AKShare returned no candles for {symbol}")
        return candles[-limit:]

    def _akshare_candle_table(
        self,
        akshare: object,
        symbol: str,
        market: MarketCode,
        period: str,
        start_date: str,
        end_date: str,
    ) -> object:
        code = _plain_code(symbol)
        if market == "HK":
            try:
                return akshare.stock_hk_hist(
                    symbol=code,
                    period=period,
                    start_date=start_date,
                    end_date=end_date,
                    adjust="",
                )
            except AttributeError:
                return akshare.stock_hk_daily(symbol=code, adjust="")
        if symbol in {"000001.SH", "399001.SZ", "399006.SZ"}:
            try:
                return akshare.index_zh_a_hist(
                    symbol=code,
                    period=period,
                    start_date=start_date,
                    end_date=end_date,
                )
            except AttributeError:
                provider_symbol = ("sz" if symbol.endswith(".SZ") else "sh") + code
                return akshare.stock_zh_index_daily(symbol=provider_symbol)
        return akshare.stock_zh_a_hist(
            symbol=code,
            period=period,
            start_date=start_date,
            end_date=end_date,
            adjust="",
        )

    def _use_akshare_worker(self) -> bool:
        return self.akshare_module is None and os.environ.get(AKSHARE_WORKER_ENV) != "1"

    def _run_akshare_worker_sync(
        self,
        operation: str,
        *args: str,
        timeout_seconds: float = DASHBOARD_SOURCE_TIMEOUT_SECONDS,
    ) -> Any:
        env = os.environ.copy()
        env[AKSHARE_WORKER_ENV] = "1"
        for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
            env.pop(key, None)
        completed = subprocess.run(
            [_worker_python_executable(), "-m", "app.services.akshare_worker", operation, *args],
            cwd=_api_root_path(),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
        )
        if completed.returncode != 0:
            detail = _clean_worker_error(completed.stderr) or _clean_worker_error(completed.stdout)
            raise RuntimeError(detail or f"akshare worker exited with code {completed.returncode}")
        output = completed.stdout.strip()
        if not output:
            raise RuntimeError("akshare worker returned no output")
        try:
            return json.loads(output)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"akshare worker returned invalid json: {exc}") from exc

    async def _fetch_yahoo_quote(self, symbol: str) -> QuoteSnapshot:
        data = await self._fetch_yahoo_chart(symbol, "1d", "5d")
        result = data["chart"]["result"][0]
        meta = result["meta"]
        price = float(meta.get("regularMarketPrice") or meta.get("previousClose") or 0)
        previous = float(meta.get("previousClose") or price)
        change = price - previous
        change_pct = change / previous * 100 if previous else 0
        market = infer_market(symbol)
        return QuoteSnapshot(
            symbol=symbol,
            name=display_name_for_symbol(symbol),
            market=market,
            price=round(price, 4),
            change=round(change, 4),
            change_pct=round(change_pct, 4),
            volume=float(meta.get("regularMarketVolume") or 0),
            turnover=float(meta.get("regularMarketVolume") or 0) * price,
            currency=meta.get("currency") or currency_for_market(market),
            source=YAHOO_SOURCE,
            as_of=datetime.now(UTC),
            delay_label=DELAY,
        )

    async def _fetch_tencent_quote(self, symbol: str) -> QuoteSnapshot:
        query_symbol = _tencent_symbol(symbol)
        async with httpx.AsyncClient(timeout=8, trust_env=False) as client:
            response = await client.get(f"https://qt.gtimg.cn/q={query_symbol}")
            response.raise_for_status()
        response.encoding = "gbk"
        quote = _parse_tencent_quote_line(symbol, response.text)
        if quote is None:
            raise RuntimeError(f"Tencent returned no quote for {symbol}")
        return quote

    async def _fetch_yahoo_candles(self, symbol: str, period: str, limit: int) -> list[CandleSnapshot]:
        interval = {"daily": "1d", "weekly": "1wk", "monthly": "1mo"}[period]
        range_value = {"daily": "1y", "weekly": "5y", "monthly": "10y"}[period]
        data = await self._fetch_yahoo_chart(symbol, interval, range_value)
        result = data["chart"]["result"][0]
        timestamps = result.get("timestamp") or []
        quote = result["indicators"]["quote"][0]
        candles: list[CandleSnapshot] = []
        for index, ts in enumerate(timestamps):
            values = {
                "open": _safe_float_at(quote.get("open", []), index),
                "high": _safe_float_at(quote.get("high", []), index),
                "low": _safe_float_at(quote.get("low", []), index),
                "close": _safe_float_at(quote.get("close", []), index),
                "volume": _safe_float_at(quote.get("volume", []), index),
            }
            if values["open"] <= 0 or values["high"] <= 0 or values["low"] <= 0 or values["close"] <= 0:
                continue
            candles.append(
                CandleSnapshot(
                    symbol=symbol,
                    date=datetime.fromtimestamp(int(ts), UTC).date().isoformat(),
                    source=YAHOO_SOURCE,
                    delay_label=DELAY,
                    **values,
                )
            )
        if not candles:
            raise RuntimeError("No candles returned")
        return candles[-limit:]

    async def _fetch_yahoo_chart(self, symbol: str, interval: str, range_value: str) -> dict:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol(symbol)}"
        async with httpx.AsyncClient(
            timeout=8,
            trust_env=False,
            headers={"User-Agent": "Mozilla/5.0 (compatible; ZhiTouTerminal/0.1)"},
        ) as client:
            response = await client.get(url, params={"interval": interval, "range": range_value})
            response.raise_for_status()
        data = response.json()
        if not data.get("chart", {}).get("result"):
            raise RuntimeError("Yahoo chart returned no result")
        return data

    def _sample_quote(self, symbol: str) -> QuoteSnapshot:
        market = infer_market(symbol)
        seed = sum(ord(char) for char in symbol)
        base = {"CN": 100, "HK": 80, "US": 160}[market]
        price = base + seed % 120
        change_pct = round(math.sin(seed) * 1.8, 4)
        change = round(price * change_pct / 100, 4)
        return QuoteSnapshot(
            symbol=symbol,
            name=display_name_for_symbol(symbol),
            market=market,
            price=round(price, 4),
            change=change,
            change_pct=change_pct,
            volume=seed * 1000,
            turnover=seed * price * 1000,
            currency=currency_for_market(market),
            source="sample fallback",
            as_of=datetime.now(UTC),
            delay_label="演示兜底数据，真实源不可用",
        )

    def _sample_candles(self, symbol: str, period: str, limit: int) -> list[CandleSnapshot]:
        quote = self._sample_quote(symbol)
        days = {"daily": 1, "weekly": 7, "monthly": 30}[period]
        close = quote.price
        candles: list[CandleSnapshot] = []
        for index in range(limit):
            date_value = datetime.now(UTC).date() - timedelta(days=(limit - index) * days)
            drift = math.sin(index / 3) * 0.012
            open_price = close
            close = max(1, close * (1 + drift))
            high = max(open_price, close) * 1.01
            low = min(open_price, close) * 0.99
            candles.append(
                CandleSnapshot(
                    symbol=symbol,
                    date=date_value.isoformat(),
                    open=round(open_price, 4),
                    high=round(high, 4),
                    low=round(low, 4),
                    close=round(close, 4),
                    volume=100000 + index * 1234,
                    source=quote.source,
                    delay_label=quote.delay_label,
                )
            )
        return candles


def _sentiment_from_quotes(quotes: list[QuoteSnapshot], advances: int, declines: int) -> float:
    quote_score = 50 + sum(item.change_pct for item in quotes) * 2
    breadth_total = max(1, advances + declines)
    breadth_score = advances / breadth_total * 100
    return round(max(0, min(100, quote_score * 0.6 + breadth_score * 0.4)), 2)


def _api_root_path() -> str:
    return str(Path(__file__).resolve().parents[2])


def _worker_python_executable() -> str:
    script_dir = "Scripts" if os.name == "nt" else "bin"
    executable = "python.exe" if os.name == "nt" else "python"
    venv_python = Path(sys.prefix) / script_dir / executable
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


def _clean_worker_error(value: str) -> str:
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    if not lines:
        return ""
    return " ".join(lines[:4])[:800]


def parse_cn_money(value: object) -> float:
    if value is None:
        return 0
    text = str(value).strip().replace(",", "")
    if not text or text in {"--", "-", "None", "nan"}:
        return 0
    multiplier = 1.0
    if text.endswith("亿"):
        multiplier = 100000000.0
        text = text[:-1]
    elif text.endswith("万"):
        multiplier = 10000.0
        text = text[:-1]
    if text.endswith("%"):
        text = text[:-1]
    try:
        return round(float(text) * multiplier, 4)
    except ValueError:
        return 0


def parse_pct(value: object) -> float:
    if value is None:
        return 0
    text = str(value).strip().replace(",", "")
    if not text or text in {"--", "-", "None", "nan"}:
        return 0
    if text.endswith("%"):
        text = text[:-1]
    try:
        return round(float(text), 4)
    except ValueError:
        return 0


def _dashboard_cache_status(statuses: list[DashboardSourceStatus]) -> DashboardCacheStatus:
    if not statuses:
        return "unavailable"
    core_statuses = [item for item in statuses if item.name not in DASHBOARD_OPTIONAL_STATUS_NAMES]
    evaluated_statuses = core_statuses or statuses
    if all(item.status == "live" for item in evaluated_statuses):
        return "live"
    if any(item.status == "stale" for item in evaluated_statuses):
        return "stale"
    if any(item.status == "live" for item in evaluated_statuses):
        return "partial"
    return "unavailable"


def _cached_status(name: str, cached: CachedSnapshot, detail: str) -> DashboardSourceStatus:
    return DashboardSourceStatus(
        name=name,
        status="stale",
        source=cached.source,
        detail=detail,
        as_of=cached.fetched_at,
    )


def _heat_items_from_rows(
    rows: list[Mapping[str, object]],
    source: str,
    limit: int,
) -> list[DashboardHeatItem]:
    items: list[DashboardHeatItem] = []
    for row in rows:
        name = str(_row_value(row, ("行业", "名称", "name")) or "").strip()
        if not name:
            continue
        change_pct = parse_pct(_row_value(row, ("行业-涨跌幅", "涨跌幅", "change_pct")))
        inflow = parse_cn_money(_row_value(row, ("流入资金", "main_inflow", "inflow")))
        outflow = parse_cn_money(_row_value(row, ("流出资金", "outflow")))
        net_amount = parse_cn_money(_row_value(row, ("净额", "主力净流入", "net_amount")))
        turnover = parse_cn_money(_row_value(row, ("成交额", "turnover")))
        if turnover <= 0:
            turnover = max(0, inflow + outflow)
        items.append(
            DashboardHeatItem(
                name=name,
                change_pct=change_pct,
                turnover=turnover,
                net_amount=net_amount,
                direction=_direction_for_pct(change_pct),
                source=source,
            )
        )
    return sorted(items, key=lambda item: abs(item.net_amount) or abs(item.change_pct), reverse=True)[:limit]


def _fund_flow_item_from_row(row: Mapping[str, object]) -> FundFlowItem:
    symbol = str(_row_value(row, ("股票代码", "symbol")) or "").strip()
    name = str(_row_value(row, ("股票简称", "名称", "name")) or "").strip()
    return FundFlowItem(
        symbol=symbol,
        name=name,
        change_pct=parse_pct(_row_value(row, ("涨跌幅", "change_pct"))),
        net_amount=parse_cn_money(_row_value(row, ("净额", "net_amount"))),
        turnover=parse_cn_money(_row_value(row, ("成交额", "turnover"))),
        source=THS_SOURCE,
    )


def _news_items_from_rows(rows: list[Mapping[str, object]], source: str) -> list[MarketNewsItem]:
    items: list[MarketNewsItem] = []
    for row in rows:
        title = _clean_text(_row_value(row, ("标题", "title")))
        content = _clean_text(_row_value(row, ("内容", "摘要", "summary", "digest", "新闻内容")))
        if not title and content:
            title = content[:48]
        if not title:
            continue
        items.append(
            MarketNewsItem(
                title=title,
                content=content,
                published_at=_parse_news_datetime(row),
                source=source,
                url=_clean_text(_row_value(row, ("链接", "url", "新闻链接"))),
            )
        )
    return sorted(
        items,
        key=lambda item: item.published_at or datetime.min.replace(tzinfo=UTC),
        reverse=True,
    )


def _model_news_prompt() -> str:
    shanghai_now = datetime.now(UTC) + timedelta(hours=8)
    return (
        "你是财经快讯编辑。请使用联网搜索获取最近24小时内与A股、港股、美股、央行、宏观、"
        "大宗商品、上市公司相关的中文财经快讯。严格只输出 JSON，不要 Markdown。\n"
        f"当前北京时间：{shanghai_now.strftime('%Y-%m-%d %H:%M:%S')}。\n"
        "输出结构：{\"items\":[{\"title\":\"不超过40字\","
        "\"content\":\"不超过120字，说明事实和市场相关性\","
        "\"published_at\":\"ISO 8601 时间，无法确认则为 null\","
        "\"source\":\"媒体或机构名\","
        "\"url\":\"可点击原文或搜索结果 URL\"}]}。\n"
        "要求：最多12条，按发布时间倒序；必须有可验证 URL；不要编造数据、观点或来源；"
        "不要输出投资建议。"
    )


def _responses_output_text(body: Mapping[str, object]) -> str:
    direct = body.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    chunks: list[str] = []
    output = body.get("output")
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, Mapping) or item.get("type") != "message":
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for part in content:
                if isinstance(part, Mapping) and isinstance(part.get("text"), str):
                    chunks.append(str(part["text"]))
    return "\n".join(chunks).strip()


def _json_object_from_text(text: str) -> dict[str, object]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end <= start:
        raise RuntimeError("model web search did not return a JSON object")
    try:
        value = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"model web search returned invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise RuntimeError("model web search JSON root is not an object")
    return value


def _model_news_items_from_payload(payload: Mapping[str, object]) -> list[MarketNewsItem]:
    rows = payload.get("items")
    if not isinstance(rows, list):
        raise RuntimeError("model web search JSON missing items")
    items: list[MarketNewsItem] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        title = _clean_text(row.get("title"))
        url = _clean_text(row.get("url"))
        if not title or not url:
            continue
        items.append(
            MarketNewsItem(
                title=title[:80],
                content=_clean_text(row.get("content"))[:180],
                published_at=_parse_optional_datetime(row.get("published_at")),
                source=_clean_text(row.get("source")) or MODEL_NEWS_SOURCE,
                url=url,
            )
        )
    if not items:
        raise RuntimeError("model web search returned no usable news items")
    return items


def _dedupe_news_items(items: list[MarketNewsItem]) -> list[MarketNewsItem]:
    seen: set[str] = set()
    output: list[MarketNewsItem] = []
    for item in sorted(
        items,
        key=lambda news: news.published_at or datetime.min.replace(tzinfo=UTC),
        reverse=True,
    ):
        key = item.url.strip() or item.title.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output


def _commodity_from_sge_rows(
    rows: list[Mapping[str, object]],
    symbol: str,
    name: str,
    unit: str,
) -> CommodityQuote | None:
    values = [_safe_float(_row_value(row, ("现价", "price"))) for row in rows]
    values = [value for value in values if value > 0]
    if not values:
        return None
    first = values[0]
    price = values[-1]
    change = price - first
    return CommodityQuote(
        symbol=symbol,
        name=name,
        price=round(price, 4),
        change=round(change, 4),
        change_pct=round(change / first * 100, 4) if first else 0,
        unit=unit,
        source="sge-spot",
        as_of=_parse_optional_datetime(_row_value(rows[-1], ("更新时间", "as_of"))) if rows else None,
        sparkline=[round(value, 4) for value in values[-24:]],
    )


def _commodities_from_global_futures(rows: list[Mapping[str, object]]) -> list[CommodityQuote]:
    wanted_names = ("黄金", "原油", "白银", "铜")
    wanted_codes = {"GC00Y", "CL00Y", "SI00Y", "HG00Y"}
    items: list[CommodityQuote] = []
    for row in rows:
        symbol = _clean_text(_row_value(row, ("代码", "symbol", "code")))
        name = _clean_text(_row_value(row, ("名称", "name")))
        if not symbol or not name:
            continue
        if symbol not in wanted_codes and not any(part in name for part in wanted_names):
            continue
        price = _safe_float(_row_value(row, ("最新价", "price", "现价")))
        if price <= 0:
            continue
        items.append(
            CommodityQuote(
                symbol=symbol,
                name=name,
                price=round(price, 4),
                change=round(_safe_float(_row_value(row, ("涨跌额", "change"))), 4),
                change_pct=round(_safe_float(_row_value(row, ("涨跌幅", "change_pct"))), 4),
                source="eastmoney-global-futures",
                as_of=datetime.now(UTC),
            )
        )
    return items[:4]


def _dragon_tiger_code_key(value: object) -> str:
    text = _clean_text(value).upper()
    if not text:
        return ""
    if "." in text:
        text = _plain_code(text)
    for prefix in ("SH", "SZ", "BJ", "HK"):
        text = text.removeprefix(prefix)
    return text


def _dragon_tiger_sector_from_row(row: Mapping[str, object]) -> str:
    return _clean_text(_row_value(row, DRAGON_TIGER_SECTOR_FIELDS))


def _dragon_tiger_market_segment(symbol: str) -> str:
    normalized = normalize_symbol(symbol, "CN")
    code = _plain_code(normalized)
    if normalized.endswith(".BJ"):
        return "北交所"
    if code.startswith(("688", "689")):
        return "科创板"
    if normalized.endswith(".SH"):
        return "沪主板"
    if normalized.endswith(".SZ"):
        if code.startswith("30"):
            return "创业板"
        return "深主板"
    if code:
        return "A股"
    return ""


def _dragon_tiger_item_from_row(row: Mapping[str, object]) -> DragonTigerItem | None:
    symbol = _clean_text(_row_value(row, ("代码", "股票代码", "symbol")))
    name = _clean_text(_row_value(row, ("名称", "股票名称", "name")))
    trade_date = _date_only_text(_row_value(row, ("上榜日", "上榜日期", "trade_date")))
    if not symbol or not name or not trade_date:
        return None
    return DragonTigerItem(
        symbol=symbol,
        name=name,
        trade_date=trade_date,
        close=_safe_float(_row_value(row, ("收盘价", "close"))),
        change_pct=parse_pct(_row_value(row, ("涨跌幅", "change_pct"))),
        turnover=parse_cn_money(_row_value(row, ("成交额", "成交金额", "成交金额(元)", "成交金额（元）", "turnover", "amount"))),
        sector=_dragon_tiger_sector_from_row(row),
        market_segment=_dragon_tiger_market_segment(symbol),
        net_amount=parse_cn_money(_row_value(row, ("龙虎榜净买额", "机构买入净额", "净额", "net_amount"))),
        buy_amount=parse_cn_money(_row_value(row, ("龙虎榜买入额", "买入金额", "buy_amount"))),
        sell_amount=parse_cn_money(_row_value(row, ("龙虎榜卖出额", "卖出金额", "sell_amount"))),
        reason=_clean_text(_row_value(row, ("上榜原因", "解读", "reason"))),
        source=LHB_SOURCE,
    )


def _parse_news_datetime(row: Mapping[str, object]) -> datetime | None:
    published = _parse_optional_datetime(_row_value(row, ("发布时间", "showTime", "time", "rtime")))
    if published is not None:
        return published
    date_text = _date_only_text(_row_value(row, ("发布日期", "日期", "date")))
    time_text = _clean_text(_row_value(row, ("发布时间", "时间", "time")))
    if date_text and time_text:
        return _parse_optional_datetime(f"{date_text} {time_text}")
    return None


def _date_only_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    text = str(value).strip()
    if not text:
        return ""
    if " " in text:
        text = text.split(" ", 1)[0]
    return text[:10]


def _clean_text(value: object) -> str:
    return str(value or "").strip()


def _direction_for_pct(value: float) -> str:
    if value > 0:
        return "up"
    if value < 0:
        return "down"
    return "flat"


def _parse_optional_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def _default_snapshot_cache_path() -> Path:
    return Path(__file__).resolve().parents[3] / ".runtime" / "market_cache.sqlite3"


def _plain_code(symbol: str) -> str:
    normalized = normalize_symbol(symbol, None)
    return normalized.removesuffix(".SH").removesuffix(".SZ").removesuffix(".BJ").removesuffix(".HK")


def _tencent_symbol(symbol: str) -> str:
    normalized = normalize_symbol(symbol, None)
    if normalized == "HSI.HK":
        return "hkHSI"
    if normalized == "HSCEI.HK":
        return "hkHSCEI"
    if normalized.endswith(".HK"):
        return "hk" + normalized.removesuffix(".HK")
    if normalized.endswith(".SH"):
        return "sh" + normalized.removesuffix(".SH")
    if normalized.endswith(".SZ"):
        return "sz" + normalized.removesuffix(".SZ")
    if normalized.endswith(".BJ"):
        return "bj" + normalized.removesuffix(".BJ")
    return normalized.lower()


def _parse_tencent_quote_line(symbol: str, text: str) -> QuoteSnapshot | None:
    payload = ""
    for line in text.split(";"):
        if '="' in line:
            payload = line.split('="', 1)[1].rstrip('"')
            break
    if not payload:
        return None
    fields = payload.split("~")
    if len(fields) < 33:
        return None
    market = infer_market(symbol)
    price = _safe_float(fields[3])
    if price <= 0:
        return None
    turnover = _safe_float(fields[37] if len(fields) > 37 else 0) * 1000
    return QuoteSnapshot(
        symbol=normalize_symbol(symbol, None),
        name=fields[1] or display_name_for_symbol(symbol),
        market=market,
        price=round(price, 4),
        change=round(_safe_float(fields[31]), 4),
        change_pct=round(_safe_float(fields[32]), 4),
        volume=_safe_float(fields[36] if len(fields) > 36 else fields[6]),
        turnover=turnover,
        currency=currency_for_market(market),
        source=TENCENT_SOURCE,
        as_of=_parse_tencent_time(fields[30]),
        delay_label=DELAY,
    )


def _parse_tencent_time(value: str) -> datetime:
    for fmt in ("%Y%m%d%H%M%S", "%Y/%m/%d %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return datetime.now(UTC)


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


def _records(table: object) -> list[Mapping[str, object]]:
    if hasattr(table, "to_dict"):
        raw_records = table.to_dict("records")
    else:
        raw_records = table
    if not isinstance(raw_records, Iterable):
        return []
    records: list[Mapping[str, object]] = []
    for row in raw_records:
        if isinstance(row, Mapping):
            records.append(row)
    return records


def _find_row_by_code(rows: list[Mapping[str, object]], code: str) -> Mapping[str, object] | None:
    candidates = {code, code.zfill(5)}
    for row in rows:
        row_code = str(_row_value(row, ("代码", "code", "symbol")) or "").strip().upper()
        if row_code in candidates or row_code.removeprefix("SH").removeprefix("SZ") in candidates:
            return row
    return None


def _row_value(row: Mapping[str, object], names: tuple[str, ...]) -> object:
    for name in names:
        if name in row:
            return row[name]
    return None


def _exchange_turnover_from_rows(rows: list[Mapping[str, object]]) -> float:
    total_candidates: list[float] = []
    a_share_candidates: list[float] = []
    turnover_row_candidates: list[float] = []
    for row in rows:
        label = _clean_text(_row_value(row, ("item", "项目", "指标", "name", "证券类别", "类别", "category")))
        turnover_value = _row_value(row, ("turnover", "amount", "成交金额", "成交额"))
        if turnover_value is not None:
            amount = _exchange_money_to_yuan(turnover_value, row)
            if amount > 0 and _is_total_stock_label(label):
                total_candidates.append(amount)
            elif amount > 0 and _is_a_share_label(label):
                a_share_candidates.append(amount)

        if _is_turnover_label(label):
            value = _row_value(row, ("stock", "股票", "A股", "a_share", "a shares", "合计", "value"))
            if value is None:
                value = _first_numeric_row_value(row)
            amount = _exchange_money_to_yuan(value, row)
            if amount > 0:
                turnover_row_candidates.append(amount)

    if total_candidates:
        return max(total_candidates)
    if a_share_candidates:
        return sum(a_share_candidates)
    if turnover_row_candidates:
        return max(turnover_row_candidates)
    return 0


def _exchange_money_to_yuan(value: object, row: Mapping[str, object]) -> float:
    if value is None:
        return 0
    text = str(value).strip()
    normalized = (
        text.replace(",", "")
        .replace("亿元", "亿")
        .replace("万元", "万")
        .replace("人民币", "")
        .replace("CNY", "")
        .replace("RMB", "")
        .replace("元", "")
        .strip()
    )
    amount = parse_cn_money(normalized)
    if amount == 0:
        return 0
    value_has_unit = any(token in text for token in ("亿", "万", "元", "CNY", "RMB", "人民币"))
    unit_text = " ".join(str(item) for key, item in row.items() if str(key).lower() in {"unit", "单位"})
    if not value_has_unit:
        unit_lower = unit_text.lower()
        if "100m" in unit_lower or "亿" in unit_text:
            amount *= 100000000
        elif "万" in unit_text:
            amount *= 10000
        elif 0 < abs(amount) < 10000000:
            amount *= 100000000
    return round(amount, 4)


def _first_numeric_row_value(row: Mapping[str, object]) -> object:
    skip_keys = {"item", "项目", "指标", "name", "证券类别", "类别", "category", "unit", "单位", "date", "日期"}
    for key, value in row.items():
        if str(key) in skip_keys:
            continue
        if parse_cn_money(value) != 0:
            return value
    return None


def _is_turnover_label(value: str) -> bool:
    text = value.lower()
    return "turnover" in text or "成交金额" in value or "成交额" in value


def _is_total_stock_label(value: str) -> bool:
    text = value.lower()
    return value in {"股票", "A股", "合计"} or "stock" in text or "a股" in text or "a share" in text


def _is_a_share_label(value: str) -> bool:
    text = value.lower()
    return "a股" in text or "a share" in text or "主板a" in text or "创业板" in value or "科创板" in value


def _latest_datetime_from_rows(rows: list[Mapping[str, object]]) -> datetime | None:
    values: list[datetime] = []
    for row in rows:
        for key in ("date", "日期", "交易日期", "统计日期", "as_of", "time", "更新时间"):
            parsed = _parse_optional_datetime(_row_value(row, (key,)))
            if parsed is not None:
                values.append(parsed)
    return max(values) if values else None


def _safe_float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0


def _safe_float_at(values: list[object], index: int) -> float:
    try:
        value = values[index]
        if value is None:
            return 0
        return round(float(value), 4)
    except (IndexError, TypeError, ValueError):
        return 0


def _history_days_for_period(period: str, limit: int) -> int:
    if period == "monthly":
        return max(limit * 45, 900)
    if period == "weekly":
        return max(limit * 10, 370)
    return max(limit * 4, 160)


def _candles_from_records(
    rows: list[Mapping[str, object]],
    symbol: str,
    source: str,
    delay_label: str,
) -> list[CandleSnapshot]:
    candles: list[CandleSnapshot] = []
    for row in rows:
        date_value = _row_value(row, ("日期", "date", "时间"))
        open_value = _safe_float(_row_value(row, ("开盘", "open")))
        high_value = _safe_float(_row_value(row, ("最高", "high")))
        low_value = _safe_float(_row_value(row, ("最低", "low")))
        close_value = _safe_float(_row_value(row, ("收盘", "close", "最新价")))
        if not date_value or open_value <= 0 or high_value <= 0 or low_value <= 0 or close_value <= 0:
            continue
        candles.append(
            CandleSnapshot(
                symbol=symbol,
                date=str(date_value)[:10],
                open=open_value,
                high=high_value,
                low=low_value,
                close=close_value,
                volume=_safe_float(_row_value(row, ("成交量", "volume", "amount"))),
                source=source,
                delay_label=delay_label,
            )
        )
    return sorted(candles, key=lambda item: item.date)


def _aggregate_candles(candles: list[CandleSnapshot], period: str) -> list[CandleSnapshot]:
    aggregated: list[CandleSnapshot] = []
    bucket: list[CandleSnapshot] = []
    current_key: tuple[int, int] | None = None
    for candle in sorted(candles, key=lambda item: item.date):
        key = _candle_period_key(candle, period)
        if key is None:
            continue
        if current_key is None:
            current_key = key
        if key != current_key and bucket:
            aggregated.append(_merge_candle_bucket(bucket))
            bucket = []
            current_key = key
        bucket.append(candle)
    if bucket:
        aggregated.append(_merge_candle_bucket(bucket))
    return aggregated


def _candle_period_key(candle: CandleSnapshot, period: str) -> tuple[int, int] | None:
    try:
        date_value = datetime.fromisoformat(candle.date[:10]).date()
    except ValueError:
        return None
    if period == "weekly":
        iso_year, iso_week, _ = date_value.isocalendar()
        return iso_year, iso_week
    return date_value.year, date_value.month


def _merge_candle_bucket(bucket: list[CandleSnapshot]) -> CandleSnapshot:
    first = bucket[0]
    last = bucket[-1]
    return CandleSnapshot(
        symbol=last.symbol,
        date=last.date,
        open=first.open,
        high=max(item.high for item in bucket),
        low=min(item.low for item in bucket),
        close=last.close,
        volume=sum(item.volume for item in bucket),
        source=last.source,
        delay_label=last.delay_label,
    )
