from datetime import UTC, datetime

from app.schemas.market import QuoteSnapshot
from app.services import market as market_module
from app.services.symbols import display_name_for_symbol, infer_market
from app.services.market import MarketDataService


async def test_hk_overview_prioritizes_hang_seng_tech_index() -> None:
    service = MarketDataService()

    async def fake_quote(symbol: str) -> QuoteSnapshot:
        market = infer_market(symbol)
        return QuoteSnapshot(
            symbol=symbol,
            name=display_name_for_symbol(symbol),
            market=market,
            price=100,
            currency="HKD",
            source="test",
            as_of=datetime.now(UTC),
            delay_label="test",
        )

    service.quote = fake_quote  # type: ignore[method-assign]

    overview = await service.overview(["HK"])

    assert overview[0].indices[0].symbol == "HSTECH.HK"
    assert overview[0].indices[0].name == "恒生科技指数"


async def test_yahoo_chart_uses_direct_client_and_user_agent(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "chart": {
                    "result": [
                        {
                            "meta": {
                                "currency": "USD",
                                "regularMarketPrice": 200,
                                "previousClose": 190,
                                "regularMarketVolume": 1234,
                            },
                            "timestamp": [1781812801],
                            "indicators": {"quote": [{}]},
                        }
                    ]
                }
            }

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

        async def __aenter__(self) -> "FakeClient":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def get(self, url: str, params: dict[str, str]) -> FakeResponse:
            captured["url"] = url
            captured["params"] = params
            return FakeResponse()

    monkeypatch.setattr(market_module.httpx, "AsyncClient", FakeClient)
    service = MarketDataService()

    quote = await service._fetch_yahoo_quote("AAPL")

    assert quote.price == 200
    assert captured["trust_env"] is False
    assert "Mozilla" in captured["headers"]["User-Agent"]


async def test_yahoo_candles_use_yahoo_source(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "chart": {
                    "result": [
                        {
                            "timestamp": [1781812801],
                            "indicators": {
                                "quote": [
                                    {
                                        "open": [200],
                                        "high": [205],
                                        "low": [198],
                                        "close": [203],
                                        "volume": [1234],
                                    }
                                ]
                            },
                        }
                    ]
                }
            }

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

        async def __aenter__(self) -> "FakeClient":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def get(self, url: str, params: dict[str, str]) -> FakeResponse:
            captured["url"] = url
            captured["params"] = params
            return FakeResponse()

    monkeypatch.setattr(market_module.httpx, "AsyncClient", FakeClient)
    service = MarketDataService()

    candles = await service._fetch_yahoo_candles("AAPL", "daily", 20)

    assert candles[0].source == "Yahoo Finance/free delayed fallback"
    assert candles[0].close == 203
    assert captured["params"] == {"interval": "1d", "range": "1y"}
