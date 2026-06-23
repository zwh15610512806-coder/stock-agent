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
    assert dashboard.industry_heatmap[0].name == "银行"
    assert dashboard.industry_heatmap[0].net_amount == 2250000000
    assert dashboard.concept_heatmap[0].name == "人工智能"
    assert dashboard.region_heatmap[0].name == "上海"
    assert dashboard.fund_flow_summary is not None
    assert dashboard.fund_flow_summary.top_inflows[0].name == "贵州茅台"
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
    assert any(status.status == "unavailable" for status in dashboard.source_status)


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
    assert body["industry_heatmap"][0]["name"] == "银行"
