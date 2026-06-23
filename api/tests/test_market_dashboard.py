import time
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.main import create_app
from app.schemas.market import CandleSnapshot, QuoteSnapshot
from app.services.market import MarketDataService, parse_cn_money, parse_pct
from app.services.market_cache import MarketSnapshotCache


class FakeTable:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows

    def to_dict(self, orient: str) -> list[dict[str, object]]:
        assert orient == "records"
        return self.rows


class DashboardAkShare:
    def stock_market_activity_legu(self) -> FakeTable:
        return FakeTable(
            [
                {"item": "上涨", "value": 2600},
                {"item": "下跌", "value": 2300},
                {"item": "平盘", "value": 120},
                {"item": "涨停", "value": 88},
                {"item": "跌停", "value": 12},
                {"item": "活跃度", "value": "57.7%"},
                {"item": "统计日期", "value": "2026-06-23 15:00:00"},
            ]
        )

    def stock_sse_summary(self) -> FakeTable:
        return FakeTable([{"item": "turnover", "stock": 5000.25, "unit": "100m CNY", "date": "2026-06-23"}])

    def stock_szse_summary(self) -> FakeTable:
        return FakeTable([{"item": "turnover", "stock": 7300.75, "unit": "100m CNY", "date": "2026-06-23"}])

    def stock_fund_flow_industry(self, symbol: str = "即时") -> FakeTable:
        assert symbol == "即时"
        return FakeTable(
            [
                {"行业": "银行", "行业-涨跌幅": "1.12%", "流入资金": "120.5亿", "流出资金": "98.0亿", "净额": "22.5亿", "公司家数": 42},
                {"行业": "电子", "行业-涨跌幅": "-0.85%", "流入资金": "80.0亿", "流出资金": "91.3亿", "净额": "-11.3亿", "公司家数": 310},
            ]
        )

    def stock_fund_flow_concept(self, symbol: str = "即时") -> FakeTable:
        assert symbol == "即时"
        return FakeTable(
            [
                {"行业": "人工智能", "行业-涨跌幅": "2.35%", "流入资金": "210.0亿", "流出资金": "180.0亿", "净额": "30.0亿", "公司家数": 180},
                {"行业": "云计算", "行业-涨跌幅": "-0.85%", "流入资金": "44.0亿", "流出资金": "49.0亿", "净额": "-5.0亿", "公司家数": 96},
            ]
        )

    def stock_fund_flow_individual(self, symbol: str = "即时") -> FakeTable:
        assert symbol == "即时"
        return FakeTable(
            [
                {"股票代码": "600519", "股票简称": "贵州茅台", "涨跌幅": "1.20%", "净额": "3.46亿", "成交额": "40.2亿"},
                {"股票代码": "300750", "股票简称": "宁德时代", "涨跌幅": "-0.50%", "净额": "-2046.45万", "成交额": "32.0亿"},
            ]
        )

    def stock_sector_fund_flow_rank(self, indicator: str = "今日", sector_type: str = "地域资金流") -> FakeTable:
        assert indicator == "今日"
        assert sector_type == "地域资金流"
        return FakeTable(
            [
                {"名称": "上海", "涨跌幅": "0.92%", "主力净流入": "12.2亿", "成交额": "333.3亿"},
                {"名称": "湖北", "涨跌幅": "-0.58%", "主力净流入": "-4.8亿", "成交额": "121.0亿"},
            ]
        )

    def stock_info_global_cls(self, symbol: str = "全部") -> FakeTable:
        assert symbol == "全部"
        return FakeTable(
            [
                {"标题": "央行开展公开市场操作", "内容": "维护银行体系流动性合理充裕", "发布日期": "2026-06-23", "发布时间": "14:57"},
                {"标题": "半导体板块午后走强", "内容": "多只成分股涨幅居前", "发布日期": "2026-06-23", "发布时间": "14:38"},
            ]
        )

    def spot_quotations_sge(self, symbol: str = "Au99.99") -> FakeTable:
        if symbol == "Au99.99":
            return FakeTable(
                [
                    {"品种": "Au99.99", "时间": "14:55", "现价": 917.84, "更新时间": "2026-06-23 14:56:00"},
                    {"品种": "Au99.99", "时间": "14:56", "现价": 918.21, "更新时间": "2026-06-23 14:57:00"},
                ]
            )
        if symbol == "Ag(T+D)":
            return FakeTable(
                [
                    {"品种": "Ag(T+D)", "时间": "14:55", "现价": 16094.0, "更新时间": "2026-06-23 14:56:00"},
                    {"品种": "Ag(T+D)", "时间": "14:56", "现价": 16099.0, "更新时间": "2026-06-23 14:57:00"},
                ]
            )
        raise AssertionError(symbol)

    def futures_global_spot_em(self) -> FakeTable:
        return FakeTable(
            [
                {"代码": "GC00Y", "名称": "COMEX黄金", "最新价": 3377.2, "涨跌额": 12.3, "涨跌幅": 0.36, "成交量": 1200},
                {"代码": "CL00Y", "名称": "NYMEX原油", "最新价": 81.4, "涨跌额": -0.7, "涨跌幅": -0.85, "成交量": 980},
            ]
        )

    def stock_lhb_detail_em(self, start_date: str, end_date: str) -> FakeTable:
        assert len(start_date) == 8
        assert len(end_date) == 8
        return FakeTable(
            [
                {
                    "代码": "002765",
                    "名称": "蓝黛科技",
                    "上榜日": "2026-06-23",
                    "收盘价": 110.43,
                    "涨跌幅": 30.0,
                    "龙虎榜净买额": 220000000,
                    "龙虎榜买入额": 350000000,
                    "龙虎榜卖出额": 130000000,
                    "上榜原因": "日涨幅偏离值达7%",
                },
                {
                    "代码": "300770",
                    "名称": "新媒股份",
                    "上榜日": "2026-06-23",
                    "收盘价": 26.1,
                    "涨跌幅": 30.0,
                    "龙虎榜净买额": 120000000,
                    "龙虎榜买入额": 200000000,
                    "龙虎榜卖出额": 80000000,
                    "上榜原因": "日换手率达20%",
                },
                {
                    "代码": "600000",
                    "名称": "旧日期股票",
                    "上榜日": "2026-06-20",
                    "收盘价": 10.1,
                    "涨跌幅": 5.0,
                    "龙虎榜净买额": 999999999,
                    "龙虎榜买入额": 1000000000,
                    "龙虎榜卖出额": 1,
                    "上榜原因": "旧交易日",
                },
            ]
        )


class DashboardMarketService(MarketDataService):
    async def _fetch_primary_quote(self, symbol: str) -> QuoteSnapshot:
        market = "HK" if symbol.endswith(".HK") else "US" if symbol in {"DJI", "SPX", "NDX"} else "CN"
        currency = {"CN": "CNY", "HK": "HKD", "US": "USD"}[market]
        return QuoteSnapshot(
            symbol=symbol,
            name=f"Index {symbol}",
            market=market,
            price=3011.05,
            change=-18.6,
            change_pct=-0.61,
            volume=1000000,
            turnover=416310000000,
            currency=currency,
            source="test-real-quote",
            as_of=datetime(2026, 6, 23, 15, 0, tzinfo=UTC),
            delay_label="test delayed source",
        )

    async def _fetch_primary_candles(self, symbol: str, period: str, limit: int) -> list[CandleSnapshot]:
        return [
            CandleSnapshot(
                symbol=symbol,
                date=f"2026-06-{day:02d}",
                open=3000 + day,
                high=3020 + day,
                low=2980 + day,
                close=3010 + day,
                volume=100000 + day,
                source="test-real-candle",
                delay_label="test delayed source",
            )
            for day in range(1, min(limit, 20) + 1)
        ]


def test_parse_cn_money_and_pct_units() -> None:
    assert parse_cn_money("3.46亿") == 346000000
    assert parse_cn_money("-2046.45万") == -20464500
    assert parse_cn_money("1,234.56") == 1234.56
    assert parse_cn_money("--") == 0
    assert parse_pct("20.00%") == 20
    assert parse_pct(" -0.85% ") == -0.85
    assert parse_pct(None) == 0


def test_market_snapshot_cache_returns_live_and_stale_payload(tmp_path) -> None:
    cache = MarketSnapshotCache(tmp_path / "market_cache.sqlite3")
    cache.save("industry_heatmap", {"items": [{"name": "银行"}]}, "test-source", ttl_seconds=1)

    fresh = cache.get("industry_heatmap")
    assert fresh is not None
    assert fresh.is_stale is False
    assert fresh.payload["items"][0]["name"] == "银行"

    cache.save(
        "industry_heatmap",
        {"items": [{"name": "电子"}]},
        "test-source",
        ttl_seconds=1,
        fetched_at=datetime.now(UTC) - timedelta(seconds=3),
    )
    stale = cache.get("industry_heatmap")
    assert stale is not None
    assert stale.is_stale is True
    assert stale.payload["items"][0]["name"] == "电子"


async def test_cached_dashboard_source_times_out_and_uses_stale_cache(tmp_path) -> None:
    cache = MarketSnapshotCache(tmp_path / "market_cache.sqlite3")
    cache.save(
        "dashboard:slow_source",
        {"items": [{"name": "缓存板块"}]},
        "cached-source",
        ttl_seconds=1,
        fetched_at=datetime.now(UTC) - timedelta(minutes=5),
    )
    service = DashboardMarketService(
        cache_ttl_seconds=90,
        akshare_module=DashboardAkShare(),
        snapshot_cache=cache,
    )

    def slow_fetcher() -> list[dict[str, str]]:
        time.sleep(0.2)
        return [{"name": "慢源板块"}]

    result, status = await service._cached_dashboard_source(
        key="dashboard:slow_source",
        name="slow_source",
        source="slow-test-source",
        ttl_seconds=1,
        fetcher=slow_fetcher,
        serializer=lambda items: {"items": items},
        deserializer=lambda payload: payload["items"],
        empty_value=[],
        timeout_seconds=0.01,
    )

    assert result == [{"name": "缓存板块"}]
    assert status.status == "stale"
    assert "timed out" in status.detail


async def test_cached_dashboard_source_uses_fresh_cache_without_fetching(tmp_path) -> None:
    cache = MarketSnapshotCache(tmp_path / "market_cache.sqlite3")
    cache.save(
        "dashboard:fresh_source",
        {"items": [{"name": "新鲜缓存"}]},
        "cached-source",
        ttl_seconds=60,
    )
    service = DashboardMarketService(
        cache_ttl_seconds=90,
        akshare_module=DashboardAkShare(),
        snapshot_cache=cache,
    )
    called = False

    def fetcher() -> list[dict[str, str]]:
        nonlocal called
        called = True
        raise RuntimeError("fresh cache should be used")

    result, status = await service._cached_dashboard_source(
        key="dashboard:fresh_source",
        name="fresh_source",
        source="slow-test-source",
        ttl_seconds=60,
        fetcher=fetcher,
        serializer=lambda items: {"items": items},
        deserializer=lambda payload: payload["items"],
        empty_value=[],
        timeout_seconds=0.01,
    )

    assert called is False
    assert result == [{"name": "新鲜缓存"}]
    assert status.status == "live"
    assert "fresh SQLite cache" in status.detail


async def test_cached_dashboard_source_skips_recent_failure_without_cache(tmp_path) -> None:
    service = DashboardMarketService(
        cache_ttl_seconds=90,
        akshare_module=DashboardAkShare(),
        snapshot_cache=MarketSnapshotCache(tmp_path / "market_cache.sqlite3"),
    )
    service._dashboard_failure_cache["dashboard:down_source"] = (time.time(), "source down")
    called = False

    def fetcher() -> list[dict[str, str]]:
        nonlocal called
        called = True
        return [{"name": "should-not-fetch"}]

    result, status = await service._cached_dashboard_source(
        key="dashboard:down_source",
        name="down_source",
        source="down-test-source",
        ttl_seconds=60,
        fetcher=fetcher,
        serializer=lambda items: {"items": items},
        deserializer=lambda payload: payload["items"],
        empty_value=[],
        timeout_seconds=0.01,
    )

    assert called is False
    assert result == []
    assert status.status == "unavailable"
    assert "recent source failure" in status.detail


def test_dashboard_heatmap_runs_in_worker_without_injected_module(monkeypatch) -> None:
    service = MarketDataService()
    calls: list[tuple[str, tuple[str, ...]]] = []

    def fake_worker(operation: str, *args: str, timeout_seconds: float = 5.0):
        calls.append((operation, args))
        return [
            {
                "name": "银行",
                "change_pct": 1.12,
                "turnover": 4200000000,
                "net_amount": 2250000000,
                "direction": "up",
                "source": "worker-akshare",
            }
        ]

    monkeypatch.setattr(service, "_run_akshare_worker_sync", fake_worker)

    items = service._fetch_fund_flow_heatmap_sync("industry")

    assert calls == [("industry_heatmap", ())]
    assert items[0].name == "银行"
    assert items[0].source == "worker-akshare"


async def test_dashboard_uses_real_sources_and_reports_cache_status(tmp_path) -> None:
    service = DashboardMarketService(
        cache_ttl_seconds=90,
        akshare_module=DashboardAkShare(),
        snapshot_cache=MarketSnapshotCache(tmp_path / "market_cache.sqlite3"),
    )

    dashboard = await service.dashboard(["CN", "HK", "US"], "daily")

    assert [market.market for market in dashboard.markets] == ["CN", "HK", "US"]
    assert dashboard.cache_status == "live"
    assert dashboard.primary_quote is not None
    assert dashboard.primary_candles
    assert dashboard.a_share_activity is not None
    assert dashboard.a_share_activity.advances == 2600
    assert dashboard.a_share_activity.sentiment == 57.7
    assert dashboard.a_share_turnover is not None
    assert dashboard.a_share_turnover.value == 1230100000000
    assert dashboard.a_share_turnover.unit == "CNY"
    assert dashboard.markets[0].turnover == 12301.0
    assert dashboard.industry_heatmap[0].name == "银行"
    assert dashboard.industry_heatmap[0].net_amount == 2250000000
    assert dashboard.concept_heatmap[0].name == "人工智能"
    assert dashboard.region_heatmap[0].name == "上海"
    assert dashboard.fund_flow_summary is not None
    assert dashboard.fund_flow_summary.top_inflows[0].name == "贵州茅台"
    assert dashboard.market_news[0].title == "央行开展公开市场操作"
    assert dashboard.commodity_quotes[0].name == "黄金连续"
    assert dashboard.commodity_quotes[0].sparkline
    assert dashboard.dragon_tiger[0].name == "蓝黛科技"
    assert dashboard.index_sparklines["000001.SH"][0] > 0
    assert all(status.status == "live" for status in dashboard.source_status)
    assert {quote.source for market in dashboard.markets for quote in market.indices} == {"test-real-quote"}


async def test_dashboard_uses_stale_cache_when_source_fails(tmp_path) -> None:
    class FailingAkShare(DashboardAkShare):
        def stock_fund_flow_industry(self, symbol: str = "即时") -> FakeTable:
            raise RuntimeError("source down")

    cache = MarketSnapshotCache(tmp_path / "market_cache.sqlite3")
    cache.save(
        "dashboard:industry_heatmap",
        {
            "items": [
                {
                    "name": "缓存行业",
                    "change_pct": 1.5,
                    "turnover": 10,
                    "net_amount": 100000000,
                    "direction": "up",
                    "source": "cached-source",
                }
            ]
        },
        "cached-source",
        ttl_seconds=1,
        fetched_at=datetime.now(UTC) - timedelta(minutes=10),
    )
    service = DashboardMarketService(
        cache_ttl_seconds=90,
        akshare_module=FailingAkShare(),
        snapshot_cache=cache,
    )

    dashboard = await service.dashboard(["CN"], "daily")

    assert dashboard.cache_status == "stale"
    assert dashboard.industry_heatmap[0].name == "缓存行业"
    industry_status = next(item for item in dashboard.source_status if item.name == "industry_heatmap")
    assert industry_status.status == "stale"
    assert "source down" in industry_status.detail


async def test_dashboard_reports_unavailable_without_fake_data(tmp_path) -> None:
    class FailingAkShare:
        def stock_market_activity_legu(self) -> FakeTable:
            raise RuntimeError("activity down")

        def stock_fund_flow_industry(self, symbol: str = "即时") -> FakeTable:
            raise RuntimeError("industry down")

        def stock_fund_flow_concept(self, symbol: str = "即时") -> FakeTable:
            raise RuntimeError("concept down")

        def stock_fund_flow_individual(self, symbol: str = "即时") -> FakeTable:
            raise RuntimeError("individual down")

        def stock_sector_fund_flow_rank(self, indicator: str = "今日", sector_type: str = "地域资金流") -> FakeTable:
            raise RuntimeError("region down")

        def stock_info_global_cls(self, symbol: str = "全部") -> FakeTable:
            raise RuntimeError("news down")

        def stock_info_global_em(self) -> FakeTable:
            raise RuntimeError("news em down")

        def stock_info_global_ths(self) -> FakeTable:
            raise RuntimeError("news ths down")

        def spot_quotations_sge(self, symbol: str = "Au99.99") -> FakeTable:
            raise RuntimeError("commodity down")

        def futures_global_spot_em(self) -> FakeTable:
            raise RuntimeError("global commodity down")

        def stock_lhb_detail_em(self, start_date: str, end_date: str) -> FakeTable:
            raise RuntimeError("lhb down")

    service = DashboardMarketService(
        cache_ttl_seconds=90,
        akshare_module=FailingAkShare(),
        snapshot_cache=MarketSnapshotCache(tmp_path / "market_cache.sqlite3"),
    )

    dashboard = await service.dashboard(["CN"], "daily")

    assert dashboard.cache_status == "partial"
    assert dashboard.a_share_activity is None
    assert dashboard.fund_flow_summary is None
    assert dashboard.industry_heatmap == []
    assert dashboard.concept_heatmap == []
    assert dashboard.region_heatmap == []
    assert dashboard.market_news == []
    assert dashboard.commodity_quotes == []
    assert dashboard.dragon_tiger == []
    assert any(status.status == "unavailable" for status in dashboard.source_status)
    assert dashboard.a_share_turnover is None


def test_dashboard_endpoint_returns_stable_contract(tmp_path) -> None:
    app = create_app()
    app.state.market_service = DashboardMarketService(
        cache_ttl_seconds=90,
        akshare_module=DashboardAkShare(),
        snapshot_cache=MarketSnapshotCache(tmp_path / "market_cache.sqlite3"),
    )
    client = TestClient(app)

    response = client.get("/api/market/dashboard?markets=CN,HK,US&period=daily")

    assert response.status_code == 200
    body = response.json()
    assert body["cache_status"] == "live"
    assert [market["market"] for market in body["markets"]] == ["CN", "HK", "US"]
    assert body["primary_quote"]["symbol"] == "000001.SH"
    assert body["primary_candles"]
    assert body["a_share_activity"]["advances"] == 2600
    assert body["a_share_turnover"]["value"] == 1230100000000
    assert body["markets"][0]["turnover"] == 12301.0
    assert body["industry_heatmap"][0]["name"] == "银行"
    assert body["market_news"][0]["title"] == "央行开展公开市场操作"
    assert body["commodity_quotes"][0]["name"] == "黄金连续"
    assert body["dragon_tiger"][0]["name"] == "蓝黛科技"
    assert body["index_sparklines"]["000001.SH"]
