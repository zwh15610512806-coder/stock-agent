import json

import httpx

from app.schemas.portfolio import PortfolioPosition
from app.services.ocr import parse_position_text_lines
from app.services.ocr import DoubaoVisionOcrService, parse_ai_position_payload


def test_parses_common_broker_position_lines() -> None:
    positions = parse_position_text_lines(
        [
            "贵州茅台 600519 持仓 10 成本 1000.00 现价 1200.00",
            "腾讯控股 00700.HK 数量 20 成本价 300 当前价 250",
        ]
    )

    assert positions[0].symbol == "600519.SH"
    assert positions[0].name == "贵州茅台"
    assert positions[0].quantity == 10
    assert positions[0].cost_price == 1000
    assert positions[0].current_price == 1200
    assert positions[1].symbol == "00700.HK"
    assert positions[1].market == "HK"


def test_parses_ai_position_json_payload() -> None:
    positions = parse_ai_position_payload(
        json.dumps(
            {
                "positions": [
                    {
                        "symbol": "600519",
                        "name": "贵州茅台",
                        "market": "CN",
                        "quantity": 10,
                        "cost_price": 1000,
                        "current_price": 1200,
                    },
                    {
                        "symbol": "00700",
                        "name": "腾讯控股",
                        "market": "HK",
                        "quantity": 20,
                        "cost_price": 300,
                        "current_price": 250,
                    },
                ]
            },
            ensure_ascii=False,
        )
    )

    assert positions[0].symbol == "600519.SH"
    assert positions[0].currency == "CNY"
    assert positions[1].symbol == "00700.HK"
    assert positions[1].currency == "HKD"


def test_parses_ai_position_payload_with_chinese_keys() -> None:
    positions = parse_ai_position_payload(
        json.dumps(
            {
                "持仓列表": [
                    {
                        "股票代码": "600519",
                        "股票名称": "贵州茅台",
                        "市场": "A股",
                        "持仓数量": "10",
                        "成本价": "1,000.00",
                        "现价": "1,200.00",
                    },
                    {
                        "证券代码": 700,
                        "证券名称": "腾讯控股",
                        "市场": "港股",
                        "数量": 20,
                        "成本": 300,
                        "当前价": 250,
                    },
                ]
            },
            ensure_ascii=False,
        )
    )

    assert positions[0].symbol == "600519.SH"
    assert positions[0].name == "贵州茅台"
    assert positions[0].quantity == 10
    assert positions[0].cost_price == 1000
    assert positions[0].current_price == 1200
    assert positions[1].symbol == "00700.HK"
    assert positions[1].name == "腾讯控股"


async def test_doubao_vision_service_sends_image_and_parses_positions() -> None:
    captured_payload: dict | None = None

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_payload
        captured_payload = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "positions": [
                                        {
                                            "symbol": "AAPL",
                                            "name": "Apple",
                                            "market": "US",
                                            "quantity": 3,
                                            "cost_price": 180,
                                            "current_price": 200,
                                        }
                                    ]
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            },
        )

    service = DoubaoVisionOcrService(
        api_key="test-key",
        api_base="https://ark.test/api/v3",
        model="doubao-seed-2-0-lite-260215",
        transport=httpx.MockTransport(handler),
    )

    status, positions, raw_lines = await service.recognize_positions(b"png-bytes")

    assert status == "completed"
    assert positions == [
        PortfolioPosition(
            symbol="AAPL",
            name="Apple",
            market="US",
            quantity=3,
            cost_price=180,
            current_price=200,
            currency="USD",
        )
    ]
    assert raw_lines
    assert captured_payload is not None
    assert captured_payload["model"] == "doubao-seed-2-0-lite-260215"
    assert "券商持仓" in captured_payload["messages"][0]["content"]
    content = captured_payload["messages"][1]["content"]
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")


async def test_doubao_vision_service_uses_uploaded_image_mime_type() -> None:
    captured_payload: dict | None = None

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_payload
        captured_payload = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps({"positions": []}, ensure_ascii=False),
                        }
                    }
                ]
            },
        )

    service = DoubaoVisionOcrService(
        api_key="test-key",
        api_base="https://ark.test/api/v3",
        model="doubao-seed-2-0-lite-260215",
        transport=httpx.MockTransport(handler),
    )

    await service.recognize_positions(b"jpg-bytes", "image/jpeg")

    assert captured_payload is not None
    content = captured_payload["messages"][1]["content"]
    assert content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")


async def test_doubao_vision_service_reports_unavailable_when_api_key_missing_and_fallback_fails() -> None:
    class FailedFallback:
        async def recognize_lines(self, image_bytes: bytes):
            return "failed", []

    service = DoubaoVisionOcrService(
        api_key="",
        api_base="https://ark.test/api/v3",
        model="doubao-seed-2-0-lite-260215",
        fallback=FailedFallback(),
    )

    status, positions, raw_lines = await service.recognize_positions(b"png-bytes")

    assert status == "unavailable"
    assert positions == []
    assert raw_lines == []
