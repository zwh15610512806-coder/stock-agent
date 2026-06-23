from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.main import create_app
from app.schemas.market import QuoteSnapshot


class FakeMarketService:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    async def quotes(self, symbols: list[str]) -> list[QuoteSnapshot]:
        self.calls.append(symbols)
        return [
            QuoteSnapshot(
                symbol="AAPL",
                name="Apple Inc.",
                market="US",
                price=250,
                change=1,
                change_pct=0.4,
                volume=1000,
                turnover=250000,
                currency="USD",
                source="test-feed",
                as_of=datetime(2026, 1, 1, tzinfo=UTC),
                delay_label="test delayed",
            )
        ]


class FakeOcrService:
    async def recognize_positions(self, image_bytes: bytes, mime_type: str = "image/png"):
        return (
            "completed",
            [
                {
                    "symbol": "600519.SH",
                    "name": "贵州茅台",
                    "market": "CN",
                    "quantity": 10,
                    "cost_price": 1000,
                    "current_price": 1200,
                    "currency": "CNY",
                }
            ],
            ["ai-json"],
        )


def test_healthz() -> None:
    client = TestClient(create_app())

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_portfolio_analyze_endpoint() -> None:
    client = TestClient(create_app())

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
            "refresh_prices": False,
        },
    )

    assert response.status_code == 200
    assert response.json()["total_value"] == 600


def test_portfolio_analyze_endpoint_refreshes_prices_by_default() -> None:
    app = create_app()
    fake_market_service = FakeMarketService()
    app.state.market_service = fake_market_service
    client = TestClient(app)

    response = client.post(
        "/api/portfolio/analyze",
        json={
            "positions": [
                {
                    "symbol": "AAPL",
                    "name": "",
                    "market": "US",
                    "quantity": 3,
                    "cost_price": 180,
                    "current_price": 1,
                    "currency": "USD",
                }
            ]
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert fake_market_service.calls == [["AAPL"]]
    assert body["positions"][0]["name"] == "Apple Inc."
    assert body["positions"][0]["current_price"] == 250
    assert body["total_value"] == 750
    assert body["pnl"] == 210


def test_ocr_positions_endpoint_uses_position_recognition_service() -> None:
    app = create_app()
    app.state.ocr_service = FakeOcrService()
    client = TestClient(app)

    response = client.post(
        "/api/ocr/positions",
        files={"file": ("positions.png", b"image", "image/png")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["positions"][0]["symbol"] == "600519.SH"
    assert body["raw_lines"] == ["ai-json"]
