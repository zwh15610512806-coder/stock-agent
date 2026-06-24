from fastapi import FastAPI
from fastapi.testclient import TestClient
from types import SimpleNamespace

from app.routers.stocks import router
from app.services.stocks import StockScreenerService


class FakeTable:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows

    def to_dict(self, orient: str) -> list[dict[str, object]]:
        assert orient == "records"
        return self.rows


class ScreenerAkShare:
    def __init__(self) -> None:
        self.calls = 0

    def stock_zh_a_spot_em(self) -> FakeTable:
        self.calls += 1
        return FakeTable(
            [
                {
                    "code": "600519",
                    "name": "贵州茅台",
                    "latest_price": 1200.5,
                    "change_pct": 1.2,
                    "turnover": 50_000_000_000,
                    "market_cap": 2_100_000_000_000,
                    "pe": 25.0,
                    "pb": 8.0,
                },
                {
                    "代码": "601318",
                    "名称": "中国平安",
                    "最新价": 48.2,
                    "涨跌幅": "-0.4%",
                    "成交额": "300亿",
                    "总市值": "8800亿",
                    "市盈率-动态": 9.5,
                    "市净率": 0.9,
                },
                {
                    "code": "300750",
                    "name": "宁德时代",
                    "latest_price": 210,
                    "change_pct": 5.3,
                    "turnover": 30_000_000_000,
                    "market_cap": 900_000_000_000,
                    "pe": 28,
                    "pb": 1.8,
                },
                {
                    "code": "000001",
                    "name": "平安银行",
                    "latest_price": 10.2,
                    "change_pct": -0.2,
                    "turnover": 2_000_000_000,
                    "market_cap": 190_000_000_000,
                    "pe": 5.2,
                    "pb": 0.55,
                },
                {
                    "code": "600000",
                    "name": "浦发银行",
                    "latest_price": 8.4,
                    "change_pct": 0.1,
                    "turnover": 35_000_000_000,
                    "market_cap": 260_000_000_000,
                    "pb": 0.45,
                },
            ]
        )


class FailingScreenerAkShare:
    def stock_zh_a_spot_em(self) -> FakeTable:
        raise RuntimeError("eastmoney disconnected")

    def stock_info_a_code_name(self) -> FakeTable:
        return FakeTable([{"code": "600519", "name": "贵州茅台"}])


class QuoteFallbackService:
    async def quote(self, symbol: str) -> SimpleNamespace:
        assert symbol == "600519.SH"
        return SimpleNamespace(
            symbol=symbol,
            price=1520.5,
            change_pct=0.82,
            turnover=987654321,
            volume=123456,
            source="tencent-free-delayed",
            as_of="2026-06-24T15:00:00Z",
        )


async def test_screener_filters_a_share_rows_from_one_spot_table() -> None:
    fake_akshare = ScreenerAkShare()
    service = StockScreenerService(akshare_module=fake_akshare)

    response = await service.screen(
        query="平安",
        min_change_pct=-1,
        max_change_pct=2,
        min_turnover=20_000_000_000,
        min_market_cap=500_000_000_000,
        max_pe=12,
        max_pb=1,
        limit=10,
    )

    assert response.status == "live"
    assert response.source == "akshare-eastmoney-a-share-spot"
    assert [item.symbol for item in response.items] == ["601318.SH"]
    assert response.items[0].turnover == 30_000_000_000
    assert response.items[0].pe == 9.5
    assert response.items[0].pb == 0.9
    assert fake_akshare.calls == 1


async def test_screener_falls_back_to_symbol_pool_and_quotes_for_keyword_query() -> None:
    service = StockScreenerService(
        akshare_module=FailingScreenerAkShare(),
        market_service=QuoteFallbackService(),
    )

    response = await service.screen(query="茅台", limit=5)

    assert response.status == "live"
    assert response.source == "symbol-pool+tencent-free-delayed"
    assert "eastmoney disconnected" in response.detail
    assert len(response.items) == 1
    assert response.items[0].symbol == "600519.SH"
    assert response.items[0].name == "贵州茅台"
    assert response.items[0].price == 1520.5
    assert response.items[0].change_pct == 0.82
    assert response.items[0].pe is None


def test_screener_endpoint_returns_contract_without_main_registration() -> None:
    app = FastAPI()
    fake_akshare = ScreenerAkShare()
    app.state.stock_screener_service = StockScreenerService(akshare_module=fake_akshare)
    app.include_router(router)
    client = TestClient(app)

    response = client.get(
        "/api/stocks/screener",
        params={
            "query": "平安",
            "min_change_pct": -1,
            "max_change_pct": 2,
            "min_turnover": 20_000_000_000,
            "min_market_cap": 500_000_000_000,
            "max_pe": 12,
            "max_pb": 1,
            "limit": 10,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "live"
    assert body["items"][0]["symbol"] == "601318.SH"
    assert fake_akshare.calls == 1
