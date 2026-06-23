from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import portfolio
from app.schemas.market import QuoteSnapshot
from app.schemas.portfolio import PortfolioPosition
from app.services.portfolio import analyze_portfolio


class SampleFallbackQuoteProvider:
    async def quotes(self, symbols: list[str]) -> list[QuoteSnapshot]:
        return [
            QuoteSnapshot(
                symbol=symbols[0],
                name="Apple Inc.",
                market="US",
                price=250,
                change=0,
                change_pct=0,
                volume=0,
                turnover=0,
                currency="USD",
                source="sample fallback",
                as_of=datetime(2026, 1, 1, tzinfo=UTC),
                delay_label="sample data",
            )
        ]


class FailingQuoteProvider:
    async def quotes(self, symbols: list[str]) -> list[QuoteSnapshot]:
        raise RuntimeError("quote backend down")


def test_analyzes_total_pnl_weights_and_concentration_risk() -> None:
    result = analyze_portfolio(
        [
            PortfolioPosition(
                symbol="600519.SH",
                name="贵州茅台",
                market="CN",
                quantity=10,
                cost_price=1000,
                current_price=1200,
                currency="CNY",
            ),
            PortfolioPosition(
                symbol="00700.HK",
                name="腾讯控股",
                market="HK",
                quantity=20,
                cost_price=300,
                current_price=250,
                currency="HKD",
            ),
        ]
    )

    assert result.total_value == 17000
    assert result.pnl == 1000
    assert result.positions[0].market_value == 12000
    assert result.positions[0].pnl_pct == 0.2
    assert result.weights[0].symbol == "600519.SH"
    assert round(result.weights[0].weight, 4) == 0.7059
    assert result.risks[0].level == "high"


def test_empty_portfolio_returns_zero_snapshot() -> None:
    result = analyze_portfolio([])

    assert result.total_value == 0
    assert result.pnl == 0
    assert result.positions == []
    assert result.weights == []
    assert result.risks == []


def test_analyze_rejects_sample_fallback_quote_and_keeps_local_price() -> None:
    app = FastAPI()
    app.state.market_service = SampleFallbackQuoteProvider()
    app.include_router(portfolio.router)
    client = TestClient(app)

    response = client.post(
        "/api/portfolio/analyze",
        json={
            "positions": [
                {
                    "symbol": "AAPL",
                    "name": "Apple",
                    "market": "US",
                    "quantity": 3,
                    "cost_price": 180,
                    "current_price": 200,
                    "currency": "USD",
                }
            ],
            "refresh_prices": True,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["positions"][0]["current_price"] == 200
    assert body["total_value"] == 600
    assert body["quote_status"][0]["symbol"] == "AAPL"
    assert body["quote_status"][0]["status"] == "unavailable"
    assert body["quote_status"][0]["source"] == "sample fallback"
    assert "sample" in body["quote_status"][0]["detail"].lower()
    assert body["data_warnings"]


def test_analyze_keeps_local_price_and_warns_when_quote_provider_fails() -> None:
    app = FastAPI()
    app.state.market_service = FailingQuoteProvider()
    app.include_router(portfolio.router)
    client = TestClient(app)

    response = client.post(
        "/api/portfolio/analyze",
        json={
            "positions": [
                {
                    "symbol": "AAPL",
                    "name": "Apple",
                    "market": "US",
                    "quantity": 3,
                    "cost_price": 180,
                    "current_price": 200,
                    "currency": "USD",
                }
            ],
            "refresh_prices": True,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["positions"][0]["current_price"] == 200
    assert body["total_value"] == 600
    assert body["quote_status"][0]["symbol"] == "AAPL"
    assert body["quote_status"][0]["status"] == "unavailable"
    assert "quote backend down" in body["quote_status"][0]["detail"]
    assert any("quote backend down" in warning for warning in body["data_warnings"])
