import asyncio
import os
import importlib
import math
import time
from collections.abc import Callable, Iterable, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, TypeVar

import httpx

from app.schemas.market import (
    AShareActivity,
    CandleSnapshot,
    DashboardCacheStatus,
    DashboardHeatItem,
    DashboardSourceStatus,
    FundFlowItem,
    FundFlowSummary,
    MarketBreadth,
    MarketCode,
    MarketDashboardResponse,
    MarketHeatItem,
    MarketOverviewItem,
    QuoteSnapshot,
    SymbolSearchResult,
)
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
SNAPSHOT_TTL_SECONDS = 10 * 60
SLOW_SNAPSHOT_TTL_SECONDS = 30 * 60
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
    ) -> None:
        self.cache_ttl_seconds = cache_ttl_seconds
        self.akshare_module = akshare_module
        self.snapshot_cache = snapshot_cache or MarketSnapshotCache(_default_snapshot_cache_path())
        self._quote_cache: dict[str, tuple[float, QuoteSnapshot]] = {}
        self._candle_cache: dict[tuple[str, str, int], tuple[float, list[CandleSnapshot]]] = {}

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
        source_status: list[DashboardSourceStatus] = []

        primary_quote, primary_quote_status = await self._fetch_dashboard_quote("000001.SH")
        source_status.append(primary_quote_status)
        primary_candles, primary_candles_status = await self._fetch_dashboard_candles(
            "000001.SH",
            normalized_period,
            120,
        )
        source_status.append(primary_candles_status)

        activity, activity_status = await self._cached_dashboard_source(
            key="dashboard:a_share_activity",
            name="a_share_activity",
            source=LEGU_SOURCE,
            ttl_seconds=SNAPSHOT_TTL_SECONDS,
            fetcher=self._fetch_a_share_activity_sync,
            serializer=lambda item: item.model_dump(mode="json"),
            deserializer=lambda payload: AShareActivity.model_validate(payload),
            empty_value=None,
        )
        source_status.append(activity_status)

        industry_heatmap, industry_status = await self._cached_dashboard_source(
            key="dashboard:industry_heatmap",
            name="industry_heatmap",
            source=THS_SOURCE,
            ttl_seconds=SNAPSHOT_TTL_SECONDS,
            fetcher=lambda: self._fetch_fund_flow_heatmap_sync("industry"),
            serializer=lambda items: {"items": [item.model_dump(mode="json") for item in items]},
            deserializer=lambda payload: [DashboardHeatItem.model_validate(item) for item in payload.get("items", [])],
            empty_value=[],
        )
        source_status.append(industry_status)

        concept_heatmap, concept_status = await self._cached_dashboard_source(
            key="dashboard:concept_heatmap",
            name="concept_heatmap",
            source=THS_SOURCE,
            ttl_seconds=SNAPSHOT_TTL_SECONDS,
            fetcher=lambda: self._fetch_fund_flow_heatmap_sync("concept"),
            serializer=lambda items: {"items": [item.model_dump(mode="json") for item in items]},
            deserializer=lambda payload: [DashboardHeatItem.model_validate(item) for item in payload.get("items", [])],
            empty_value=[],
        )
        source_status.append(concept_status)

        region_heatmap, region_status = await self._cached_dashboard_source(
            key="dashboard:region_heatmap",
            name="region_heatmap",
            source=EASTMONEY_SOURCE,
            ttl_seconds=SNAPSHOT_TTL_SECONDS,
            fetcher=self._fetch_region_heatmap_sync,
            serializer=lambda items: {"items": [item.model_dump(mode="json") for item in items]},
            deserializer=lambda payload: [DashboardHeatItem.model_validate(item) for item in payload.get("items", [])],
            empty_value=[],
        )
        source_status.append(region_status)

        fund_flow_summary, fund_status = await self._cached_dashboard_source(
            key="dashboard:fund_flow_summary",
            name="fund_flow_summary",
            source=THS_SOURCE,
            ttl_seconds=SLOW_SNAPSHOT_TTL_SECONDS,
            fetcher=self._fetch_fund_flow_summary_sync,
            serializer=lambda item: item.model_dump(mode="json"),
            deserializer=lambda payload: FundFlowSummary.model_validate(payload),
            empty_value=None,
        )
        source_status.append(fund_status)

        market_items, market_status = await self._dashboard_markets(normalized_markets, activity)
        source_status.append(market_status)

        return MarketDashboardResponse(
            as_of=datetime.now(UTC),
            cache_status=_dashboard_cache_status(source_status),
            source_status=source_status,
            primary_quote=primary_quote,
            primary_candles=primary_candles,
            markets=market_items,
            a_share_activity=activity,
            fund_flow_summary=fund_flow_summary,
            industry_heatmap=industry_heatmap,
            concept_heatmap=concept_heatmap,
            region_heatmap=region_heatmap,
            disclaimer="免费公开源可能延迟、缺失或被缓存；缓存数据会在来源状态中标记。",
        )

    async def _fetch_dashboard_quote(self, symbol: str) -> tuple[QuoteSnapshot | None, DashboardSourceStatus]:
        try:
            quote = await self._fetch_quote_without_sample(symbol)
            return quote, DashboardSourceStatus(name="primary_quote", status="live", source=quote.source, as_of=quote.as_of)
        except Exception as exc:
            return None, DashboardSourceStatus(
                name="primary_quote",
                status="unavailable",
                source="market-quote",
                detail=str(exc),
            )

    async def _fetch_dashboard_candles(
        self,
        symbol: str,
        period: str,
        limit: int,
    ) -> tuple[list[CandleSnapshot], DashboardSourceStatus]:
        try:
            candles = await self._fetch_primary_candles(normalize_symbol(symbol, None), period, limit)
            source = candles[-1].source if candles else "market-candles"
            if source == "sample fallback":
                raise RuntimeError(f"sample candles rejected for dashboard: {symbol}")
            return candles, DashboardSourceStatus(name="primary_candles", status="live", source=source)
        except Exception as exc:
            return [], DashboardSourceStatus(
                name="primary_candles",
                status="unavailable",
                source="market-candles",
                detail=str(exc),
            )

    async def _dashboard_markets(
        self,
        markets: list[MarketCode],
        activity: AShareActivity | None,
    ) -> tuple[list[MarketOverviewItem], DashboardSourceStatus]:
        statuses: list[str] = []

        async def build_market(market: MarketCode) -> MarketOverviewItem:
            quotes = await asyncio.gather(
                *(self._fetch_quote_without_sample(symbol) for symbol, _ in INDEX_SYMBOLS[market]),
                return_exceptions=True,
            )
            live_quotes = [quote for quote in quotes if isinstance(quote, QuoteSnapshot)]
            statuses.extend("live" if isinstance(quote, QuoteSnapshot) else "unavailable" for quote in quotes)
            advances = activity.advances if market == "CN" and activity else sum(1 for quote in live_quotes if quote.change_pct > 0)
            declines = activity.declines if market == "CN" and activity else sum(1 for quote in live_quotes if quote.change_pct < 0)
            unchanged = activity.unchanged if market == "CN" and activity else max(0, len(live_quotes) - advances - declines)
            sentiment = activity.sentiment if market == "CN" and activity else _sentiment_from_quotes(live_quotes, advances, declines)
            return MarketOverviewItem(
                market=market,
                label={"CN": "A股", "HK": "港股", "US": "美股"}[market],
                indices=live_quotes,
                turnover=round(sum(item.turnover for item in live_quotes) / 100000000, 2),
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
    ) -> tuple[T, DashboardSourceStatus]:
        try:
            result = await asyncio.to_thread(fetcher)
            self.snapshot_cache.save(key, serializer(result), source, ttl_seconds)
            return result, DashboardSourceStatus(name=name, status="live", source=source, as_of=datetime.now(UTC))
        except Exception as exc:
            cached = self.snapshot_cache.get(key)
            if cached is not None:
                return deserializer(cached.payload), _cached_status(name, cached, str(exc))
            return empty_value, DashboardSourceStatus(name=name, status="unavailable", source=source, detail=str(exc))

    def _fetch_a_share_activity_sync(self) -> AShareActivity:
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

    def _fetch_fund_flow_heatmap_sync(self, kind: str) -> list[DashboardHeatItem]:
        with _without_proxy_env():
            akshare = self._akshare()
            if kind == "industry":
                rows = _records(akshare.stock_fund_flow_industry(symbol="即时"))
            elif kind == "concept":
                rows = _records(akshare.stock_fund_flow_concept(symbol="即时"))
            else:
                raise ValueError(f"Unsupported heatmap kind: {kind}")
        return _heat_items_from_rows(rows, THS_SOURCE, limit=12)

    def _fetch_region_heatmap_sync(self) -> list[DashboardHeatItem]:
        with _without_proxy_env():
            rows = _records(
                self._akshare().stock_sector_fund_flow_rank(
                    indicator="今日",
                    sector_type="地域资金流",
                )
            )
        return _heat_items_from_rows(rows, EASTMONEY_SOURCE, limit=12)

    def _fetch_fund_flow_summary_sync(self) -> FundFlowSummary:
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
    if all(item.status == "live" for item in statuses):
        return "live"
    if any(item.status == "stale" for item in statuses):
        return "stale"
    if any(item.status == "live" for item in statuses):
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


def _direction_for_pct(value: float) -> str:
    if value > 0:
        return "up"
    if value < 0:
        return "down"
    return "flat"


def _parse_optional_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
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
