from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.etfs import router
from app.services.etfs import ETFService


class FakeTable:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows

    def to_dict(self, orient: str) -> list[dict[str, object]]:
        assert orient == "records"
        return self.rows


class ETFAkShare:
    def __init__(self) -> None:
        self.spot_calls = 0
        self.hist_calls: list[tuple[str, str]] = []

    def fund_etf_spot_em(self) -> FakeTable:
        self.spot_calls += 1
        return FakeTable(
            [
                {
                    "代码": "510300",
                    "名称": "沪深300ETF",
                    "最新价": 4.12,
                    "涨跌幅": "0.73%",
                    "成交额": "12.5亿",
                    "成交量": 3000000,
                },
                {
                    "symbol": "159915",
                    "name": "创业板ETF",
                    "price": 2.22,
                    "change_pct": -0.2,
                    "turnover": 500_000_000,
                    "volume": 800000,
                },
            ]
        )

    def fund_etf_hist_em(self, symbol: str, period: str = "daily", adjust: str = "") -> FakeTable:
        self.hist_calls.append((symbol, period))
        return FakeTable(
            [
                {"日期": "2026-06-22", "开盘": 4.01, "最高": 4.08, "最低": 4.0, "收盘": 4.06, "成交量": 1000, "成交额": 4060},
                {"date": "2026-06-23", "open": 4.06, "high": 4.14, "low": 4.05, "close": 4.12, "volume": 1200, "turnover": 4944},
            ]
        )


class FailingETFAkShare:
    def fund_etf_spot_em(self) -> FakeTable:
        raise RuntimeError("spot source down")

    def fund_etf_hist_em(self, symbol: str, period: str = "daily", adjust: str = "") -> FakeTable:
        raise RuntimeError("hist source down")


class SinaFallbackETFAkShare:
    def __init__(self) -> None:
        self.sina_calls: list[str] = []

    def fund_etf_spot_em(self) -> FakeTable:
        return FakeTable([])

    def fund_etf_hist_em(self, symbol: str, period: str = "daily", adjust: str = "") -> FakeTable:
        raise RuntimeError("eastmoney hist disconnected")

    def fund_etf_hist_sina(self, symbol: str) -> FakeTable:
        self.sina_calls.append(symbol)
        return FakeTable(
            [
                {"date": "2026-06-23", "open": 5.08, "high": 5.1, "low": 4.91, "close": 4.94, "volume": 1000, "amount": 4940},
            ]
        )


async def test_etf_search_returns_live_items_from_spot_table() -> None:
    fake_akshare = ETFAkShare()
    service = ETFService(akshare_module=fake_akshare)

    response = await service.search("沪深", limit=5)

    assert response.status == "live"
    assert response.source == "akshare-eastmoney-etf-spot"
    assert [item.symbol for item in response.items] == ["510300"]
    assert response.items[0].name == "沪深300ETF"
    assert response.items[0].change_pct == 0.73
    assert response.items[0].turnover == 1_250_000_000
    assert fake_akshare.spot_calls == 1


async def test_etf_candles_returns_live_items_from_hist_table() -> None:
    fake_akshare = ETFAkShare()
    service = ETFService(akshare_module=fake_akshare)

    response = await service.candles("510300", period="daily", limit=2)

    assert response.status == "live"
    assert response.source == "akshare-eastmoney-etf-history"
    assert [item.date for item in response.items] == ["2026-06-22", "2026-06-23"]
    assert response.items[-1].close == 4.12
    assert fake_akshare.hist_calls == [("510300", "daily")]


async def test_etf_source_failure_returns_empty_unavailable_without_sample_data() -> None:
    service = ETFService(akshare_module=FailingETFAkShare())

    search_response = await service.search("沪深", limit=5)
    candle_response = await service.candles("510300", period="daily", limit=10)

    assert search_response.status == "unavailable"
    assert search_response.items == []
    assert "spot source down" in search_response.detail
    assert candle_response.status == "unavailable"
    assert candle_response.items == []
    assert "hist source down" in candle_response.detail


async def test_etf_candles_fall_back_to_sina_daily_history() -> None:
    fake_akshare = SinaFallbackETFAkShare()
    service = ETFService(akshare_module=fake_akshare)

    response = await service.candles("510300", period="daily", limit=5)

    assert response.status == "live"
    assert response.source == "akshare-sina-etf-history"
    assert fake_akshare.sina_calls == ["sh510300"]
    assert response.items[0].source == "akshare-sina-etf-history"
    assert response.items[0].close == 4.94
    assert response.items[0].turnover == 4940


def test_etf_endpoints_return_contract_without_main_registration() -> None:
    app = FastAPI()
    app.state.etf_service = ETFService(akshare_module=ETFAkShare())
    app.include_router(router)
    client = TestClient(app)

    search_response = client.get("/api/etfs/search", params={"q": "沪深", "limit": 5})
    candles_response = client.get("/api/etfs/candles", params={"symbol": "510300", "period": "daily", "limit": 2})

    assert search_response.status_code == 200
    assert search_response.json()["items"][0]["symbol"] == "510300"
    assert candles_response.status_code == 200
    assert candles_response.json()["items"][-1]["close"] == 4.12
