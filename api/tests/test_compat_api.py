from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.schemas.etfs import ETFQuoteItem, ETFSearchResponse
from app.schemas.macro import MacroDashboardResponse, MacroDataPoint, MacroSourceStatus
from app.schemas.market import (
    CandleSnapshot,
    MarketBreadth,
    MarketDashboardResponse,
    MarketOverviewItem,
    QuoteSnapshot,
    SymbolSearchResult,
)
from app.schemas.stocks import StockScreenerItem, StockScreenerResponse


class FakeMarketService:
    async def _fetch_quote_without_sample(self, symbol: str) -> QuoteSnapshot:
        if symbol == "000001.SH":
            name = "SSE Composite"
            price = 4110.81
            change_pct = 0.11
            source = "tencent-free-delayed"
        elif symbol == "399001.SZ":
            name = "SZSE Component"
            price = 15788.32
            change_pct = 0.21
            source = "tencent-free-delayed"
        elif symbol == "399006.SZ":
            name = "ChiNext"
            price = 3102.45
            change_pct = -0.31
            source = "tencent-free-delayed"
        elif symbol == "600519.SH":
            name = "Kweichow Moutai"
            price = 1520.5
            change_pct = 0.82
            source = "tencent-free-delayed"
        elif symbol == "300750.SZ":
            name = "CATL"
            price = 210.0
            change_pct = -1.2
            source = "sina-free-delayed"
        elif symbol == "300185.SZ":
            name = "Tongyu Heavy Industry"
            price = 2.56
            change_pct = 1.19
            source = "sina-free-delayed"
        else:
            raise RuntimeError(f"no quote for {symbol}")
        return QuoteSnapshot(
            symbol=symbol,
            name=name,
            market="CN",
            price=price,
            change=round(price * change_pct / 100, 4),
            change_pct=change_pct,
            volume=1000,
            turnover=price * 1000,
            currency="CNY",
            source=source,
            as_of=datetime(2026, 6, 24, 15, 0, tzinfo=UTC),
            delay_label="free delayed",
        )

    async def _fetch_primary_candles(self, symbol: str, period: str, limit: int) -> list[CandleSnapshot]:
        return [
            CandleSnapshot(
                symbol=symbol,
                date="2025-08-11",
                open=100,
                high=102,
                low=99,
                close=101,
                volume=1000,
                source="Yahoo Finance/free delayed fallback",
                delay_label="free delayed",
            ),
            CandleSnapshot(
                symbol=symbol,
                date="2025-08-12",
                open=101,
                high=103,
                low=100,
                close=102,
                volume=1100,
                source="Yahoo Finance/free delayed fallback",
                delay_label="free delayed",
            ),
        ]

    async def dashboard(self, markets: list[str], period: str) -> MarketDashboardResponse:
        quote = await self._fetch_quote_without_sample("000001.SH")
        return MarketDashboardResponse(
            as_of=datetime(2026, 6, 24, 15, 0, tzinfo=UTC),
            cache_status="live",
            source_status=[],
            primary_quote=quote,
            primary_candles=[],
            markets=[
                MarketOverviewItem(
                    market="CN",
                    label="A Share",
                    indices=[quote],
                    turnover=4110.81,
                    sentiment=55,
                    breadth=MarketBreadth(advances=1, declines=0, unchanged=0),
                    heatmap=[],
                    source=quote.source,
                    delay_label=quote.delay_label,
                    as_of=quote.as_of,
                )
            ],
            disclaimer="test",
        )


class FakeStockService:
    async def screen(self, **kwargs) -> StockScreenerResponse:
        return StockScreenerResponse(
            items=[
                StockScreenerItem(
                    symbol="600519.SH",
                    code="600519",
                    name="Kweichow Moutai",
                    exchange="SH",
                    price=1520.5,
                    change_pct=0.82,
                    turnover=987654321,
                    source="tencent-free-delayed",
                )
            ],
            source="symbol-pool+tencent-free-delayed",
            as_of=datetime(2026, 6, 24, 15, 0, tzinfo=UTC),
            status="live",
        )


class FakeETFService:
    async def search(self, q: str = "", limit: int = 50) -> ETFSearchResponse:
        return ETFSearchResponse(
            items=[
                ETFQuoteItem(
                    symbol="510300",
                    name="CSI 300 ETF",
                    price=4.12,
                    change_pct=0.42,
                    turnover=50800000,
                    volume=123456,
                    source="akshare-eastmoney-etf-spot",
                )
            ],
            source="akshare-eastmoney-etf-spot",
            as_of=datetime(2026, 6, 24, 15, 0, tzinfo=UTC),
            status="live",
        )


class FakeMacroService:
    async def dashboard(self) -> MacroDashboardResponse:
        point = MacroDataPoint(
            name="LPR 1Y",
            value=3.0,
            unit="%",
            as_of=datetime(2026, 6, 20, tzinfo=UTC),
            source="akshare.macro_china_lpr",
            status="live",
        )
        return MacroDashboardResponse(
            as_of=datetime(2026, 6, 24, 15, 0, tzinfo=UTC),
            cache_status="live",
            source_status=[
                MacroSourceStatus(
                    name="macro_china_lpr",
                    status="live",
                    source="akshare.macro_china_lpr",
                    as_of=datetime(2026, 6, 24, 15, 0, tzinfo=UTC),
                )
            ],
            rates=[point],
            indicators=[],
            bond_yields=[],
            fx_rates=[],
            disclaimer="test",
        )

    async def timeseries(self, **kwargs) -> dict:
        assert kwargs["series_ids"] == ["cn.money.m1_yoy"]
        return {
            "ts": datetime(2026, 6, 24, 15, 0, tzinfo=UTC),
            "start": "2026-01-01",
            "end": "2026-06-30",
            "series": [
                {
                    "series_id": "cn.money.m1_yoy",
                    "name": "M1 YoY",
                    "category": "money",
                    "frequency": "monthly",
                    "unit": "%",
                    "source": "akshare.macro_china_money_supply",
                    "status": "live",
                    "methodology": "test",
                    "is_derived": False,
                    "description": "",
                    "points": [{"date": "2026-05-01", "value": 4.8, "point_date": "2026-05-01", "release_date": None}],
                }
            ],
            "source_status": [
                {
                    "name": "macro_china_money_supply",
                    "status": "live",
                    "source": "akshare.macro_china_money_supply",
                    "detail": "",
                    "as_of": "2026-06-24T15:00:00Z",
                }
            ],
            "disclaimer": "test",
        }


class FakeMacroXrayService:
    async def xray(self, **kwargs) -> dict:
        assert kwargs["universe_code"] == "000300.SH"
        return {
            "ts": datetime(2026, 6, 24, 15, 0, tzinfo=UTC),
            "status": "live",
            "index": "000300.SH",
            "universe": {"type": "index", "code": "000300.SH", "name": "CSI 300", "scope": "non_financial"},
            "period": {"latest": "2026Q2", "quarters": 40, "lookback": 6},
            "sample": {"count": 300, "coverage": 1.0, "source": "public-proxy"},
            "latest": {
                "period": "2026Q2",
                "revenueYoy": 0.06,
                "profitYoy": 0.04,
                "inventoryYoy": 0.03,
                "cashConversionRatio": 0.82,
            },
            "points": [
                {
                    "period": "2026Q2",
                    "date": "2026-06-30",
                    "revenueYoy": 0.06,
                    "profitYoy": 0.04,
                    "inventoryYoy": 0.03,
                    "cashConversionRatio": 0.82,
                }
            ],
            "source_status": [],
            "insights": [],
            "diagnostics": [],
            "methodology": "public proxy",
        }

    async def targets(self, **kwargs) -> dict:
        return {
            "ts": datetime(2026, 6, 24, 15, 0, tzinfo=UTC),
            "status": "live",
            "items": [
                {
                    "id": "index:000300.SH",
                    "type": "index",
                    "code": "000300.SH",
                    "name": "CSI 300",
                    "source": "static-index-targets",
                    "status": "live",
                }
            ],
            "source_status": [],
            "methodology": "test",
        }


def make_client() -> TestClient:
    from app.routers.compat import router

    app = FastAPI()
    app.state.market_service = FakeMarketService()
    app.state.stock_screener_service = FakeStockService()
    app.state.etf_service = FakeETFService()
    app.state.macro_service = FakeMacroService()
    app.state.macro_xray_service = FakeMacroXrayService()
    app.include_router(router)
    return TestClient(app)


def test_quotes_compat_returns_realtime_index_group_without_sample_data() -> None:
    client = make_client()

    response = client.get("/api/quotes", params={"type": "realtime", "group": "indices-cn"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "live"
    assert body["items"][0]["symbol"] == "000001.SH"
    assert body["items"][0]["source"] == "tencent-free-delayed"
    assert all(item["source"] != "sample fallback" for item in body["items"])


def test_intraday_wrapper_is_explicitly_unavailable_instead_of_daily_proxy() -> None:
    client = make_client()

    response = client.get("/api/quotes", params={"type": "intraday", "group": "indices-cn"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "unavailable"
    assert body["source"] == "unavailable"
    assert body["series"][0]["items"] == []
    assert "intraday free source is not connected" in body["detail"]


def test_pricing_historical_resolves_requested_date_from_real_candles() -> None:
    client = make_client()

    response = client.get("/api/pricing/historical", params={"market": "CN", "date": "2025-08-12"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "live"
    assert body["date"] == "2025-08-12"
    assert body["items"][0]["date"] == "2025-08-12"
    assert body["items"][0]["close"] == 102


def test_time_machine_resolve_returns_requested_and_resolved_date() -> None:
    client = make_client()

    response = client.get("/api/time-machine/resolve", params={"date": "2025-08-12"})

    assert response.status_code == 200
    assert response.json()["resolved_date"] == "2025-08-12"


def test_stocks_v2_search_screener_compare_and_ranking_contracts(monkeypatch) -> None:
    client = make_client()

    def fail_pool(*args, **kwargs):
        raise RuntimeError("a-share pool should not be required for static hit")

    monkeypatch.setattr("app.services.symbols._a_share_pool", fail_pool)

    search_response = client.get("/api/stocks/v2/search", params={"q": "600519"})
    screener_response = client.get("/api/stocks/v2/screener/query", params={"query": "moutai"})
    compare_response = client.get("/api/stocks/v2/compare/query", params={"symbols": "600519.SH,300750.SZ"})
    ranking_response = client.get("/api/quotes/v2/stock-latest/ranking", params={"symbols": "600519.SH,300750.SZ"})

    assert search_response.status_code == 200
    assert any(item["symbol"] == "600519.SH" for item in search_response.json()["items"])
    assert screener_response.status_code == 200
    assert screener_response.json()["items"][0]["symbol"] == "600519.SH"
    assert compare_response.status_code == 200
    assert [item["symbol"] for item in compare_response.json()["items"]] == ["600519.SH", "300750.SZ"]
    assert ranking_response.status_code == 200
    assert ranking_response.json()["items"][0]["symbol"] == "600519.SH"


def test_quotes_compat_resolves_a_share_name_from_symbol_pool(monkeypatch) -> None:
    client = make_client()

    def fake_pool(*args, **kwargs) -> list[SymbolSearchResult]:
        return [
            SymbolSearchResult(
                symbol="300185.SZ",
                name="\u901a\u88d5\u91cd\u5de5",
                market="CN",
                currency="CNY",
                type="stock",
                source="test-symbol-pool",
                exchange="SZ",
            )
        ]

    monkeypatch.setattr("app.services.symbols._a_share_pool", fake_pool)

    response = client.get("/api/quotes", params={"type": "realtime", "symbols": "\u901a\u88d5\u91cd\u5de5"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "live"
    assert body["items"][0]["symbol"] == "300185.SZ"


def test_etf_catalog_and_macro_timeseries_wrappers() -> None:
    client = make_client()

    etf_response = client.get("/api/etfs/v1/catalog", params={"q": "300", "limit": 5})
    macro_response = client.get("/api/market/macro-timeseries")
    xray_response = client.get("/api/market/macro-xray")
    target_response = client.get("/api/market/macro-xray/targets")

    assert etf_response.status_code == 200
    assert etf_response.json()["items"][0]["symbol"] == "510300"
    assert macro_response.status_code == 200
    assert macro_response.json()["series"][0]["id"] == "rates"
    assert xray_response.status_code == 200
    assert xray_response.json()["status"] == "live"
    assert target_response.status_code == 200
    assert "index:000300.SH" in {item["id"] for item in target_response.json()["items"]}


def test_macro_timeseries_wrapper_accepts_series_ids_query() -> None:
    client = make_client()

    response = client.get(
        "/api/market/macro-timeseries",
        params={"series_ids": "cn.money.m1_yoy", "start": "2026-01-01", "end": "2026-06-30", "max_points": 10},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["series"][0]["series_id"] == "cn.money.m1_yoy"
    assert body["series"][0]["points"][0]["value"] == 4.8
    assert body["start"] == "2026-01-01"


def test_macro_xray_wrapper_returns_universe_points_and_targets() -> None:
    client = make_client()

    xray_response = client.get(
        "/api/market/macro-xray",
        params={"universe_type": "index", "universe_code": "000300.SH", "scope": "non_financial"},
    )
    targets_response = client.get("/api/market/macro-xray/targets", params={"universe_type": "index"})

    assert xray_response.status_code == 200
    assert xray_response.json()["universe"]["code"] == "000300.SH"
    assert xray_response.json()["points"][0]["revenueYoy"] == 0.06
    assert targets_response.status_code == 200
    assert targets_response.json()["items"][0]["id"] == "index:000300.SH"
